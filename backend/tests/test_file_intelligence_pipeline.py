"""Upload → identify → classify → store, through the real documents endpoint.

`tests/test_file_intelligence.py` pins the rules in isolation. This checks the
wiring: that a document uploaded the way the application actually uploads one
comes back carrying what the file turned out to be, and that the uploader's own
choice is still the one stored as authoritative.
"""

import asyncio
import io
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.documents import upload_document
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.document import Document
from app.models.enums import DocumentType, ProjectStatus, UserRole, UserStatus
from app.models.project import Project, ProjectMember
from app.models.user import User
from tests.pdf_fixture import build_pdf


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
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    (tmp_path / "uploads").mkdir()

    # example.com rather than .test.local: DocumentOut nests UserOut, whose
    # EmailStr rejects reserved TLDs, and this suite serialises the response.
    manager = User(full_name="DocPm", email=f"docpm-{suffix}@example.com", hashed_password="x",
                   role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    owner = User(full_name="DocOwner", email=f"docowner-{suffix}@example.com", hashed_password="x",
                 role=UserRole.OWNER, status=UserStatus.ACTIVE)
    db.add_all([manager, owner])
    db.flush()
    project = Project(name=f"Docs {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=manager.id,
                         role_on_project=UserRole.PROJECT_MANAGER, is_active=True))
    db.commit()
    try:
        yield {"project": project, "manager": manager, "tmp": tmp_path}
    finally:
        _purge(db, project.id, [manager.id, owner.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    params = {"projects": [project_id], "users": list(user_ids)}
    for statement in (
        "DELETE FROM document_chunks WHERE document_id IN (SELECT id FROM documents WHERE project_id = ANY(:projects))",
        "DELETE FROM documents WHERE project_id = ANY(:projects)",
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


def _upload(db, world, *, filename: str, content: bytes, mime: str,
            declared: str | None = None, title: str = "Uploaded file") -> Document:
    upload = UploadFile(filename=filename, file=io.BytesIO(content),
                        headers={"content-type": mime})
    return asyncio.run(upload_document(
        file=upload, project_id=str(world["project"].id), title=title,
        document_type=declared, task_id=None, notes=None,
        db=db, current_user=world["manager"],
    ))


def _pdf(world, pages: list[str]) -> bytes:
    path = build_pdf(world["tmp"] / f"{uuid4().hex}.pdf", pages)
    return path.read_bytes()


def test_a_bill_of_quantities_is_recognised_from_its_own_first_page(db, world):
    content = _pdf(world, ["BILL OF QUANTITIES", "Item 1 Concrete"])
    document = _upload(db, world, filename="scan_0031.pdf", content=content,
                       mime="application/pdf", declared="other")
    assert document.detected_format == "PDF"
    assert document.suggested_document_type == "BOQ"
    assert document.classification_json["source"] == "CONTENT"
    assert document.classification_json["evidence"] == "bill of quantities"


def test_the_uploaders_choice_remains_the_stored_type(db, world):
    """Advisory means advisory. Classification never rewrites the record."""
    content = _pdf(world, ["BILL OF QUANTITIES"])
    document = _upload(db, world, filename="x.pdf", content=content,
                       mime="application/pdf", declared="contract")
    assert document.document_type == DocumentType.CONTRACT
    assert document.suggested_document_type == "BOQ"
    assert document.classification_json["disagreesWithDeclared"] is True


def test_a_document_the_classifier_cannot_place_is_left_as_other(db, world):
    content = _pdf(world, ["Page 1 of 2", "continued"])
    document = _upload(db, world, filename="scan_0002.pdf", content=content,
                       mime="application/pdf", declared="other")
    assert document.suggested_document_type == "OTHER"
    assert document.classification_json["evidence"] is None
    assert document.classification_json["confidence"] <= 0.2


def test_the_filename_carries_the_classification_when_the_pdf_says_nothing(db, world):
    content = _pdf(world, ["", "1"])
    document = _upload(db, world, filename="Construction Programme Rev C.pdf",
                       content=content, mime="application/pdf", declared="other")
    assert document.suggested_document_type == "SCHEDULE"
    assert document.classification_json["source"] == "FILENAME"


def test_the_new_document_kinds_can_actually_be_stored(db, world):
    """The enum migration, exercised rather than assumed."""
    for declared, expected in (("boq", DocumentType.BOQ), ("schedule", DocumentType.SCHEDULE),
                               ("technical", DocumentType.TECHNICAL)):
        document = _upload(db, world, filename=f"{declared}.pdf", content=_pdf(world, ["x"]),
                           mime="application/pdf", declared=declared)
        assert document.document_type == expected


def test_a_dwg_is_stored_and_recognised_as_a_drawing(db, world):
    document = _upload(db, world, filename="GA Plan.dwg", content=b"AC1027" + b"\x00" * 512,
                       mime="application/octet-stream", declared="other")
    assert document.detected_format == "DWG"
    assert document.suggested_document_type == "DRAWING"
    assert document.classification_json["source"] == "FORMAT"


def test_classification_failure_never_blocks_an_upload(db, world, monkeypatch):
    """A missing second opinion is not a reason to reject submitted work."""
    def explode(*_args, **_kwargs):
        raise RuntimeError("classifier unavailable")

    monkeypatch.setattr("app.api.documents.classify_document", explode)
    document = _upload(db, world, filename="notes.pdf", content=_pdf(world, ["hello"]),
                       mime="application/pdf", declared="report")
    assert document.id
    assert document.document_type == DocumentType.REPORT
    assert document.suggested_document_type is None
    assert document.classification_json == {}


def test_an_existing_document_without_classification_still_serialises(db, world):
    """Rows written before this existed must keep working, not blow up a list."""
    from app.schemas.document import DocumentOut

    document = _upload(db, world, filename="x.pdf", content=_pdf(world, ["y"]),
                       mime="application/pdf", declared="report")
    document.detected_format = None
    document.suggested_document_type = None
    document.classification_json = {}
    db.commit()
    payload = DocumentOut.model_validate(document, from_attributes=True)
    assert payload.detected_format is None
    assert payload.classification_json == {}


def test_a_file_lying_about_its_extension_is_still_refused(db, world):
    """The upload gate is unchanged by classification being added behind it."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as failure:
        _upload(db, world, filename="malicious.pdf", content=b"<script>alert(1)</script>",
                mime="application/pdf", declared="other")
    assert failure.value.status_code == 415
