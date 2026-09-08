"""The pipeline end to end, through the real endpoints and the real database.

`test_ingestion_classification.py` and `test_ingestion_archives.py` pin the
rules in isolation. This checks the wiring: that a file uploaded the way the
application actually uploads one is stored, classified, processed, settled and
readable, and that every refusal reaches the caller as the right status code.

Storage is redirected to a temporary directory, and background processing is
switched off so an upload settles before the call returns — the assertions are
about *what* the pipeline produces, not about when.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import ingestion as ingestion_api
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.ingestion import IngestedFile, IngestionJob
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.ingestion import state
from app.services.ingestion.categories import FileCategory
from tests.pdf_fixture import build_pdf

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
DWG = b"AC1027" + b"\x00" * 64
IFC_SOURCE = (
    b"ISO-10303-21;\nHEADER;\n"
    b"FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');\n"
    b"FILE_NAME('tower.ifc','2026-01-01T00:00:00',(''),(''),"
    b"'IfcOpenShell 0.8','Revit 2025','');\n"
    b"FILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
)


# --- World ------------------------------------------------------------------

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
    private = tmp_path / "private"
    private.mkdir()
    # `monkeypatch.setenv` as well as `setattr`: a spawned child re-imports
    # `app.core.config` and would otherwise look in the default directory.
    monkeypatch.setattr(settings, "PRIVATE_UPLOAD_DIR", str(private))
    monkeypatch.setenv("PRIVATE_UPLOAD_DIR", str(private))
    monkeypatch.setattr(settings, "INGESTION_ENABLED", True)
    monkeypatch.setattr(settings, "INGESTION_BACKGROUND_PROCESSING_ENABLED", False)

    manager = User(full_name="IngestPm", email=f"ingestpm-{suffix}@example.com",
                   hashed_password="x", role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    outsider = User(full_name="IngestOther", email=f"ingestother-{suffix}@example.com",
                    hashed_password="x", role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    owner = User(full_name="IngestOwner", email=f"ingestowner-{suffix}@example.com",
                 hashed_password="x", role=UserRole.OWNER, status=UserStatus.ACTIVE)
    db.add_all([manager, outsider, owner])
    db.flush()

    project = Project(name=f"Ingest {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    other_project = Project(name=f"Ingest other {suffix}", status=ProjectStatus.ACTIVE,
                            owner_id=owner.id, project_manager_id=outsider.id)
    db.add_all([project, other_project])
    db.flush()
    db.add_all([
        ProjectMember(project_id=project.id, user_id=manager.id,
                      role_on_project=UserRole.PROJECT_MANAGER, is_active=True),
        ProjectMember(project_id=other_project.id, user_id=outsider.id,
                      role_on_project=UserRole.PROJECT_MANAGER, is_active=True),
    ])
    db.commit()
    try:
        yield {"project": project, "other_project": other_project, "manager": manager,
               "outsider": outsider, "owner": owner, "tmp": tmp_path}
    finally:
        _purge(db, [project.id, other_project.id],
               [manager.id, outsider.id, owner.id])


def _purge(db, project_ids, user_ids):
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM ingestion_jobs WHERE file_id IN "
        "(SELECT id FROM ingested_files WHERE project_id = ANY(:projects))",
        "UPDATE ingested_files SET parent_file_id = NULL, duplicate_of_id = NULL "
        "WHERE project_id = ANY(:projects)",
        "DELETE FROM ingested_files WHERE project_id = ANY(:projects)",
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


def upload(db, world, *, filename, content, mime, project=None, user=None):
    from fastapi import UploadFile

    handle = UploadFile(filename=filename, file=io.BytesIO(content),
                        headers={"content-type": mime})
    return asyncio.run(ingestion_api.ingest_file(
        project_id=(project or world["project"]).id,
        background_tasks=BackgroundTasks(),
        file=handle,
        db=db,
        current_user=user or world["manager"],
    ))


def _drain(response) -> bytes:
    """Collect a StreamingResponse's body.

    Starlette wraps a sync generator in `iterate_in_threadpool`, so
    `body_iterator` is an *async* iterator even though the endpoint yields
    synchronously.
    """

    async def collect():
        return b"".join([chunk async for chunk in response.body_iterator])

    return asyncio.run(collect())


def pdf_bytes(world, pages):
    return build_pdf(world["tmp"] / f"{uuid4().hex}.pdf", pages).read_bytes()


def zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return buffer.getvalue()


def docx_bytes(paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml",
                         f'<?xml version="1.0"?><w:document><w:body>{body}</w:body></w:document>')
    return buffer.getvalue()


def xlsx_bytes(sheets):
    entries = "".join(
        f'<sheet name="{name}" sheetId="{index + 1}" r:id="rId{index + 1}"/>'
        for index, name in enumerate(sheets)
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml",
                         f'<?xml version="1.0"?><workbook><sheets>{entries}</sheets></workbook>')
    return buffer.getvalue()


# --- The happy path ---------------------------------------------------------

def test_a_pdf_is_stored_classified_and_processed_to_ready(db, world):
    result = upload(db, world, filename="specification.pdf",
                    content=pdf_bytes(world, ["TECHNICAL SPECIFICATION", "Section 2"]),
                    mime="application/pdf")
    assert result.status == state.READY
    assert result.file_category == FileCategory.PDF.value
    assert result.detected_format == "PDF"
    assert result.document_kind == "SPECIFICATION"
    assert result.processor_name == "pdf"
    assert result.metadata_json["details"]["pageCount"] == 2
    assert result.metadata_json["details"]["hasTextLayer"] is True
    assert result.metadata_json["extraction"] == "TEXT"
    assert result.error is None
    assert result.checksum_sha256


def test_the_response_never_carries_the_storage_key(db, world):
    result = upload(db, world, filename="plan.pdf", content=pdf_bytes(world, ["Plan"]),
                    mime="application/pdf")
    assert "storage_key" not in result.model_dump()
    assert "storageKey" not in result.model_dump(by_alias=True)


def test_a_word_document_gives_up_its_body_text(db, world):
    result = upload(db, world, filename="method-statement.docx",
                    content=docx_bytes(["METHOD STATEMENT", "Concrete pour sequence"]),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert result.status == state.READY
    assert result.file_category == FileCategory.DOCX.value
    assert "Concrete pour sequence" in result.metadata_json["details"]["textSample"]


def test_a_workbook_gives_up_its_sheet_names_and_says_the_cells_were_not_read(db, world):
    result = upload(db, world, filename="boq.xlsx", content=xlsx_bytes(["Summary", "Concrete"]),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    # PARTIAL on purpose: the quantities were not read, and calling this READY
    # would tell somebody their BOQ had been understood.
    assert result.status == state.PARTIAL
    assert result.metadata_json["details"]["sheetNames"] == ["Summary", "Concrete"]
    assert result.error["code"] == "FORMAT_NOT_PARSED"
    assert result.error["retryable"] is False


def test_a_scanned_pdf_is_partial_with_a_reason_rather_than_failed(db, world):
    result = upload(db, world, filename="scan.pdf", content=pdf_bytes(world, [""]),
                    mime="application/pdf")
    assert result.status == state.PARTIAL
    assert result.error["code"] == "NO_TEXT_LAYER"
    assert result.metadata_json["details"]["hasTextLayer"] is False


def test_an_image_is_ready_because_nothing_was_promised_about_it(db, world):
    result = upload(db, world, filename="site.png", content=PNG, mime="image/png")
    assert result.status == state.READY
    assert result.metadata_json["extraction"] == "NONE"


def test_a_drawing_is_stored_and_declared_unparsed(db, world):
    result = upload(db, world, filename="ground-floor.dwg", content=DWG,
                    mime="application/octet-stream")
    assert result.file_category == FileCategory.DRAWING.value
    assert result.document_kind == "DRAWING"
    assert result.status == state.PARTIAL
    assert result.error["code"] == "FORMAT_NOT_PARSED"


def test_a_standalone_ifc_reads_its_header_and_points_at_the_ifc_workspace(db, world):
    result = upload(db, world, filename="tower.ifc", content=IFC_SOURCE,
                    mime="application/octet-stream")
    assert result.file_category == FileCategory.IFC.value
    assert result.metadata_json["details"]["ifcSchema"] == "IFC4"
    assert result.metadata_json["details"]["authoringApplication"] == "Revit 2025"
    assert result.status == state.PARTIAL
    assert "IFC" in result.metadata_json["details"]["nextStep"]


# --- Refusals ---------------------------------------------------------------

def test_an_unsupported_type_is_refused_with_415_and_stores_nothing(db, world):
    before = db.query(IngestedFile).count()
    with pytest.raises(HTTPException) as refusal:
        upload(db, world, filename="setup.exe", content=b"MZ\x90\x00" + b"\x00" * 64,
               mime="application/octet-stream")
    assert refusal.value.status_code == 415
    db.rollback()
    assert db.query(IngestedFile).count() == before


def test_a_renamed_executable_is_refused_on_its_bytes(db, world):
    with pytest.raises(HTTPException) as refusal:
        upload(db, world, filename="invoice.pdf", content=b"MZ\x90\x00" + b"\x00" * 64,
               mime="application/pdf")
    assert refusal.value.status_code == 415


def test_an_empty_upload_is_refused(db, world):
    with pytest.raises(HTTPException) as refusal:
        upload(db, world, filename="nothing.pdf", content=b"", mime="application/pdf")
    assert refusal.value.status_code == 400


def test_an_oversized_upload_is_refused_with_413(db, world, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_MAX_FILE_MB", 1)
    payload = pdf_bytes(world, ["x"]) + b"\x00" * (2 * 1024 * 1024)
    with pytest.raises(HTTPException) as refusal:
        upload(db, world, filename="huge.pdf", content=payload, mime="application/pdf")
    assert refusal.value.status_code == 413


def test_the_feature_flag_closes_the_endpoint(db, world, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_ENABLED", False)
    with pytest.raises(HTTPException) as refusal:
        upload(db, world, filename="a.pdf", content=pdf_bytes(world, ["a"]),
               mime="application/pdf")
    assert refusal.value.status_code == 503


# --- Project isolation ------------------------------------------------------

def test_a_stranger_cannot_upload_into_a_project(db, world):
    with pytest.raises(HTTPException) as refusal:
        upload(db, world, filename="a.pdf", content=pdf_bytes(world, ["a"]),
               mime="application/pdf", user=world["outsider"])
    assert refusal.value.status_code == 403


def test_a_stranger_cannot_list_a_projects_files(db, world):
    with pytest.raises(HTTPException) as refusal:
        ingestion_api.list_files(
            project_id=world["project"].id, category=None, status=None, parent_id=None,
            root_only=False, limit=50, offset=0, db=db, current_user=world["outsider"],
        )
    assert refusal.value.status_code == 403


def test_a_file_cannot_be_read_through_another_projects_route(db, world):
    """Membership of both projects must not make one project's file readable
    through the other's URL — the check is the row's project, not the caller's."""
    mine = upload(db, world, filename="mine.pdf", content=pdf_bytes(world, ["mine"]),
                  mime="application/pdf")
    db.add(ProjectMember(project_id=world["other_project"].id, user_id=world["manager"].id,
                         role_on_project=UserRole.PROJECT_MANAGER, is_active=True))
    db.commit()
    with pytest.raises(HTTPException) as refusal:
        ingestion_api.get_file(project_id=world["other_project"].id, file_id=mine.id,
                               db=db, current_user=world["manager"])
    assert refusal.value.status_code == 404


