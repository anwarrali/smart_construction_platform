"""The Manager Site Report verification workflow (approve / reject).

Mirrors the shape of `test_authorization_migrated_endpoints.py`: real DB rows,
the router's own endpoint function called directly (exactly as a crafted HTTP
request would reach it), and an explicit teardown since the endpoint commits.
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.site_reports import review_site_report
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.notification import Notification
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.site_report import SiteReport
from app.models.user import User
from app.schemas.site_report import SiteReportReviewRequest


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

    def user(name, role, status=UserStatus.ACTIVE):
        person = User(full_name=name, email=f"{name.lower()}-{suffix}@test.local",
                      hashed_password="x", role=role, status=status)
        db.add(person)
        return person

    people = {
        "admin": user("SrvAdmin", UserRole.ADMIN),
        "manager": user("SrvPm", UserRole.PROJECT_MANAGER),
        "other_manager": user("SrvOtherPm", UserRole.PROJECT_MANAGER),
        "engineer": user("SrvEngineer", UserRole.ENGINEER),
        "worker": user("SrvWorker", UserRole.WORKER),
        "submitter": user("SrvSubmitter", UserRole.ENGINEER),
    }
    db.flush()

    project = Project(name=f"Verification Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["manager"].id, project_manager_id=people["manager"].id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=people["submitter"].id,
                         role_on_project=UserRole.ENGINEER, is_active=True))
    db.flush()
    people["project"] = project

    def report(status="submitted"):
        item = SiteReport(project_id=project.id, submitted_by_id=people["submitter"].id,
                          report_date=date.today(), summary_text="Poured slab on grid B",
                          review_status=status)
        db.add(item)
        db.flush()
        return item

    people["report"] = report
    people["db"] = db
    yield people
    _purge(db, [project.id], [person.id for person in people.values() if isinstance(person, User)])


def _purge(db, project_ids, user_ids):
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM user_permission_overrides WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM site_reports WHERE project_id = ANY(:projects)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), params)
    db.commit()


# --- happy path --------------------------------------------------------------

def test_the_assigned_manager_can_verify_a_submitted_report(db, world):
    report = world["report"]()
    result = review_site_report(report.id, SiteReportReviewRequest(approved=True),
                                db=db, current_user=world["manager"])
    assert result.review_status == "approved"
    assert result.reviewed_by_id == world["manager"].id
    assert result.reviewed_at is not None
    assert result.rejection_reason is None

    notified = db.query(Notification).filter(
        Notification.user_id == world["submitter"].id,
        Notification.related_entity_id == report.id,
    ).first()
    assert notified is not None
    assert "verified" in notified.title.lower()

    audit = db.query(AuditLog).filter(
        AuditLog.entity_type == "site_report", AuditLog.entity_id == report.id,
    ).first()
    assert audit is not None
    assert audit.action == "site_report_verified"
    assert audit.actor_id == world["manager"].id


def test_the_assigned_manager_can_reject_with_a_reason(db, world):
    report = world["report"]()
    result = review_site_report(
        report.id, SiteReportReviewRequest(approved=False, rejection_reason="Missing rebar photos"),
        db=db, current_user=world["manager"],
    )
    assert result.review_status == "rejected"
    assert result.rejection_reason == "Missing rebar photos"

    notified = db.query(Notification).filter(
        Notification.user_id == world["submitter"].id,
        Notification.related_entity_id == report.id,
    ).first()
    assert notified is not None
    assert "rejected" in notified.title.lower()
    assert "Missing rebar photos" in notified.message

    audit = db.query(AuditLog).filter(
        AuditLog.entity_type == "site_report", AuditLog.entity_id == report.id,
    ).first()
    assert audit.action == "site_report_rejected"


def test_rejecting_without_a_reason_is_rejected(db, world):
    report = world["report"]()
    with pytest.raises(HTTPException) as error:
        review_site_report(report.id, SiteReportReviewRequest(approved=False),
                           db=db, current_user=world["manager"])
    assert error.value.status_code == 400
    db.refresh(report)
    assert report.review_status == "submitted"


# --- permission enforcement ---------------------------------------------------

def test_a_manager_cannot_verify_a_report_on_someone_elses_project(db, world):
    report = world["report"]()
    with pytest.raises(HTTPException) as error:
        review_site_report(report.id, SiteReportReviewRequest(approved=True),
                           db=db, current_user=world["other_manager"])
    assert error.value.status_code == 403
    db.refresh(report)
    assert report.review_status == "submitted"


def test_an_engineer_cannot_call_the_verification_endpoint_directly(db, world):
    """Hiding the button is not the protection — this calls the endpoint exactly
    as a crafted HTTP request would, bypassing any UI restriction entirely."""
    report = world["report"]()
    with pytest.raises(HTTPException) as error:
        review_site_report(report.id, SiteReportReviewRequest(approved=True),
                           db=db, current_user=world["engineer"])
    assert error.value.status_code == 403


def test_a_worker_cannot_call_the_verification_endpoint_directly(db, world):
    report = world["report"]()
    with pytest.raises(HTTPException) as error:
        review_site_report(report.id, SiteReportReviewRequest(approved=True),
                           db=db, current_user=world["worker"])
    assert error.value.status_code == 403


def test_the_report_author_cannot_self_verify_without_being_the_manager(db, world):
    report = world["report"]()
    with pytest.raises(HTTPException) as error:
        review_site_report(report.id, SiteReportReviewRequest(approved=True),
                           db=db, current_user=world["submitter"])
    assert error.value.status_code == 403


def test_an_administrator_needs_an_explicit_grant_to_verify(db, world):
    report = world["report"]()
    with pytest.raises(HTTPException) as error:
        review_site_report(report.id, SiteReportReviewRequest(approved=True),
                           db=db, current_user=world["admin"])
    assert error.value.status_code == 403

    db.add(UserPermissionOverride(user_id=world["admin"].id, permission_code="site_report.verify", allowed=True))
    db.flush()
    result = review_site_report(report.id, SiteReportReviewRequest(approved=True),
                                db=db, current_user=world["admin"])
    assert result.review_status == "approved"


# --- state transitions ---------------------------------------------------------

def test_a_draft_report_cannot_be_verified(db, world):
    report = world["report"](status="draft")
    with pytest.raises(HTTPException) as error:
        review_site_report(report.id, SiteReportReviewRequest(approved=True),
                           db=db, current_user=world["manager"])
    assert error.value.status_code == 409


def test_an_already_approved_report_cannot_be_reviewed_again(db, world):
    report = world["report"](status="approved")
    with pytest.raises(HTTPException) as error:
        review_site_report(report.id, SiteReportReviewRequest(approved=False, rejection_reason="changed my mind"),
                           db=db, current_user=world["manager"])
    assert error.value.status_code == 409


def test_verifying_an_unknown_report_is_a_404(db, world):
    with pytest.raises(HTTPException) as error:
        review_site_report(uuid4(), SiteReportReviewRequest(approved=True),
                           db=db, current_user=world["manager"])
    assert error.value.status_code == 404
