"""The `cff92f4479c8` data migration: backfilling ai_insights.message_key.

`ae32c1d7e043` added the column but left existing rows NULL. Those rows never
picked up Arabic, because the frontend only translates through `message_key`
and falls back to the stored English sentence when it is missing.

These tests exercise the migration's logic directly — both the pure mapping
function and the same SQL `run_backfill()` runs under Alembic — against rows
built the way the real detectors (`ifc_compatibility_service.py`) actually
write them, not guessed shapes.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.ifc import AIInsight, IFCModelGroup, IFCModelVersion
from app.models.project import Project
from app.models.user import User

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic" / "versions" / "cff92f4479c8_backfill_ai_insight_message_keys.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("backfill_ai_insight_message_keys", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()


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


# --- Pure mapping: no database involved -------------------------------------

def test_discipline_family_reproduces_the_live_params():
    key, params = migration.derive_backfill(
        "DISCIPLINE_PLUMBING_NOT_IN_IFC",
        {"discipline": "PLUMBING", "matchedTaskCount": 1, "expectedIfcClasses": ["IfcPipeSegment"]},
    )
    assert key == "DISCIPLINE_NOT_IN_IFC"
    assert params == {"discipline": "plumbing", "label": "plumbing / sanitary installation", "taskCount": 1}


def test_discipline_family_handles_the_compound_discipline_name():
    key, params = migration.derive_backfill(
        "DISCIPLINE_MECHANICAL_HVAC_NOT_IN_IFC",
        {"discipline": "MECHANICAL_HVAC", "matchedTaskCount": 4},
    )
    assert key == "DISCIPLINE_NOT_IN_IFC"
    assert params["discipline"] == "mechanical/hvac"
    assert params["label"] == "mechanical / HVAC installation"
    assert params["taskCount"] == 4


def test_task_elements_family_reproduces_the_live_params():
    key, params = migration.derive_backfill(
        "TASK_BEAM_ELEMENTS_MISSING",
        {"taskIds": ["a", "b"], "expectedIfcClasses": ["IfcBeam"], "modelElementTypes": []},
    )
    assert key == "TASK_ELEMENTS_MISSING"
    assert params == {"category": "beam", "taskCount": 2, "expectedClasses": "IfcBeam"}


def test_project_name_family_reproduces_the_live_params():
    key, params = migration.derive_backfill(
        "IFC_PROJECT_NAME_MISMATCH",
        {"platformProjectName": "Residential Complex C", "ifcNameScores": {"Default": 0.2}},
    )
    assert key == "IFC_PROJECT_NAME_MISMATCH"
    assert params == {"projectName": "Residential Complex C"}


def test_a_type_outside_the_known_families_derives_nothing():
    """No translation family exists for this yet; the caller falls back to
    the code-as-key rule rather than inventing one."""
    assert migration.derive_backfill("IFC_MAJOR_REVISION_DRIFT", {"storeys": {"before": 1, "after": 9}}) is None
    assert migration.derive_backfill("IFC_ASSET_TYPE_MISMATCH", {"projectType": "villa"}) is None
    assert migration.derive_backfill("IFC_PROJECT_IDENTITY_MISSING", {}) is None


def test_a_discipline_shaped_type_with_untrusted_evidence_derives_nothing():
    """Evidence that does not match the expected shape is not guessed at."""
    assert migration.derive_backfill("DISCIPLINE_PLUMBING_NOT_IN_IFC", {"discipline": "ELECTRICAL"}) is None
    assert migration.derive_backfill("DISCIPLINE_PLUMBING_NOT_IN_IFC", {}) is None
    assert migration.derive_backfill("TASK_BEAM_ELEMENTS_MISSING", {}) is None


# --- run_backfill() against a real database ---------------------------------

@pytest.fixture()
def world(db):
    suffix = uuid.uuid4().hex[:10]

    def user(name, role):
        person = User(full_name=name, email=f"{name.lower()}-{suffix}@test.local",
                      hashed_password="x", role=role, status=UserStatus.ACTIVE)
        db.add(person)
        return person

    manager = user("BackfillPm", UserRole.PROJECT_MANAGER)
    owner = user("BackfillOwner", UserRole.OWNER)
    db.flush()

    project = Project(name=f"Backfill Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()

    group = IFCModelGroup(project_id=project.id, name=f"Group {suffix}", created_by_id=manager.id)
    db.add(group)
    db.flush()
    version = IFCModelVersion(project_id=project.id, model_group_id=group.id, version_number=1,
                              revision_code="R01", title="Revision 1", processing_status="READY",
                              is_active=True, uploaded_by_id=manager.id, original_filename="r1.ifc",
                              storage_key=f"{suffix}/r1.ifc", file_hash=uuid.uuid4().hex, file_size=1024)
    db.add(version)
    db.flush()

    try:
        yield {"db": db, "project": project, "version": version, "manager": manager, "owner": owner}
    finally:
        db.rollback()
        for statement in (
            "DELETE FROM ai_insights WHERE project_id = :project",
            "DELETE FROM ifc_model_versions WHERE project_id = :project",
            "DELETE FROM ifc_model_groups WHERE project_id = :project",
            "DELETE FROM project_members WHERE project_id = :project OR user_id = ANY(:users)",
            "DELETE FROM projects WHERE id = :project",
            "DELETE FROM users WHERE id = ANY(:users)",
        ):
            db.execute(text(statement), {"project": project.id, "users": [manager.id, owner.id]})
        db.commit()


def _insight(world, *, insight_type, evidence, status="OPEN", message_key=None,
             message_params_json=None, reviewed_at=None, resolved_at=None,
             review_note=None, reviewed_by_id=None, title=None):
    item = AIInsight(
        project_id=world["project"].id, model_revision_id=world["version"].id,
        fingerprint=uuid.uuid4().hex, insight_type=insight_type, category="TEST",
        severity="WARNING", confidence=0.9, title=title or insight_type,
        description="test", reason="test", recommended_action="test",
        evidence_json=evidence, affected_json={}, message_key=message_key,
        message_params_json=message_params_json or {}, status=status,
        source_engine="IFC_COMPATIBILITY_RULES_V1",
        reviewed_at=reviewed_at, resolved_at=resolved_at,
        review_note=review_note, reviewed_by_id=reviewed_by_id,
    )
    world["db"].add(item)
    world["db"].flush()
    return item


def test_legacy_discipline_row_is_backfilled_with_the_live_family(world):
    row = _insight(world, insight_type="DISCIPLINE_PLUMBING_NOT_IN_IFC",
                   evidence={"discipline": "PLUMBING", "matchedTaskCount": 1,
                             "expectedIfcClasses": ["IfcPipeSegment"], "modelElementTypes": []})
    updated = migration.run_backfill(world["db"].connection())
    assert updated >= 1
    world["db"].refresh(row)
    assert row.message_key == "DISCIPLINE_NOT_IN_IFC"
    assert row.message_params_json == {
        "discipline": "plumbing", "label": "plumbing / sanitary installation", "taskCount": 1,
    }


def test_legacy_task_elements_row_is_backfilled(world):
    row = _insight(world, insight_type="TASK_WALL_ELEMENTS_MISSING",
                   evidence={"taskIds": ["a"], "expectedIfcClasses": ["IfcWall", "IfcWallStandardCase"],
                             "modelElementTypes": []})
    migration.run_backfill(world["db"].connection())
    world["db"].refresh(row)
    assert row.message_key == "TASK_ELEMENTS_MISSING"
    assert row.message_params_json == {
        "category": "wall", "taskCount": 1, "expectedClasses": "IfcWall, IfcWallStandardCase",
    }


def test_legacy_project_name_row_is_backfilled(world):
    row = _insight(world, insight_type="IFC_PROJECT_NAME_MISMATCH",
                   evidence={"platformProjectName": "Backfill Project X", "ifcNameScores": {}})
    migration.run_backfill(world["db"].connection())
    world["db"].refresh(row)
    assert row.message_key == "IFC_PROJECT_NAME_MISMATCH"
    assert row.message_params_json == {"projectName": "Backfill Project X"}


def test_a_type_with_no_translation_family_gets_the_code_as_key_fallback(world):
    """Matches the data gap, doesn't paper over it: message_key becomes
    consistent with what live code would write, but no localized string
    exists for it yet, so this alone does not make it render in Arabic."""
    row = _insight(world, insight_type="IFC_MAJOR_REVISION_DRIFT",
                   evidence={"storeys": {"before": 2, "after": 9}})
    migration.run_backfill(world["db"].connection())
    world["db"].refresh(row)
    assert row.message_key == "IFC_MAJOR_REVISION_DRIFT"
    assert row.message_params_json == {"storeys": {"before": 2, "after": 9}}


def test_already_localized_rows_are_left_exactly_as_they_are(world):
    """A row a modern write already localized must not be touched."""
    row = _insight(world, insight_type="DISCIPLINE_ELECTRICAL_NOT_IN_IFC",
                   evidence={"discipline": "ELECTRICAL", "matchedTaskCount": 9},
                   message_key="DISCIPLINE_NOT_IN_IFC",
                   message_params_json={"discipline": "electrical", "label": "electrical installation", "taskCount": 9})
    migration.run_backfill(world["db"].connection())
    world["db"].refresh(row)
    assert row.message_key == "DISCIPLINE_NOT_IN_IFC"
    assert row.message_params_json == {"discipline": "electrical", "label": "electrical installation", "taskCount": 9}


def test_running_the_backfill_twice_is_a_no_op_the_second_time(world):
    row = _insight(world, insight_type="DISCIPLINE_STRUCTURAL_NOT_IN_IFC",
                   evidence={"discipline": "STRUCTURAL", "matchedTaskCount": 3})
    first = migration.run_backfill(world["db"].connection())
    assert first >= 1
    second = migration.run_backfill(world["db"].connection())
    assert second == 0
    world["db"].refresh(row)
    assert row.message_key == "DISCIPLINE_NOT_IN_IFC"


def test_the_backfill_does_not_change_status_lifecycle_or_duplicate_rows(world):
    reviewer = world["manager"]
    fixed_time = None
    row = _insight(world, insight_type="TASK_COLUMN_ELEMENTS_MISSING",
                   evidence={"taskIds": ["a", "b"], "expectedIfcClasses": ["IfcColumn"]},
                   status="RESOLVED", review_note="handled", reviewed_by_id=reviewer.id)
    before_id, before_status, before_fingerprint = row.id, row.status, row.fingerprint
    before_created_at, before_note = row.created_at, row.review_note
    project_row_count_before = world["db"].query(AIInsight).filter(
        AIInsight.project_id == world["project"].id).count()

    migration.run_backfill(world["db"].connection())
    world["db"].refresh(row)

    assert row.id == before_id
    assert row.status == before_status == "RESOLVED"
    assert row.fingerprint == before_fingerprint
    assert row.created_at == before_created_at
    assert row.review_note == before_note
    assert row.message_key == "TASK_ELEMENTS_MISSING"
    project_row_count_after = world["db"].query(AIInsight).filter(
        AIInsight.project_id == world["project"].id).count()
    assert project_row_count_after == project_row_count_before
