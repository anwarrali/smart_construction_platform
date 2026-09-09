"""Uploaded files must not be reachable without the authorization that reaches the row.

Before this suite existed, four upload categories — documents, attachments,
site-report photos and field evidence — were written into `UPLOAD_DIR` and
served by an unauthenticated `StaticFiles` mount at `/uploads`. Every endpoint
that returned one of them checked permissions properly and then published the
public URL, so the effect of the check was to decide *who learned the address*,
not who could fetch the bytes. `GET /documents/{id}/download` was the clearest
case: it called `assert_document_readable` and returned `{"url": file_url}`.

The properties pinned here are therefore about the bytes, not the metadata:

  * a person entitled to read the row can stream the file;
  * a person on another project cannot, by any route;
  * an unauthenticated caller cannot;
  * the public mount no longer serves any of the four categories, so knowing a
    storage key is worth nothing.

The last one is the regression test that matters. The first three could all pass
while the hole stayed wide open, because they only exercise the endpoint that was
already checking.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.attachment import Attachment
from app.models.company import Company
from app.models.document import Document
from app.models.enums import (
    DocumentType, FieldSubmissionStatus, ProjectStatus, TaskStatus, UserRole, UserStatus,
)
from app.models.field_submission import (
    FieldSubmission, FieldSubmissionPhoto, PhotoCategoryAssignment,
)
from app.models.project import Project, ProjectMember
from app.models.site_report import SiteReport
from app.models.task import Task
from app.models.user import User
from app.services import rbac
from app.services.private_storage import private_storage

PASSWORD = "Correct#12345"
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 64


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
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


def _auth(client, user: User) -> dict:
    login = client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _store(key: str, payload: bytes) -> str:
    with private_storage.writable_local_path(key) as target:
        target.write_bytes(payload)
    return key


@pytest.fixture()
def world(db):
    """Two projects. An insider on the first; an outsider who owns the second.

    The outsider is a full project manager *somewhere*, deliberately: a test
    whose unauthorized caller has no permissions anywhere proves only that
    authentication works. This one holds every permission the insider holds,
    on a different project, so what stops them is project scope alone.
    """
    suffix = uuid.uuid4().hex[:10]
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    role = roles["project_manager"]

    office = Company(name=f"Download Office {suffix}", kind="CONSULTING_OFFICE", is_active=True)
    db.add(office)
    db.flush()

    def person(label: str) -> User:
        user = User(
            full_name=f"{label}{suffix}", email=f"{label.lower()}.{suffix}@constro.io",
            hashed_password=hash_password(PASSWORD), role=UserRole.PROJECT_MANAGER,
            status=UserStatus.ACTIVE, company_id=office.id, org_role_id=role.id,
            is_internal=role.is_internal_only,
        )
        db.add(user)
        db.flush()
        return user

    insider = person("Insider")
    outsider = person("Outsider")

    def project_for(manager: User, name: str) -> Project:
        project = Project(
            name=f"{name} {suffix}", status=ProjectStatus.ACTIVE,
            company_id=office.id, project_manager_id=manager.id,
        )
        db.add(project)
        db.flush()
        db.add(ProjectMember(
            project_id=project.id, user_id=manager.id, role_on_project=manager.role,
            project_role_id=role.id, is_active=True,
        ))
        db.flush()
        return project

    project = project_for(insider, "Guarded")
    other_project = project_for(outsider, "Unrelated")

    task = Task(
        project_id=project.id, name=f"Guarded task {suffix}",
        task_code=f"T-{suffix[:6].upper()}", status=TaskStatus.IN_PROGRESS,
        created_by_id=insider.id,
    )
    db.add(task)
    db.flush()

    # --- one row per category, each with real bytes in private storage ------
    document_key = _store(f"documents/{uuid.uuid4()}_spec.pdf", PDF_BYTES)
    document = Document(
        project_id=project.id, uploaded_by_id=insider.id, title=f"Guarded spec {suffix}",
        document_type=DocumentType.OTHER, storage_key=document_key,
        file_url=f"private://{document_key}", file_size_bytes=len(PDF_BYTES),
        mime_type="application/pdf", version=1,
    )
    db.add(document)

    def attachment_for(entity_type: str, entity_id, category: str) -> Attachment:
        key = _store(f"{category}/{uuid.uuid4()}_photo.jpg", JPEG_BYTES)
        row = Attachment(
            original_filename="photo.jpg", storage_key=key, file_url=f"private://{key}",
            mime_type="image/jpeg", file_size_bytes=len(JPEG_BYTES),
            uploaded_by_id=insider.id, project_id=project.id,
            entity_type=entity_type, entity_id=entity_id,
        )
        db.add(row)
        db.flush()
        return row

    task_attachment = attachment_for("TASK", task.id, "attachments")

    report = SiteReport(
        project_id=project.id, submitted_by_id=insider.id,
        report_date=datetime.date.today(),
    )
    db.add(report)
    db.flush()
    site_photo = attachment_for("SITE_REPORT", report.id, "site-reports")

    submission = FieldSubmission(
        project_id=project.id, task_id=task.id, submitted_by_id=insider.id,
        status=FieldSubmissionStatus.VERIFIED,
    )
    db.add(submission)
    db.flush()
    evidence = attachment_for("FIELD_SUBMISSION", submission.id, "field-evidence")
    db.add(FieldSubmissionPhoto(
        field_submission_id=submission.id, attachment_id=evidence.id,
    ))

    db.commit()

    created = {
        "insider": insider, "outsider": outsider, "project": project,
        "other_project": other_project, "document": document,
        "task_attachment": task_attachment, "site_photo": site_photo,
        "evidence": evidence,
        "keys": [document_key, task_attachment.storage_key,
                 site_photo.storage_key, evidence.storage_key],
    }
    try:
        yield created
    finally:
        # This suite shares the developer database with every other suite, so a
        # fixture that leaks is not a tidiness problem — two project-visibility
        # tests assert against a *paginated* project list, and enough stray
        # projects push their fixtures off the first page. Their failure looked
        # exactly like an authorization regression and was not one.
        #
        # Deleted child-first, in foreign-key order, and by id rather than by a
        # name pattern so a partially-built fixture still cleans up after itself.
        for key in created["keys"]:
            private_storage.delete(key)
        db.rollback()
        db.query(PhotoCategoryAssignment).filter(
            PhotoCategoryAssignment.field_submission_photo_id.in_(
                db.query(FieldSubmissionPhoto.id).filter(
                    FieldSubmissionPhoto.field_submission_id == submission.id
                )
            )
        ).delete(synchronize_session=False)
        db.query(FieldSubmissionPhoto).filter(
            FieldSubmissionPhoto.field_submission_id == submission.id
        ).delete(synchronize_session=False)
        db.query(FieldSubmission).filter(FieldSubmission.id == submission.id).delete(
            synchronize_session=False
        )
        db.query(Attachment).filter(Attachment.project_id == project.id).delete(
            synchronize_session=False
        )
        db.query(Document).filter(Document.project_id == project.id).delete(
            synchronize_session=False
        )
        db.query(SiteReport).filter(SiteReport.id == report.id).delete(
            synchronize_session=False
        )
        db.query(Task).filter(Task.id == task.id).delete(synchronize_session=False)
        project_ids = [project.id, other_project.id]
        db.query(ProjectMember).filter(ProjectMember.project_id.in_(project_ids)).delete(
            synchronize_session=False
        )
        db.query(Project).filter(Project.id.in_(project_ids)).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_([insider.id, outsider.id])).delete(
            synchronize_session=False
        )
        db.query(Company).filter(Company.id == office.id).delete(synchronize_session=False)
        db.commit()


def _urls(world) -> dict[str, str]:
    return {
        "document": f"/api/v1/documents/{world['document'].id}/download",
        "attachment": f"/api/v1/attachments/{world['task_attachment'].id}/download",
        "site photo": f"/api/v1/attachments/{world['site_photo'].id}/download",
        "field evidence": f"/api/v1/attachments/{world['evidence'].id}/download",
    }


# --- the authorized path ----------------------------------------------------

@pytest.mark.parametrize("category", ["document", "attachment", "site photo", "field evidence"])
def test_a_person_on_the_project_receives_the_bytes(client, world, category):
    """The point of securing a download is that the entitled caller still gets it."""
    response = client.get(_urls(world)[category], headers=_auth(client, world["insider"]))
    assert response.status_code == 200, f"{category}: {response.text}"
    assert response.content in (PDF_BYTES, JPEG_BYTES)
    assert "attachment;" in response.headers["content-disposition"]


# --- the unauthorized paths -------------------------------------------------

@pytest.mark.parametrize("category", ["document", "attachment", "site photo", "field evidence"])
def test_a_person_on_another_project_is_refused(client, world, category):
    """Project scope, not permission level, is what refuses them.

    The outsider is a project manager with the full permission set — on their
    own project. Holding `document.view` somewhere must not read a file here.
    """
    response = client.get(_urls(world)[category], headers=_auth(client, world["outsider"]))
    assert response.status_code in (403, 404), (
        f"{category}: an unrelated project manager received {response.status_code}"
    )
    assert PDF_BYTES not in response.content
    assert JPEG_BYTES not in response.content


@pytest.mark.parametrize("category", ["document", "attachment", "site photo", "field evidence"])
def test_an_unauthenticated_caller_is_refused(client, world, category):
    response = client.get(_urls(world)[category])
    assert response.status_code in (401, 403), f"{category}: {response.status_code}"


# --- the hole itself --------------------------------------------------------

@pytest.mark.parametrize("category", ["document", "attachment", "site photo", "field evidence"])
def test_the_public_mount_no_longer_serves_the_file(client, world, category):
    """Knowing the storage key must be worth nothing.

    This is the regression that the endpoint tests above cannot catch. The old
    failure was not a missing check on the download route — that check was
    there. It was that the bytes were *also* available at a second address that
    had no check at all, and the route handed that address out.
    """
    key = {
        "document": world["document"].storage_key,
        "attachment": world["task_attachment"].storage_key,
        "site photo": world["site_photo"].storage_key,
        "field evidence": world["evidence"].storage_key,
    }[category]
    response = client.get(f"/uploads/{key}")
    assert response.status_code == 404, (
        f"{category}: /uploads/{key} answered {response.status_code}; the public "
        "mount is serving a category it must not."
    )


def test_the_download_response_never_carries_a_public_url(client, world):
    """A list response must not publish a fetchable location either.

    `AttachmentOut` used to expose `fileUrl` and `storageKey`, and `DocumentOut`
    exposed `fileUrl`. Every list endpoint therefore handed out the bypass to
    anybody authorized to see the metadata once.
    """
    headers = _auth(client, world["insider"])
    documents = client.get(
        f"/api/v1/documents?project_id={world['project'].id}", headers=headers
    )
    assert documents.status_code == 200, documents.text
    for item in documents.json():
        assert "fileUrl" not in item, "DocumentOut still publishes a public URL"
        assert item["downloadUrl"].startswith("/api/v1/documents/")

    attachments = client.get(
        f"/api/v1/attachments?project_id={world['project'].id}", headers=headers
    )
    assert attachments.status_code == 200, attachments.text
    for item in attachments.json():
        assert "fileUrl" not in item, "AttachmentOut still publishes a public URL"
        assert "storageKey" not in item, "AttachmentOut still discloses the storage layout"
        assert item["downloadUrl"].startswith("/api/v1/attachments/")


def test_a_document_with_no_storage_key_is_refused_rather_than_served_publicly(client, world, db):
    """An unmigrated row must fail closed.

    The tempting fallback — "no storage key, so serve `file_url`" — would
    reinstate the vulnerability for precisely the rows that predate the fix.
    """
    document = db.get(Document, world["document"].id)
    document.storage_key = None
    document.file_url = "http://localhost:8000/uploads/documents/legacy.pdf"
    db.commit()

    response = client.get(
        f"/api/v1/documents/{document.id}/download", headers=_auth(client, world["insider"])
    )
    assert response.status_code == 409
    assert "uploads" not in response.text
