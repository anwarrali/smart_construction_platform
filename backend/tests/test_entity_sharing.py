"""Sharing project entities as messages — "Forward" / "Ask for Opinion".

The central guarantee under test is that sharing is *communication*: it
creates a Message and nothing else, so the shared entity's ownership,
assignee, status and verification state are all unchanged afterwards.
"""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.messages import share_entity
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.design_change import DesignChange
from app.models.document import Document
from app.models.enums import (
    DesignChangeStatus, DocumentType, IssueSeverity, IssueStatus,
    ProjectStatus, TaskStatus, UserRole, UserStatus,
)
from app.models.issue import Issue
from app.models.message import Conversation, Message
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.site_report import SiteReport
from app.models.task import Task
from app.models.user import User
from app.schemas.message import ShareEntityCreate


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

    def user(name, role, affiliation=None):
        person = User(full_name=name, email=f"{name.lower()}.{suffix}@constro.io",
                      hashed_password="x", role=role, status=UserStatus.ACTIVE,
                      engineer_affiliation=affiliation)
        db.add(person)
        return person

    people = {
        "manager": user("SharePm", UserRole.PROJECT_MANAGER),
        "owner": user("ShareOwner", UserRole.OWNER),
        "engineer_a": user("ShareEngineerA", UserRole.ENGINEER, "main_contractor"),
        "engineer_b": user("ShareEngineerB", UserRole.ENGINEER, "main_contractor"),
        "worker": user("ShareWorker", UserRole.WORKER),
        "outsider": user("ShareOutsider", UserRole.ENGINEER, "main_contractor"),
        "other_project_engineer": user("ShareOtherEngineer", UserRole.ENGINEER, "main_contractor"),
    }
    db.flush()

    project = Project(name=f"Sharing Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["owner"].id, project_manager_id=people["manager"].id)
    other_project = Project(name=f"Unrelated Sharing Project {suffix}", status=ProjectStatus.ACTIVE,
                            owner_id=people["owner"].id, project_manager_id=people["manager"].id)
    db.add_all([project, other_project])
    db.flush()
    for person in (people["manager"], people["engineer_a"], people["engineer_b"], people["worker"]):
        db.add(ProjectMember(project_id=project.id, user_id=person.id,
                             role_on_project=person.role, is_active=True))
    db.add(ProjectMember(project_id=other_project.id, user_id=people["other_project_engineer"].id,
                         role_on_project=UserRole.ENGINEER, is_active=True))
    db.flush()

    issue = Issue(project_id=project.id, title="Electrical routing conflict",
                  description="Ceiling void clashes with the cable tray run.",
                  severity=IssueSeverity.HIGH, status=IssueStatus.OPEN,
                  raised_by_id=people["engineer_a"].id)
    task = Task(project_id=project.id, name="Level 3 slab pour", task_code=f"T-{suffix[:4]}",
                description="Pour and cure the level 3 slab.", status=TaskStatus.IN_PROGRESS,
                created_by_id=people["manager"].id)
    report = SiteReport(project_id=project.id, submitted_by_id=people["engineer_a"].id,
                        report_date=date.today(), summary_text="Slab poured on grid B.",
                        review_status="submitted")
    change = DesignChange(project_id=project.id, title="Raise ceiling void by 100mm",
                          description="Needed to clear the revised duct route.",
                          source_discipline="architectural", status=DesignChangeStatus.PROPOSED,
                          proposed_by_id=people["engineer_a"].id)
    document = Document(project_id=project.id, uploaded_by_id=people["manager"].id,
                        title="Revised ceiling plan", document_type=DocumentType.DRAWING,
                        file_url="/uploads/docs/ceiling.pdf")
    db.add_all([issue, task, report, change, document])
    db.flush()
    task.assignees.append(people["engineer_a"])
    db.flush()

    people.update({
        "project": project, "other_project": other_project, "issue": issue,
        "task": task, "report": report, "change": change, "document": document,
        "db": db,
    })
    yield people
    _purge(db, [project.id, other_project.id],
           [p.id for p in people.values() if isinstance(p, User)])


def _purge(db, project_ids, user_ids):
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM message_recipient_states WHERE user_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "UPDATE messages SET responded_to_message_id = NULL, forwarded_from_message_id = NULL, "
        "forward_origin_message_id = NULL WHERE conversation_id IN "
        "(SELECT id FROM conversations WHERE project_id = ANY(:projects))",
        "DELETE FROM messages WHERE conversation_id IN "
        "(SELECT id FROM conversations WHERE project_id = ANY(:projects))",
        "DELETE FROM conversation_participants WHERE conversation_id IN "
        "(SELECT id FROM conversations WHERE project_id = ANY(:projects))",
        "DELETE FROM conversations WHERE project_id = ANY(:projects)",
        "DELETE FROM documents WHERE project_id = ANY(:projects)",
        "DELETE FROM design_change_affected_disciplines WHERE design_change_id IN "
        "(SELECT id FROM design_changes WHERE project_id = ANY(:projects))",
        "DELETE FROM design_changes WHERE project_id = ANY(:projects)",
        "DELETE FROM site_reports WHERE project_id = ANY(:projects)",
        "DELETE FROM issues WHERE project_id = ANY(:projects)",
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
        "DELETE FROM tasks WHERE project_id = ANY(:projects)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), params)
    db.commit()


def _share(db, actor, entity_type, entity_id, recipient, note=None):
    return share_entity(
        ShareEntityCreate(entity_type=entity_type, entity_id=entity_id,
                          recipient_ids=[recipient.id], note=note),
        db=db, current_user=actor,
    )


# --- Issue: the required integration -----------------------------------------

def test_sharing_an_issue_delivers_its_context_to_the_recipient(db, world):
    result = _share(db, world["engineer_a"], "ISSUE", world["issue"].id, world["engineer_b"],
                    note="Can you review this and give me your opinion?")
    db.commit()
    message = result["messages"][-1]

    assert message["shared_entity_type"] == "ISSUE"
    assert message["shared_entity_id"] == world["issue"].id
    content = message["content"]
    assert "Shared Issue" in content
    assert world["issue"].title in content
    assert world["project"].name in content
    assert "Open" in content and "High" in content
    assert world["engineer_a"].full_name in content       # original owner
    assert "Can you review this and give me your opinion?" in content


def test_sharing_an_issue_notifies_the_recipient(db, world):
    result = _share(db, world["engineer_a"], "ISSUE", world["issue"].id, world["engineer_b"])
    db.commit()
    notification = db.query(Notification).filter(
        Notification.user_id == world["engineer_b"].id,
        Notification.related_entity_id == result["id"],
    ).first()
    assert notification is not None
    assert "shared an issue with you" in notification.title.lower()


def test_sharing_is_recorded_in_the_audit_log(db, world):
    result = _share(db, world["engineer_a"], "ISSUE", world["issue"].id, world["engineer_b"])
    db.commit()
    audit = db.query(AuditLog).filter(
        AuditLog.entity_type == "conversation", AuditLog.entity_id == result["id"],
    ).first()
    assert audit is not None and audit.action == "entity_shared"


# --- Ownership / state must never change (the critical guarantee) ------------

def test_sharing_an_issue_does_not_transfer_ownership_or_change_status(db, world):
    issue = world["issue"]
    _share(db, world["engineer_a"], "ISSUE", issue.id, world["engineer_b"],
           note="Please advise")
    db.commit()
    db.refresh(issue)
    assert issue.raised_by_id == world["engineer_a"].id
    assert issue.assigned_to_id is None
    assert issue.status == IssueStatus.OPEN
    # and no duplicate issue was created as a side effect of sharing
    assert db.query(Issue).filter(Issue.project_id == world["project"].id).count() == 1


def test_sharing_a_task_does_not_change_the_assignee(db, world):
    task = world["task"]
    # Shared to the task's own assignee, who can access it under the existing
    # task rules — see `test_a_task_cannot_be_shared_to_an_unassigned_engineer`
    # for why an arbitrary engineer is not a valid recipient here.
    _share(db, world["manager"], "TASK", task.id, world["engineer_a"],
           note="Opinion please")
    db.commit()
    db.refresh(task)
    assert [person.id for person in task.assignees] == [world["engineer_a"].id]
    assert task.status == TaskStatus.IN_PROGRESS


def test_a_task_cannot_be_shared_to_an_unassigned_engineer(db, world):
    """Documents the boundary this feature deliberately does not cross.

    `can_access_context` restricts a main-contractor Engineer to the tasks
    assigned to them. Sharing therefore cannot be used to show an unassigned
    Engineer a task they could not open themselves — consulting them requires
    widening that existing rule, which is out of scope here rather than
    something sharing may quietly override.
    """
    with pytest.raises(HTTPException) as error:
        _share(db, world["manager"], "TASK", world["task"].id, world["engineer_b"])
    assert error.value.status_code == 403
    assert "cannot access" in error.value.detail.lower()


def test_sharing_a_site_report_does_not_change_its_verification_state(db, world):
    report = world["report"]
    _share(db, world["manager"], "SITE_REPORT", report.id, world["engineer_b"])
    db.commit()
    db.refresh(report)
    assert report.review_status == "submitted"
    assert report.reviewed_by_id is None
    assert report.reviewed_at is None


def test_sharing_a_design_change_does_not_modify_it(db, world):
    change = world["change"]
    _share(db, world["engineer_a"], "DESIGN_CHANGE", change.id, world["manager"],
           note="Does this affect your discipline?")
    db.commit()
    db.refresh(change)
    assert change.status == DesignChangeStatus.PROPOSED
    assert change.approved_by_id is None
    assert change.proposed_by_id == world["engineer_a"].id


def test_sharing_a_document_does_not_modify_it(db, world):
    document = world["document"]
    before = document.version
    _share(db, world["manager"], "DOCUMENT", document.id, world["engineer_b"])
    db.commit()
    db.refresh(document)
    assert document.version == before
    assert document.uploaded_by_id == world["manager"].id


# --- Every supported entity carries real context -----------------------------

@pytest.mark.parametrize("entity_key,entity_type,expected,recipient_key", [
    # The Task row goes to its own assignee: an unassigned Engineer legitimately
    # cannot access it (see test_a_task_cannot_be_shared_to_an_unassigned_engineer).
    ("task", "TASK", "Shared Task", "engineer_a"),
    ("report", "SITE_REPORT", "Shared Site Report", "engineer_b"),
    ("change", "DESIGN_CHANGE", "Shared Design Change", "engineer_b"),
    ("document", "DOCUMENT", "Shared Document", "engineer_b"),
])
def test_each_supported_entity_produces_a_context_summary(
    db, world, entity_key, entity_type, expected, recipient_key,
):
    result = _share(db, world["manager"], entity_type, world[entity_key].id, world[recipient_key])
    db.commit()
    message = result["messages"][-1]
    assert message["content"].startswith(expected)
    assert world["project"].name in message["content"]
    assert message["shared_entity_type"] == entity_type
    assert message["shared_entity_id"] == world[entity_key].id


# --- Permissions and project isolation ---------------------------------------

def test_cannot_share_to_a_user_outside_the_project(db, world):
    with pytest.raises(HTTPException) as error:
        _share(db, world["engineer_a"], "ISSUE", world["issue"].id, world["outsider"])
    assert error.value.status_code == 403


def test_cannot_use_sharing_to_leak_into_an_unrelated_project(db, world):
    with pytest.raises(HTTPException) as error:
        _share(db, world["engineer_a"], "ISSUE", world["issue"].id,
               world["other_project_engineer"])
    assert error.value.status_code == 403
    leaked = db.query(Conversation).filter(
        Conversation.project_id == world["project"].id,
        Conversation.participants.any(user_id=world["other_project_engineer"].id),
    ).first()
    assert leaked is None


def test_a_user_without_access_to_the_entity_cannot_share_it(db, world):
    """A Worker is excluded from Issues by the entity's own access rules, so
    they must not be able to read one out through sharing either."""
    with pytest.raises(HTTPException) as error:
        _share(db, world["worker"], "ISSUE", world["issue"].id, world["manager"])
    assert error.value.status_code == 403


def test_a_recipient_who_cannot_access_the_entity_is_rejected(db, world):
    """The document/issue permission must not be weakened by sharing: a Worker
    cannot access project documents, so sharing one *to* them is refused
    rather than silently delivering the content."""
    with pytest.raises(HTTPException) as error:
        _share(db, world["manager"], "DOCUMENT", world["document"].id, world["worker"])
    assert error.value.status_code == 403
    assert "cannot access" in error.value.detail.lower()


def test_sharing_an_unknown_entity_is_a_404(db, world):
    with pytest.raises(HTTPException) as error:
        share_entity(
            ShareEntityCreate(entity_type="ISSUE", entity_id=uuid4(),
                              recipient_ids=[world["engineer_b"].id]),
            db=db, current_user=world["engineer_a"],
        )
    assert error.value.status_code == 404


def test_an_unsupported_entity_type_is_rejected(db, world):
    with pytest.raises(HTTPException) as error:
        share_entity(
            ShareEntityCreate(entity_type="INVOICE", entity_id=world["issue"].id,
                              recipient_ids=[world["engineer_b"].id]),
            db=db, current_user=world["engineer_a"],
        )
    assert error.value.status_code == 422


def test_sharing_requires_at_least_one_recipient(world):
    with pytest.raises(ValidationError):
        ShareEntityCreate(entity_type="ISSUE", entity_id=world["issue"].id, recipient_ids=[])


# --- Consultation: the recipient can reply without taking anything over ------

def test_the_recipient_can_reply_in_the_shared_thread(db, world):
    from app.api.messages import send_conversation_message
    from app.schemas.message import MessageSend

    result = _share(db, world["engineer_a"], "ISSUE", world["issue"].id, world["engineer_b"],
                    note="Can you review this and give me your opinion?")
    db.commit()
    reply = send_conversation_message(
        result["id"], MessageSend(content="Looks like it affects the structural drop beam."),
        db=db, current_user=world["engineer_b"],
    )
    db.commit()
    assert reply.sender_id == world["engineer_b"].id
    # Replying is ordinary messaging — it carries no entity share of its own
    # and, crucially, still changes nothing about the issue.
    assert reply.shared_entity_type is None
    db.refresh(world["issue"])
    assert world["issue"].raised_by_id == world["engineer_a"].id
    assert world["issue"].status == IssueStatus.OPEN
