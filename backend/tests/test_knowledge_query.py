"""The routed knowledge endpoint, against a real project with a real model.

Reuses the Phase 2 interference fixture, so the IFC answers here are built from
genuinely tessellated geometry and a genuinely detected finding — not from
rows written by the test to make an assertion pass.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.knowledge import query_project_knowledge
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, TaskStatus, UserRole, UserStatus
from app.models.ifc import IFCModelGroup, IFCModelVersion
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.schemas.knowledge import KnowledgeQueryRequest
from app.services import ifc_processing_service as service

pytest.importorskip("ifcopenshell")

FIXTURE = Path(__file__).parent / "fixtures" / "interference_ifc4.ifc"


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
def world(db, tmp_path, monkeypatch):
    suffix = uuid4().hex[:10]
    root = tmp_path / "private"
    (root / "ifc").mkdir(parents=True)
    storage_key = f"ifc/{suffix}.ifc"
    (root / storage_key).write_bytes(FIXTURE.read_bytes())
    monkeypatch.setenv("PRIVATE_UPLOAD_DIR", str(root))
    monkeypatch.setattr(settings, "PRIVATE_UPLOAD_DIR", str(root))
    monkeypatch.setattr(settings, "IFC_GEOMETRY_ENABLED", True)
    monkeypatch.setattr(settings, "IFC_COORDINATION_CHECKS_ENABLED", True)

    manager = User(full_name="KnowPm", email=f"knowpm-{suffix}@example.com", hashed_password="x",
                   role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    owner = User(full_name="KnowOwner", email=f"knowowner-{suffix}@example.com", hashed_password="x",
                 role=UserRole.OWNER, status=UserStatus.ACTIVE)
    db.add_all([manager, owner])
    db.flush()
    project = Project(name=f"Knowledge {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=manager.id,
                         role_on_project=UserRole.PROJECT_MANAGER, is_active=True))
    # `task_code` is NOT NULL; the API generates it with `_next_task_code`,
    # and a fixture has to supply one just the same.
    db.add_all([
        Task(project_id=project.id, task_code="T-001", name="Pour ground slab",
             status=TaskStatus.DONE, progress_percentage=100, created_by_id=manager.id),
        Task(project_id=project.id, task_code="T-002", name="Erect steel frame",
             status=TaskStatus.IN_PROGRESS, progress_percentage=40, created_by_id=manager.id),
    ])
    group = IFCModelGroup(project_id=project.id, name=f"Group {suffix}", created_by_id=manager.id)
    db.add(group)
    db.flush()
    version = IFCModelVersion(
        project_id=project.id, model_group_id=group.id, version_number=1,
        revision_code="P01", title="Coordination model", processing_status="UPLOADED",
        uploaded_by_id=manager.id, original_filename="interference.ifc",
        storage_key=storage_key, file_hash=uuid4().hex, file_size=FIXTURE.stat().st_size,
        is_active=True,
    )
    db.add(version)
    db.commit()
    service.process_version(db, version.id, manager.id)
    db.commit()
    try:
        yield {"project": project, "manager": manager, "version": version}
    finally:
        _purge(db, project.id, [manager.id, owner.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    params = {"projects": [project_id], "users": list(user_ids)}
    for statement in (
        "DELETE FROM ifc_coordination_findings WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_elements WHERE version_id IN (SELECT id FROM ifc_model_versions WHERE project_id = ANY(:projects))",
        "DELETE FROM ifc_spatial_nodes WHERE version_id IN (SELECT id FROM ifc_model_versions WHERE project_id = ANY(:projects))",
        "DELETE FROM ifc_processing_jobs WHERE version_id IN (SELECT id FROM ifc_model_versions WHERE project_id = ANY(:projects))",
        "DELETE FROM ifc_suggestions WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_entity_links WHERE project_id = ANY(:projects)",
        "DELETE FROM ai_insights WHERE project_id = ANY(:projects)",
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
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


def ask(db, world, question, language=None):
    return query_project_knowledge(
        world["project"].id, KnowledgeQueryRequest(query=question, language=language),
        db=db, current_user=world["manager"],
    )


# --- Structured data is preferred, and no documents are touched -------------

def test_project_progress_is_answered_from_records_not_documents(db, world):
    response = ask(db, world, "what is the project progress?")
    assert response.source == "PROJECT_STRUCTURED"
    assert response.topic == "PROJECT_PROGRESS"
    assert response.found is True
    assert response.answer
    assert all(citation.source_type == "PROJECT_RECORD" for citation in response.citations)


def test_a_structured_answer_carries_the_numbers_behind_it(db, world):
    response = ask(db, world, "what is the project progress?")
    assert response.data, "a project-record answer should expose its facts"


def test_the_same_question_in_arabic_reaches_the_same_source(db, world):
    assert ask(db, world, "شو نسبة الإنجاز؟").source == "PROJECT_STRUCTURED"


# --- IFC knowledge is retrievable -------------------------------------------

def test_a_clash_question_is_answered_from_the_model(db, world):
    response = ask(db, world, "what conflicts with the transfer beam")
    assert response.source == "IFC_MODEL"
    assert response.found is True
    assert any(c.source_type == "IFC_COORDINATION_FINDING" for c in response.citations)


def test_the_model_answer_cites_a_finding_that_really_exists(db, world):
    from app.models.ifc import IFCCoordinationFinding

    response = ask(db, world, "are there any clashes")
    citation = next(c for c in response.citations if c.source_type == "IFC_COORDINATION_FINDING")
    stored = db.get(IFCCoordinationFinding, citation.source_id)
    assert stored is not None
    assert stored.project_id == world["project"].id


def test_the_model_answer_keeps_the_findings_own_hedge(db, world):
    """A fact lifted out of its card must carry the caveat the card carried."""
    response = ask(db, world, "are there any clashes")
    assert "verify" in response.answer.casefold()
    assert "potential-interference" in response.answer


def test_the_evidence_behind_a_model_citation_travels_with_it(db, world):
    response = ask(db, world, "are there any clashes")
    citation = next(c for c in response.citations if c.source_type == "IFC_COORDINATION_FINDING")
    assert citation.evidence["penetrationMetres"] == pytest.approx(0.3)
    assert citation.evidence["severity"] == "HIGH"


def test_naming_an_element_narrows_the_answer_to_it(db, world):
    response = ask(db, world, "what conflicts with Supply Duct SA-01")
    assert response.found is True
    assert response.source == "IFC_MODEL"


def test_an_element_question_without_a_clash_word_describes_the_element(db, world):
    response = ask(db, world, "tell me about ifc element Transfer Beam B1")
    assert response.source == "IFC_MODEL"
    assert response.found is True
    assert any(c.source_type == "IFC_ELEMENT" for c in response.citations)


def test_an_unknown_element_says_so_instead_of_inventing_one(db, world):
    response = ask(db, world, "what conflicts with element ZZZQQQ999")
    assert response.found is False
    assert "matched" in response.answer.casefold() or "no coordination" in response.answer.casefold()


# --- Documents, and the honest empty answer ---------------------------------

def test_a_document_question_routes_to_documents(db, world):
    response = ask(db, world, "what does the specification say about concrete grade")
    assert response.source == "DOCUMENTS"
    # Nothing is indexed in this project, and that is reported rather than
    # answered around.
    assert response.found is False
    assert "indexed" in response.answer.casefold()


def test_every_routed_answer_explains_why_that_source_was_chosen(db, world):
    for question in ("what is the project progress?", "are there any clashes",
                     "what does the specification say about grout"):
        response = ask(db, world, question)
        assert response.route_reason
        assert response.source in {"PROJECT_STRUCTURED", "IFC_MODEL", "DOCUMENTS", "SITE_REPORTS"}


def test_access_to_another_project_is_refused(db, world):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as failure:
        query_project_knowledge(
            uuid4(), KnowledgeQueryRequest(query="what is the project progress?"),
            db=db, current_user=world["manager"],
        )
    assert failure.value.status_code == 403
