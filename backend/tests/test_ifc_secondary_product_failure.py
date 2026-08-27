"""A model that parsed must stay parsed when an optional extra falls over.

`process_version` finishes by committing the extracted model as READY, then
produces two secondary artefacts: the project-intelligence pass and the 3D
viewer geometry. Neither is part of the model's facts — the code says so
directly: "Intelligence and geometry are secondary products. A failure in
either must never turn successfully extracted IFC metadata into a failed
model."

Only the intelligence call was actually guarded. Geometry sat inside the outer
`try`, so anything its own broad handler could not contain — a connection lost
while it commits, the row deleted underneath it — reached the outer handler and
rewrote an already-committed READY version as FAILED, complete with a support
log ID for a parse that had succeeded.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.ifc import IFCElement, IFCModelGroup, IFCModelVersion
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services import ifc_processing_service as service

pytest.importorskip("ifcopenshell")

FIXTURE = Path(__file__).parent / "fixtures" / "multi_discipline_ifc4.ifc"
READY_STATES = {"READY", "READY_WITH_WARNINGS"}


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
def uploaded(db, tmp_path, monkeypatch):
    """A real IFC in private storage, recorded as freshly uploaded."""
    suffix = uuid4().hex[:10]
    root = tmp_path / "private"
    (root / "ifc").mkdir(parents=True)
    storage_key = f"ifc/{suffix}.ifc"
    (root / storage_key).write_bytes(FIXTURE.read_bytes())
    # The parser runs in a *spawned* process, which re-imports the settings
    # module and reads this from the environment. Patching the object alone
    # would leave the child looking in the default directory, where the file
    # does not exist, and the parse would fail as "corrupted" for no reason.
    monkeypatch.setenv("PRIVATE_UPLOAD_DIR", str(root))
    monkeypatch.setattr(settings, "PRIVATE_UPLOAD_DIR", str(root))
    monkeypatch.setattr(settings, "IFC_GEOMETRY_ENABLED", True)

    manager = User(full_name="GeomPm", email=f"geompm-{suffix}@test.local",
                   hashed_password="x", role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    owner = User(full_name="GeomOwner", email=f"geomowner-{suffix}@test.local",
                 hashed_password="x", role=UserRole.OWNER, status=UserStatus.ACTIVE)
    db.add_all([manager, owner])
    db.flush()
    project = Project(name=f"Geometry Guard {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=manager.id,
                         role_on_project=UserRole.PROJECT_MANAGER, is_active=True))
    group = IFCModelGroup(project_id=project.id, name=f"Group {suffix}", created_by_id=manager.id)
    db.add(group)
    db.flush()
    version = IFCModelVersion(
        project_id=project.id, model_group_id=group.id, version_number=1,
        title="Issued for coordination", processing_status="UPLOADED",
        uploaded_by_id=manager.id, original_filename="model.ifc",
        storage_key=storage_key, file_hash=uuid4().hex,
        file_size=FIXTURE.stat().st_size,
    )
    db.add(version)
    db.commit()
    try:
        yield {"version": version, "project": project, "manager": manager, "owner": owner}
    finally:
        _purge(db, project.id, [manager.id, owner.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    params = {"projects": [project_id], "users": list(user_ids)}
    for statement in (
        "DELETE FROM ifc_elements WHERE version_id IN (SELECT id FROM ifc_model_versions WHERE project_id = ANY(:projects))",
        "DELETE FROM ifc_spatial_nodes WHERE version_id IN (SELECT id FROM ifc_model_versions WHERE project_id = ANY(:projects))",
        "DELETE FROM ifc_processing_jobs WHERE version_id IN (SELECT id FROM ifc_model_versions WHERE project_id = ANY(:projects))",
        "DELETE FROM ifc_coordination_findings WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_suggestions WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_entity_links WHERE project_id = ANY(:projects)",
        "DELETE FROM ai_insights WHERE project_id = ANY(:projects)",
        "DELETE FROM tasks WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM ifc_model_versions WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_model_groups WHERE project_id = ANY(:projects)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
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


def _exploding_geometry(*_args, **_kwargs):
    raise RuntimeError("connection lost while recording geometry status")


def test_geometry_blowing_up_leaves_the_model_ready(db, uploaded, monkeypatch):
    monkeypatch.setattr(service, "generate_geometry", _exploding_geometry)
    version = uploaded["version"]

    service.process_version(db, version.id, uploaded["manager"].id)

    db.refresh(version)
    assert version.processing_status in READY_STATES
    assert version.parsing_error_code is None
    assert version.support_log_id is None
    assert version.processing_progress == 100


def test_the_extracted_model_survives_a_geometry_blow_up(db, uploaded, monkeypatch):
    monkeypatch.setattr(service, "generate_geometry", _exploding_geometry)
    version = uploaded["version"]

    service.process_version(db, version.id, uploaded["manager"].id)

    elements = db.query(IFCElement).filter(IFCElement.version_id == version.id).count()
    assert elements == 28
    db.refresh(version)
    assert version.model_summary_json["mainStatistics"]["storeys"] == 2


def test_intelligence_blowing_up_also_leaves_the_model_ready(db, uploaded, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("intelligence pass failed")

    monkeypatch.setattr(service, "run_project_intelligence", explode)
    monkeypatch.setattr(service, "generate_geometry", lambda *a, **k: {"status": "GEOMETRY_READY"})
    version = uploaded["version"]

    service.process_version(db, version.id, uploaded["manager"].id)

    db.refresh(version)
    assert version.processing_status in READY_STATES
    assert version.parsing_error_code is None


def test_a_real_parse_failure_is_still_recorded_as_failed(db, uploaded, monkeypatch):
    """The guard must not swallow the failures that genuinely belong to parsing."""
    def explode(*_args, **_kwargs):
        raise service.IFCParseError("IFC_FILE_CORRUPTED")

    monkeypatch.setattr(service, "parse_with_timeout", explode)
    version = uploaded["version"]

    service.process_version(db, version.id, uploaded["manager"].id)

    db.refresh(version)
    assert version.processing_status == "FAILED"
    assert version.parsing_error_code == "IFC_FILE_CORRUPTED"
    assert version.support_log_id
    assert version.parsing_error_message
