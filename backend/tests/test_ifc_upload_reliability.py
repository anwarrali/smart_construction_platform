"""IFC upload and processing reliability — the failures seen on 2026-10-14.

Three real uploads to one project failed, each for a different reason, and the
UI reported all of them as a vague error:

* A 112.7 MB architectural model was refused as "too large" by an entity cap
  that counted all 2,163,670 STEP records — geometry included — although the
  model holds only 2,263 products and extracts in about 20 seconds.
* A generated 1 MB IFC4 file wrote its doors and windows in the IFC2X3 layout
  (9 attributes instead of 13). Reading `PredefinedType` raised ifcopenshell's
  `RuntimeError`, which `getattr(..., None)` does not absorb, so one optional
  field aborted the whole extraction — reported as a generic failure with
  nothing in the logs.
* Re-uploading that file returned HTTP 409 (the project already holds those
  bytes) without saying where, and a second retry of a running job also
  answered 409, which read as a failure of something that was working.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import pytest

from app.core.config import settings
from app.models.ifc import IFCModelVersion
from app.services import ifc_processing_service as service
from app.services.ifc_parser import IFCParseError, IFCParser
from app.services.ifc_policy import friendly_ifc_error, is_retryable
from app.models.background_job import BackgroundJob
from app.services.private_storage import private_storage

# Shared fixtures: two projects, a manager holding every IFC verb, real login.
from tests.test_ifc_authorization import (  # noqa: F401 - pytest fixtures
    _auth, client, db, ifc_url, no_background_processing, world,
)

FIXTURES = Path(__file__).parent / "fixtures"


# --- the parser ---------------------------------------------------------------


def _ifc4_with_ifc2x3_shaped_door(tmp_path: Path) -> Path:
    """minimal_ifc4.ifc plus a door written with 9 attributes, as the QA file was.

    IFC4 defines 13 attributes for IfcDoor; IFC2X3 defines fewer. The STEP line
    below is the shape the generator produced.
    """
    source = (FIXTURES / "minimal_ifc4.ifc").read_text(encoding="utf-8")
    door = "#9001=IFCDOOR('2X8Wd8lDjCHPsE2zt6hlGl',$,'Internal Door F1',$,'Internal Door F1',$,$,'DOOR-00178',$);\n"
    patched = source.replace("ENDSEC;\nEND-ISO-10303-21;", door + "ENDSEC;\nEND-ISO-10303-21;")
    assert patched != source, "fixture layout changed; update the splice point"
    path = tmp_path / "ifc2x3_shaped_door.ifc"
    path.write_text(patched, encoding="utf-8")
    return path


def test_a_schema_mismatched_entity_is_a_warning_not_a_failed_import(tmp_path):
    pytest.importorskip("ifcopenshell")
    parsed = IFCParser().parse(_ifc4_with_ifc2x3_shaped_door(tmp_path))
    door = next(item for item in parsed.elements if item.entity_type == "IfcDoor")
    assert door.name == "Internal Door F1"
    # The unreadable attribute is absent, not invented.
    assert door.predefined_type is None
    warning = next(text for text in parsed.warnings if "do not match" in text)
    assert "IfcDoor x1" in warning and "IFC4" in warning


def test_a_clean_model_reports_no_schema_mismatch():
    pytest.importorskip("ifcopenshell")
    parsed = IFCParser().parse(FIXTURES / "multi_discipline_ifc4.ifc")
    assert not any("do not match" in text for text in parsed.warnings)


def test_the_entity_limit_counts_products_not_step_records(monkeypatch):
    pytest.importorskip("ifcopenshell")
    import ifcopenshell

    path = FIXTURES / "multi_discipline_ifc4.ifc"
    model = ifcopenshell.open(str(path))
    products = len(model.by_type("IfcProduct"))
    step_records = sum(1 for _ in model)
    assert step_records > products  # geometry and relationships outnumber products

    # A cap between the two: the old rule (all STEP records) refused this
    # model; the new one (products) accepts it.
    monkeypatch.setattr(settings, "IFC_MAX_ENTITY_COUNT", products)
    IFCParser().parse(path)

    monkeypatch.setattr(settings, "IFC_MAX_ENTITY_COUNT", products - 1)
    with pytest.raises(IFCParseError) as failure:
        IFCParser().parse(path)
    assert str(failure.value) == "IFC_ENTITY_LIMIT_EXCEEDED"


# --- the memory guard ---------------------------------------------------------


def test_a_model_beyond_the_memory_budget_is_refused_before_it_is_opened(monkeypatch):
    monkeypatch.setattr(settings, "IFC_PARSE_MEMORY_MB", 3072)
    with pytest.raises(IFCParseError) as failure:
        service.check_processing_memory(300 * 1024 * 1024)
    assert str(failure.value) == "IFC_MODEL_TOO_LARGE_FOR_HOST"
    message = failure.value.user_message
    assert "300 MB" in message and "3.0 GB" in message and "unchanged" in message


def test_the_measured_112mb_model_fits_the_default_budget(monkeypatch):
    # 112.7 MB peaked at 1.98 GB resident in a real parse on this stack.
    monkeypatch.setattr(settings, "IFC_PARSE_MEMORY_MB", 3072)
    service.check_processing_memory(112_680_487)
    assert 1900 <= service.estimated_parse_memory_mb(112_680_487) <= 2300


def test_the_processable_size_follows_the_budget(monkeypatch):
    monkeypatch.setattr(settings, "IFC_PARSE_MEMORY_MB", 3072)
    assert service.max_processable_file_mb() == 174
    monkeypatch.setattr(settings, "IFC_PARSE_MEMORY_MB", 8192)
    assert service.max_processable_file_mb() == 484


# --- the worker reports what actually happened --------------------------------


class _Queue:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (RuntimeError("Index 10 is out of range for variant of size 9"), "IFC_PROCESSING_FAILED"),
        (MemoryError(), "IFC_PARSER_OUT_OF_MEMORY"),
        (RuntimeError("std::bad_alloc"), "IFC_PARSER_OUT_OF_MEMORY"),
        (IFCParseError("IFC_FILE_CORRUPTED"), "IFC_FILE_CORRUPTED"),
    ],
)
def test_the_parser_worker_returns_a_code_and_a_loggable_reason(monkeypatch, raised, code):
    monkeypatch.setattr(service, "_limit_worker_memory", lambda: None)

    def explode(self, source):
        raise raised

    monkeypatch.setattr(IFCParser, "parse", explode)
    queue = _Queue()
    service._parse_worker("ifc/any.ifc", queue)
    kind, (returned_code, detail) = queue.items[0]
    assert kind == "error" and returned_code == code
    if code == "IFC_PROCESSING_FAILED":
        # The real exception is kept for the log the support ID points at.
        assert detail.startswith("RuntimeError: Index 10")


def test_the_new_failure_code_has_user_facing_text():
    friendly = friendly_ifc_error("IFC_MODEL_TOO_LARGE_FOR_HOST", "s-1")
    assert friendly["title"] and friendly["description"] and friendly["suggestedAction"]


def test_retry_is_offered_only_where_it_can_help():
    assert is_retryable("IFC_PROCESSING_FAILED")
    assert is_retryable("IFC_ENTITY_LIMIT_EXCEEDED")  # a limit an admin may change
    assert not is_retryable("IFC_DUPLICATE")


# --- the HTTP surface ---------------------------------------------------------


def _upload(client, headers, project_id, group_id, content: bytes, name="model.ifc"):
    return client.post(
        ifc_url(project_id, f"/models/{group_id}/versions"),
        headers=headers,
        files={"file": (name, content, "application/x-step")},
        data={"title": "Upload reliability", "revision_code": "R1", "version_type": "DESIGN"},
    )


def _unique_ifc(tag: str) -> bytes:
    """A valid IFC whose bytes — and so whose hash — are unique to this run."""
    source = (FIXTURES / "minimal_ifc4.ifc").read_text(encoding="utf-8")
    return source.replace("FILE_NAME('minimal_ifc4.ifc'", f"FILE_NAME('reliability-{tag}.ifc'", 1).encode()


def test_a_repeated_upload_names_the_version_that_already_holds_the_file(client, world, no_background_processing):
    headers = _auth(client, world["manager"])
    project_id, group_id = world["project_a"].id, world["a"]["group"].id
    content = _unique_ifc(uuid.uuid4().hex)

    first = _upload(client, headers, project_id, group_id, content)
    assert first.status_code == 202, first.text
    second = _upload(client, headers, project_id, group_id, content, name="renamed-copy.ifc")
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "IFC_DUPLICATE"
    assert detail["existingVersionId"] == first.json()["id"]
    assert detail["existingModelGroupId"] == str(group_id)
    assert detail["existingVersionNumber"] == first.json()["versionNumber"]
    assert detail["existingStatus"]
    # Only one version holds those bytes, and only one processing job was queued.
    assert len(no_background_processing) == 1


def test_a_racing_duplicate_upload_gets_the_same_answer_and_leaves_no_orphan_file(
    client, world, db, no_background_processing, monkeypatch,
):
    """Two requests that both passed the duplicate check before either committed.

    The pre-check is bypassed for the second request, which is exactly the
    window a double click opens; the unique (project_id, file_hash) index must
    then decide, and the loser must clean up its own stored copy.
    """
    headers = _auth(client, world["manager"])
    project_id, group_id = world["project_a"].id, world["a"]["group"].id
    content = _unique_ifc(uuid.uuid4().hex)
    first = _upload(client, headers, project_id, group_id, content)
    assert first.status_code == 202, first.text

    saved: list[str] = []
    real_save = private_storage.save

    async def recording_save(upload, folder):
        key, size = await real_save(upload, folder)
        saved.append(key)
        return key, size

    monkeypatch.setattr("app.api.ifc._find_duplicate", lambda *args: None)
    monkeypatch.setattr(private_storage, "save", recording_save)
    racing = _upload(client, headers, project_id, group_id, content)

    assert racing.status_code == 409, racing.text
    assert racing.json()["detail"]["existingVersionId"] == first.json()["id"]
    assert saved and not private_storage.exists(saved[0])
    db.expire_all()
    holders = db.query(IFCModelVersion).filter(
        IFCModelVersion.project_id == project_id, IFCModelVersion.title == "Upload reliability",
        IFCModelVersion.file_size == len(content),
    ).count()
    assert holders == 1


def test_retrying_a_version_that_is_already_processing_joins_it(client, world, db, no_background_processing):
    headers = _auth(client, world["manager"])
    version = world["a"]["second_version"]
    version.processing_status = "PARSING"
    db.commit()
    try:
        first = client.post(ifc_url(world["project_a"].id, f"/versions/{version.id}/retry"), headers=headers)
        second = client.post(ifc_url(world["project_a"].id, f"/versions/{version.id}/retry"), headers=headers)
        assert first.status_code == 202 and second.status_code == 202
        assert first.json()["processingStatus"] == "PARSING"
        # Joining a running job queues nothing new.
        assert no_background_processing == []
    finally:
        version.processing_status = "READY"
        db.commit()


def test_retrying_a_failed_version_queues_exactly_one_job(client, world, db):
    """Real enqueue, real dedupe: two quick retries are one job."""
    headers = _auth(client, world["manager"])
    version = world["a"]["second_version"]
    version.processing_status = "FAILED"
    version.parsing_error_code = "IFC_PROCESSING_FAILED"
    db.commit()
    try:
        for _ in range(2):
            response = client.post(ifc_url(world["project_a"].id, f"/versions/{version.id}/retry"), headers=headers)
            assert response.status_code == 202, response.text
        db.expire_all()
        jobs = db.query(BackgroundJob).filter(
            BackgroundJob.kind == "ifc.process_version",
            BackgroundJob.dedupe_key == f"ifc.process:{version.id}",
        ).all()
        assert len(jobs) == 1
        assert response.json()["parsingErrorRetryable"] is True
    finally:
        db.query(BackgroundJob).filter(BackgroundJob.dedupe_key == f"ifc.process:{version.id}").delete(synchronize_session=False)
        version.processing_status = "READY"
        version.parsing_error_code = None
        db.commit()


def test_retrying_a_processed_version_is_refused(client, world):
    headers = _auth(client, world["manager"])
    version = world["a"]["version"]
    response = client.post(ifc_url(world["project_a"].id, f"/versions/{version.id}/retry"), headers=headers)
    assert response.status_code == 409


def test_upload_constraints_separate_storage_from_processing(client, world, monkeypatch):
    monkeypatch.setattr(settings, "IFC_PARSE_MEMORY_MB", 3072)
    body = client.get(ifc_url(world["project_a"].id, "/upload-constraints"), headers=_auth(client, world["manager"])).json()
    assert body["maxFileMb"] == settings.IFC_MAX_FILE_MB
    assert body["maxProcessableFileMb"] == min(settings.IFC_MAX_FILE_MB, 174)


# --- a failure is recorded, explained and logged --------------------------------


def test_a_processing_failure_is_logged_under_its_support_id(world, db, monkeypatch, caplog):
    version = world["a"]["second_version"]
    version.processing_status = "FAILED"
    db.commit()

    def failing_parse(storage_key):
        raise IFCParseError("IFC_PROCESSING_FAILED", detail="RuntimeError: Index 10 is out of range for variant of size 9")

    monkeypatch.setattr(service, "parse_with_timeout", failing_parse)
    monkeypatch.setattr(service, "check_processing_memory", lambda size: None)
    try:
        with caplog.at_level(logging.WARNING, logger=service.__name__):
            service.process_version(db, version.id)
        db.expire_all()
        failed = db.get(IFCModelVersion, version.id)
        assert failed.processing_status == "FAILED"
        assert failed.parsing_error_code == "IFC_PROCESSING_FAILED"
        assert failed.support_log_id
        logged = [record.getMessage() for record in caplog.records if failed.support_log_id in record.getMessage()]
        assert logged and "Index 10 is out of range" in logged[0]
        # The user-facing text never carries the technical detail.
        assert "Index 10" not in (failed.parsing_error_message or "")
    finally:
        failed = db.get(IFCModelVersion, version.id)
        failed.processing_status = "READY"; failed.parsing_error_code = None
        failed.parsing_error_message = None; failed.support_log_id = None
        db.commit()


def test_a_model_too_large_for_the_host_fails_fast_with_its_numbers(world, db, monkeypatch):
    version = world["a"]["second_version"]
    version.processing_status = "FAILED"
    original_size = version.file_size
    version.file_size = 400 * 1024 * 1024
    db.commit()
    monkeypatch.setattr(settings, "IFC_PARSE_MEMORY_MB", 3072)
    parsed: list = []
    monkeypatch.setattr(service, "parse_with_timeout", lambda key: parsed.append(key))
    try:
        service.process_version(db, version.id)
        db.expire_all()
        failed = db.get(IFCModelVersion, version.id)
        assert failed.parsing_error_code == "IFC_MODEL_TOO_LARGE_FOR_HOST"
        assert "400 MB" in failed.parsing_error_message
        assert parsed == []  # never opened
    finally:
        failed = db.get(IFCModelVersion, version.id)
        failed.processing_status = "READY"; failed.file_size = original_size
        failed.parsing_error_code = None; failed.parsing_error_message = None; failed.support_log_id = None
        db.commit()


# --- recovery ------------------------------------------------------------------


def test_a_successful_retry_clears_the_earlier_failure(world, db, monkeypatch):
    """Seen on the live QA file: READY_WITH_WARNINGS, still carrying IFC_PROCESSING_FAILED."""
    pytest.importorskip("ifcopenshell")
    version = world["a"]["second_version"]
    version.processing_status = "FAILED"
    version.parsing_error_code = "IFC_PROCESSING_FAILED"
    version.parsing_error_message = "Extraction stopped before the model could be stored."
    version.support_log_id = "old-support-id"
    db.commit()
    monkeypatch.setattr(service, "check_processing_memory", lambda size: None)
    monkeypatch.setattr(service, "parse_with_timeout", lambda key: IFCParser().parse(FIXTURES / "minimal_ifc4.ifc"))
    monkeypatch.setattr(service, "generate_geometry", lambda db, version_id: None)
    monkeypatch.setattr(service, "run_interference_analysis", lambda db, version_id: None)
    service.process_version(db, version.id)
    db.expire_all()
    done = db.get(IFCModelVersion, version.id)
    assert done.processing_status in {"READY", "READY_WITH_WARNINGS"}
    assert done.parsing_error_code is None and done.parsing_error_message is None and done.support_log_id is None


def _geometry_jobs(db, version_id):
    return db.query(BackgroundJob).filter(BackgroundJob.dedupe_key == f"ifc.geometry:{version_id}")


def test_geometry_orphaned_by_a_dead_worker_can_be_started_again(client, world, db):
    version = world["a"]["version"]
    version.geometry_status = "GEOMETRY_PROCESSING"  # no job behind it
    db.commit()
    try:
        response = client.post(ifc_url(world["project_a"].id, f"/versions/{version.id}/geometry/generate"),
                               headers=_auth(client, world["manager"]))
        assert response.status_code == 202
        assert response.json()["message"] == "Geometry generation started."
        db.expire_all()
        assert _geometry_jobs(db, version.id).count() == 1
        # With that job now active, a second request joins it.
        again = client.post(ifc_url(world["project_a"].id, f"/versions/{version.id}/geometry/generate"),
                            headers=_auth(client, world["manager"]))
        assert again.json()["message"] == "Geometry is already processing."
        db.expire_all()
        assert _geometry_jobs(db, version.id).count() == 1
    finally:
        _geometry_jobs(db, version.id).delete(synchronize_session=False)
        version.geometry_status = "NOT_REQUESTED"
        db.commit()
