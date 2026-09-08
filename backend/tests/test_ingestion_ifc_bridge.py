"""IFC appears in the unified file view without the IFC engine being touched.

Two properties matter here, and they pull in opposite directions:

  * an IFC revision **must** show up in the project's file list, or "every file
    on this project" is a lie;
  * the ingestion layer **must not** become a second source of truth about IFC
    processing state, because two copies of a status is how they drift.

The resolution is derivation: one bookkeeping row, and a status read from the
`IFCModelVersion` at process time. These tests pin the mapping, the
idempotence, and — most importantly — that a bookkeeping failure can never take
an IFC upload down with it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.ifc import IFCModelGroup, IFCModelVersion
from app.models.ingestion import IngestedFile
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.ingestion import ifc_bridge, state
from app.services.ingestion.categories import FileCategory
from app.services.ingestion.contracts import ProcessorContext
from app.services.ingestion.processors.ifc import IFCProcessor
from app.services.ifc_processing_service import VERSION_TRANSITIONS


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:  # pragma: no cover - only without a database
        session.close()
        pytest.skip("database is not reachable")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def world(db):
    suffix = uuid4().hex[:10]
    manager = User(full_name="BridgePm", email=f"bridgepm-{suffix}@example.com",
                   hashed_password="x", role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    owner = User(full_name="BridgeOwner", email=f"bridgeowner-{suffix}@example.com",
                 hashed_password="x", role=UserRole.OWNER, status=UserStatus.ACTIVE)
    db.add_all([manager, owner])
    db.flush()
    project = Project(name=f"Bridge {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=manager.id,
                         role_on_project=UserRole.PROJECT_MANAGER, is_active=True))
    group = IFCModelGroup(project_id=project.id, name=f"Architecture {suffix}",
                          created_by_id=manager.id)
    db.add(group)
    db.commit()
    try:
        yield {"project": project, "manager": manager, "group": group, "suffix": suffix}
    finally:
        _purge(db, project.id, [manager.id, owner.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    params = {"projects": [project_id], "users": list(user_ids)}
    for statement in (
        "DELETE FROM ingestion_jobs WHERE file_id IN "
        "(SELECT id FROM ingested_files WHERE project_id = ANY(:projects))",
        "DELETE FROM ingested_files WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_model_versions WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_model_groups WHERE project_id = ANY(:projects)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        try:
            db.execute(text(statement), params)
        except SQLAlchemyError:
            db.rollback()
    db.commit()


def make_version(db, world, *, status="READY", number=1, **overrides):
    version = IFCModelVersion(
        model_group_id=world["group"].id, project_id=world["project"].id,
        version_number=number, title=f"Rev {number}",
        original_filename="tower.ifc",
        storage_key=f"ifc/{uuid4()}_tower.ifc",
        file_hash=uuid4().hex + uuid4().hex[:0].ljust(0, "0"),
        file_size=2048, uploaded_by_id=world["manager"].id,
        processing_status=status, ifc_schema="IFC4",
        authoring_application="Revit 2025", entity_count=1200,
        **overrides,
    )
    db.add(version)
    db.commit()
    return version


# --- Registration -----------------------------------------------------------

def test_an_ifc_revision_becomes_a_file_in_the_unified_view(db, world):
    version = make_version(db, world)
    file = ifc_bridge.register_version(db, version)
    db.commit()
    assert file.project_id == world["project"].id
    assert file.file_category == FileCategory.IFC.value
    assert file.source_entity_type == "IFC_MODEL_VERSION"
    assert file.source_entity_id == version.id
    # The same storage object, not a copy: the IFC subsystem still owns it.
    assert file.storage_key == version.storage_key
    assert file.checksum_sha256 == version.file_hash


def test_registering_the_same_revision_twice_produces_one_row(db, world):
    version = make_version(db, world)
    first = ifc_bridge.register_version(db, version)
    db.commit()
    second = ifc_bridge.register_version(db, version)
    db.commit()
    assert first.id == second.id
    assert db.query(IngestedFile).filter(
        IngestedFile.source_entity_id == version.id).count() == 1


def test_a_bookkeeping_failure_returns_none_rather_than_breaking_the_upload(db, world, monkeypatch):
    """The property the IFC upload path depends on. See the module docstring."""
    version = make_version(db, world)
    monkeypatch.setattr(
        ifc_bridge.IngestedFile, "__init__",
        lambda self, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert ifc_bridge.register_version(db, version) is None


def test_a_database_level_failure_leaves_the_callers_transaction_usable(db, world):
    """The reason the write sits in a SAVEPOINT.

    Returning None is not enough on its own. A failed flush poisons the
    session, so without `begin_nested` the *caller's* next statement — the
    audit record and the commit in `upload_version` — would raise
    `PendingRollbackError`, and the IFC upload this is meant to survive would
    fail because of a bookkeeping row.
    """
    version = make_version(db, world, number=1)

    # An unrelated ingested file already occupying this version's storage key,
    # so registering the version violates `uq_ingested_files_storage_key`. The
    # idempotency lookup misses it, because it names no source entity.
    db.add(IngestedFile(
        project_id=world["project"].id, uploaded_by_id=world["manager"].id,
        original_filename="squatter.ifc", normalized_filename="squatter.ifc",
        file_category=FileCategory.IFC.value, storage_key=version.storage_key,
        status=state.UPLOADED,
    ))
    db.commit()

    assert ifc_bridge.register_version(db, version) is None

    # The proof: the session still works. Before the savepoint, this raised.
    db.add(IFCModelVersion(
        model_group_id=world["group"].id, project_id=world["project"].id,
        version_number=2, title="Rev 2", original_filename="after.ifc",
        storage_key=f"ifc/{uuid4()}_after.ifc", file_hash=uuid4().hex,
        file_size=1, uploaded_by_id=world["manager"].id, processing_status="UPLOADED",
    ))
    db.commit()
    assert db.query(IFCModelVersion).filter(
        IFCModelVersion.project_id == world["project"].id).count() == 2


def test_a_backfill_registers_only_the_revisions_that_have_no_row(db, world):
    first = make_version(db, world, number=1)
    ifc_bridge.register_version(db, first)
    db.commit()
    make_version(db, world, number=2)
    make_version(db, world, number=3)
    created = ifc_bridge.backfill_project(db, world["project"].id)
    db.commit()
    assert created == 2
    assert db.query(IngestedFile).filter(
        IngestedFile.project_id == world["project"].id).count() == 3
    # Repeatable: running it again adds nothing.
    assert ifc_bridge.backfill_project(db, world["project"].id) == 0


# --- Derived status ---------------------------------------------------------

def test_the_status_map_covers_every_state_the_ifc_engine_can_be_in():
    """A new IFC state must fail here, not produce a silently wrong status."""
    engine_states = set(VERSION_TRANSITIONS) | {
        target for targets in VERSION_TRANSITIONS.values() for target in targets
    }
    assert engine_states <= set(ifc_bridge.IFC_STATUS_MAP)


@pytest.mark.parametrize(
    "ifc_status,expected",
    [
        ("READY", state.READY),
        ("READY_WITH_WARNINGS", state.PARTIAL),
        ("FAILED", state.FAILED),
        ("PARSING", state.PARTIAL),
        ("ARCHIVED", state.PARTIAL),
    ],
)
def test_the_file_status_is_derived_from_the_version(db, world, ifc_status, expected):
    version = make_version(db, world, status=ifc_status)
    file = ifc_bridge.register_version(db, version)
    db.commit()
    context = ProcessorContext(db=db, file=file, storage=None, depth=0)
    outcome = ifc_bridge.outcome_for_version(
        version, {"processor": "ifc", "category": "IFC", "extraction": "MODEL", "details": {}},
    )
    assert outcome.status == expected


def test_a_failed_version_carries_its_own_error_code_through(db, world):
    version = make_version(db, world, status="FAILED",
                           parsing_error_code="IFC_FILE_CORRUPTED",
                           parsing_error_message="truncated at byte 1024")
    outcome = ifc_bridge.outcome_for_version(version, {})
    assert outcome.status == state.FAILED
    assert outcome.error_code == "IFC_FILE_CORRUPTED"


def test_the_version_details_are_the_engines_answer_not_a_header_guess(db, world):
    version = make_version(db, world)
    details = ifc_bridge.version_details(version)
    assert details["entityCount"] == 1200
    assert details["ifcSchema"] == "IFC4"
    assert details["ifcVersionId"] == str(version.id)


def test_a_file_not_linked_to_a_version_finds_none(db, world):
    unlinked = IngestedFile(
        project_id=world["project"].id, uploaded_by_id=world["manager"].id,
        original_filename="loose.ifc", normalized_filename="loose.ifc",
        file_category=FileCategory.IFC.value, storage_key=f"ingest/{uuid4()}_loose.ifc",
        status=state.UPLOADED,
    )
    db.add(unlinked)
    db.flush()
    assert ifc_bridge.linked_version(db, unlinked) is None


def test_the_ifc_processor_prefers_the_engines_facts_when_a_version_exists(db, world, tmp_path,
                                                                          monkeypatch):
    from app.core.config import settings
    from app.services.private_storage import LocalFilesystemStorage

    monkeypatch.setattr(settings, "PRIVATE_UPLOAD_DIR", str(tmp_path))
    storage = LocalFilesystemStorage()
    version = make_version(db, world, status="READY")
    with storage.writable_local_path(version.storage_key) as target:
        target.write_bytes(
            b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\nENDSEC;\n"
        )
    file = ifc_bridge.register_version(db, version)
    db.commit()

    outcome = IFCProcessor().process(
        ProcessorContext(db=db, file=file, storage=storage, depth=0)
    )
    assert outcome.status == state.READY
    # The header says IFC2X3 and the engine says IFC4. The engine wins, because
    # it comes from a full parse rather than a 64 KB read.
    assert outcome.metadata["details"]["ifcSchema"] == "IFC4"
    assert outcome.metadata["details"]["entityCount"] == 1200