def test_listing_returns_only_this_projects_files(db, world):
    upload(db, world, filename="ours.pdf", content=pdf_bytes(world, ["ours"]),
           mime="application/pdf")
    upload(db, world, filename="theirs.pdf", content=pdf_bytes(world, ["theirs"]),
           mime="application/pdf", project=world["other_project"], user=world["outsider"])
    page = ingestion_api.list_files(
        project_id=world["project"].id, category=None, status=None, parent_id=None,
        root_only=False, limit=50, offset=0, db=db, current_user=world["manager"],
    )
    assert [item.original_filename for item in page.items] == ["ours.pdf"]
    assert page.total == 1


# --- Packages ---------------------------------------------------------------

def test_a_design_package_becomes_one_registered_file_per_member(db, world):
    payload = zip_bytes([
        ("ARCH/plan-01.pdf", pdf_bytes(world, ["GENERAL ARRANGEMENT"])),
        ("SPEC/specification.pdf", pdf_bytes(world, ["TECHNICAL SPECIFICATION"])),
        ("BOQ/quantities.xlsx", xlsx_bytes(["Bill"])),
    ])
    package = upload(db, world, filename="rev-c.zip", content=payload,
                     mime="application/zip")
    assert package.file_category == FileCategory.ZIP_PACKAGE.value
    assert package.status == state.READY
    assert package.metadata_json["details"]["registeredCount"] == 3

    children = ingestion_api.list_files(
        project_id=world["project"].id, category=None, status=None,
        parent_id=package.id, root_only=False, limit=50, offset=0,
        db=db, current_user=world["manager"],
    )
    assert children.total == 3
    kinds = {item.original_filename: item.document_kind for item in children.items}
    assert kinds["specification.pdf"] == "SPECIFICATION"
    assert {item.file_category for item in children.items} == {"PDF", "XLSX"}


def test_a_package_member_records_where_in_the_package_it_came_from(db, world):
    payload = zip_bytes([("ARCH/GF/plan-01.pdf", pdf_bytes(world, ["Plan"]))])
    package = upload(db, world, filename="p.zip", content=payload, mime="application/zip")
    child = db.query(IngestedFile).filter(IngestedFile.parent_file_id == package.id).one()
    assert child.classification_json["packagePath"] == "ARCH/GF/plan-01.pdf"


def test_a_hostile_package_fails_and_registers_none_of_its_members(db, world):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ARCH/plan.pdf", pdf_bytes(world, ["Plan"]))
        info = zipfile.ZipInfo()
        info.filename = "../../escape.pdf"
        archive.writestr(info, b"%PDF-1.7\n")
    package = upload(db, world, filename="hostile.zip", content=buffer.getvalue(),
                     mime="application/zip")
    assert package.status == state.FAILED
    assert package.error["code"] == "ARCHIVE_UNSAFE_ENTRY"
    assert db.query(IngestedFile).filter(
        IngestedFile.parent_file_id == package.id).count() == 0


def test_a_package_member_that_is_not_an_accepted_type_is_dropped_and_recorded(db, world):
    payload = zip_bytes([
        ("ARCH/plan.pdf", pdf_bytes(world, ["Plan"])),
        ("tools/setup.exe", b"MZ\x90\x00" + b"\x00" * 64),
    ])
    package = upload(db, world, filename="mixed.zip", content=payload, mime="application/zip")
    assert package.status == state.PARTIAL
    skipped = {item["name"]: item["reason"] for item in package.metadata_json["details"]["skipped"]}
    assert skipped["tools/setup.exe"] == "UNSUPPORTED_FILE_TYPE"
    assert package.metadata_json["details"]["registeredCount"] == 1


def test_an_archive_inside_a_package_is_stored_but_not_expanded(db, world):
    inner = zip_bytes([("deep.pdf", pdf_bytes(world, ["Deep"]))])
    payload = zip_bytes([("nested.zip", inner)])
    package = upload(db, world, filename="outer.zip", content=payload, mime="application/zip")
    child = db.query(IngestedFile).filter(IngestedFile.parent_file_id == package.id).one()
    assert child.file_category == FileCategory.ZIP_PACKAGE.value
    assert child.status == state.PARTIAL
    assert child.error_code == "ARCHIVE_NESTING_LIMIT"
    # The grandchild was never registered: nothing has `child` as a parent.
    assert db.query(IngestedFile).filter(IngestedFile.parent_file_id == child.id).count() == 0


def test_a_zip_bomb_fails_the_package(db, world, monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_ZIP_MAX_RATIO", 10)
    payload = zip_bytes([("bomb.txt", b"\x00" * (2 * 1024 * 1024))])
    package = upload(db, world, filename="bomb.zip", content=payload, mime="application/zip")
    assert package.status == state.FAILED
    assert package.error["code"] == "ARCHIVE_EXPANSION_LIMIT"


# --- Duplicates, jobs and retries -------------------------------------------

def test_identical_bytes_are_recorded_as_a_duplicate_rather_than_refused(db, world):
    content = pdf_bytes(world, ["DRAWING REGISTER"])
    first = upload(db, world, filename="register.pdf", content=content, mime="application/pdf")
    second = upload(db, world, filename="register-copy.pdf", content=content,
                    mime="application/pdf")
    assert second.duplicate_of_id == first.id
    assert first.duplicate_of_id is None
    # Both are real files with their own storage, because a package
    # legitimately ships the same sheet twice.
    assert second.id != first.id
    assert second.status == state.READY


def test_a_duplicate_chain_always_points_at_the_original(db, world):
    content = pdf_bytes(world, ["A"])
    first = upload(db, world, filename="a.pdf", content=content, mime="application/pdf")
    upload(db, world, filename="b.pdf", content=content, mime="application/pdf")
    third = upload(db, world, filename="c.pdf", content=content, mime="application/pdf")
    assert third.duplicate_of_id == first.id


def test_the_same_bytes_in_two_projects_are_not_duplicates_of_each_other(db, world):
    content = pdf_bytes(world, ["Shared"])
    upload(db, world, filename="a.pdf", content=content, mime="application/pdf")
    theirs = upload(db, world, filename="a.pdf", content=content, mime="application/pdf",
                    project=world["other_project"], user=world["outsider"])
    assert theirs.duplicate_of_id is None


def test_processing_records_a_job_with_timing(db, world):
    result = upload(db, world, filename="a.pdf", content=pdf_bytes(world, ["A"]),
                    mime="application/pdf")
    job = db.query(IngestionJob).filter(IngestionJob.file_id == result.id).one()
    assert job.status == "COMPLETED"
    assert job.attempt == 1
    assert job.duration_ms is not None
    assert job.failure_code is None


def test_a_retry_reuses_the_job_row_and_counts_the_attempt(db, world):
    result = upload(db, world, filename="scan.pdf", content=pdf_bytes(world, [""]),
                    mime="application/pdf")
    assert result.status == state.PARTIAL
    retried = ingestion_api.retry_file(
        project_id=world["project"].id, file_id=result.id,
        background_tasks=BackgroundTasks(), db=db, current_user=world["manager"],
    )
    assert retried.queued is False
    assert retried.file.status == state.PARTIAL
    job = db.query(IngestionJob).filter(IngestionJob.file_id == result.id).one()
    assert job.attempt == 2


def test_a_stranger_cannot_retry(db, world):
    result = upload(db, world, filename="a.pdf", content=pdf_bytes(world, ["A"]),
                    mime="application/pdf")
    with pytest.raises(HTTPException) as refusal:
        ingestion_api.retry_file(
            project_id=world["project"].id, file_id=result.id,
            background_tasks=BackgroundTasks(), db=db, current_user=world["outsider"],
        )
    assert refusal.value.status_code == 403


# --- Failure paths ----------------------------------------------------------

def test_a_processor_that_raises_leaves_the_file_failed_and_not_stuck(db, world, monkeypatch):
    from app.services.ingestion import pipeline

    class Exploding:
        name = "exploding"

        def process(self, context):
            raise RuntimeError("secret internal path /srv/private/uploads/x")

    monkeypatch.setattr(pipeline.registry, "select", lambda file: Exploding())
    result = upload(db, world, filename="a.pdf", content=pdf_bytes(world, ["A"]),
                    mime="application/pdf")
    assert result.status == state.FAILED
    assert result.error["code"] == "PROCESSING_FAILED"
    # The internal detail is kept on the row for operators and never published.
    row = db.get(IngestedFile, result.id)
    assert "/srv/private/uploads/x" in row.error_message
    assert "/srv/private" not in str(result.error)


def test_a_failed_file_can_be_retried_back_to_ready(db, world, monkeypatch):
    """A transient failure is recoverable, and the retry clears the error.

    The processor fails once and then behaves, rather than being unpatched
    half-way: `monkeypatch.undo()` would also revert the fixture's storage
    redirection, and the test would then pass or fail for the wrong reason.
    """
    from app.services.ingestion import pipeline

    real_select = pipeline.registry.select
    state_flag = {"fail": True}

    class Flaky:
        name = "flaky"

        def process(self, context):
            raise RuntimeError("transient")

    monkeypatch.setattr(
        pipeline.registry, "select",
        lambda file: Flaky() if state_flag["fail"] else real_select(file),
    )
    result = upload(db, world, filename="a.pdf", content=pdf_bytes(world, ["A"]),
                    mime="application/pdf")
    assert result.status == state.FAILED
    assert result.error["code"] == "PROCESSING_FAILED"

    state_flag["fail"] = False
    retried = ingestion_api.retry_file(
        project_id=world["project"].id, file_id=result.id,
        background_tasks=BackgroundTasks(), db=db, current_user=world["manager"],
    )
    assert retried.file.status == state.READY
    assert retried.file.error is None


# --- Constraints and downloads ----------------------------------------------

def test_upload_constraints_tell_a_client_what_the_server_will_enforce(db, world):
    constraints = ingestion_api.upload_constraints(
        project_id=world["project"].id, db=db, current_user=world["manager"],
    )
    assert constraints.max_file_mb == settings.INGESTION_MAX_FILE_MB
    assert ".zip" in constraints.accepted_extensions
    assert constraints.max_package_depth == settings.INGESTION_ZIP_MAX_DEPTH


def test_a_download_streams_the_bytes_back_without_revealing_where_they_live(db, world):
    content = pdf_bytes(world, ["DOWNLOADABLE"])
    result = upload(db, world, filename="plan.pdf", content=content, mime="application/pdf")
    response = ingestion_api.download_file(
        project_id=world["project"].id, file_id=result.id,
        db=db, current_user=world["manager"],
    )
    assert response.headers["content-disposition"] == 'attachment; filename="plan.pdf"'
    # Always octet-stream, never the file's own type: serving a caller-supplied
    # content type is how a stored HTML or SVG file becomes stored XSS on the
    # API's own origin.
    assert response.media_type == "application/octet-stream"
    assert _drain(response) == content


def test_a_download_filename_cannot_inject_a_header(db, world):
    """A carriage return in a filename would otherwise let an uploader append
    headers of their choosing to every download of that file."""
    result = upload(db, world, filename='ev"il\r\nX-Injected: yes.pdf',
                    content=pdf_bytes(world, ["x"]), mime="application/pdf")
    response = ingestion_api.download_file(
        project_id=world["project"].id, file_id=result.id,
        db=db, current_user=world["manager"],
    )
    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    assert "X-Injected" not in response.headers


def test_a_stranger_cannot_download(db, world):
    result = upload(db, world, filename="a.pdf", content=pdf_bytes(world, ["A"]),
                    mime="application/pdf")
    with pytest.raises(HTTPException) as refusal:
        ingestion_api.download_file(
            project_id=world["project"].id, file_id=result.id,
            db=db, current_user=world["outsider"],
        )
    assert refusal.value.status_code == 403
