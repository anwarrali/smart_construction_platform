"""How IFC bytes leave the server, and how much work may run at once.

Two properties that were correct only by accident before, and one that was not
bounded at all.

**The download must not depend on where the object lives.** `download_version`
and `geometry_asset` used to hand `FileResponse` a path taken from
`private_storage.local_path(...)` *inside* a `with` block. Starlette opens that
path after the handler returns — after the block has exited — so the pattern
works purely because the local backend's `local_path` yields the real file and
cleans up nothing. The abstraction exists so an R2/S3 backend can materialise
an object into a temporary file and remove it on exit, and against such a
backend every download would have failed. `_EphemeralPathStorage` below is that
backend, in miniature.

**Processing must be bounded.** Each job spawns a child process holding a whole
model; nothing limited how many could exist at once, so N simultaneous uploads
meant N parsers. The pool now caps that, and the cap has to hold under a burst,
survive a failing job, and not leak a slot.
"""

from __future__ import annotations

import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import ifc as ifc_api
from app.core.config import settings
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.company import Company
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.ifc import IFCModelGroup, IFCModelVersion
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services import rbac
from app.services.private_storage import private_storage

PASSWORD = "Correct#12345"
IFC_FIXTURE = Path(__file__).parent / "fixtures" / "minimal_ifc4.ifc"


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


@pytest.fixture()
def world(db):
    """One project, one manager, one processed revision with a real file."""
    suffix = uuid.uuid4().hex[:10]
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    office = Company(name=f"IFC Stream Office {suffix}", kind="CONSULTING_OFFICE", is_active=True)
    db.add(office)
    db.flush()

    role = roles["project_manager"]
    manager = User(
        full_name=f"StreamManager{suffix}", email=f"stream.{suffix}@constro.io",
        hashed_password=hash_password(PASSWORD), role=UserRole.PROJECT_MANAGER,
        status=UserStatus.ACTIVE, company_id=office.id, org_role_id=role.id,
        is_internal=role.is_internal_only,
    )
    db.add(manager)
    db.flush()

    project = Project(
        name=f"IFC Stream {suffix}", status=ProjectStatus.ACTIVE,
        company_id=office.id, project_manager_id=manager.id,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(
        project_id=project.id, user_id=manager.id, role_on_project=manager.role,
        project_role_id=role.id, is_active=True,
    ))
    db.flush()

    group = IFCModelGroup(
        project_id=project.id, name=f"Stream model {suffix}", created_by_id=manager.id,
    )
    db.add(group)
    db.flush()

    # A name with a non-ASCII character, so the header has to carry both forms.
    storage_key = f"ifc/{uuid.uuid4()}_stream_{suffix}.ifc"
    with private_storage.writable_local_path(storage_key) as target:
        target.write_bytes(IFC_FIXTURE.read_bytes())
    geometry_key = f"ifc_geometry/{uuid.uuid4()}_{suffix}.bimgeom"
    with private_storage.writable_local_path(geometry_key) as target:
        target.write_bytes(b"BIMGEO1\x00mock-geometry-payload")

    version = IFCModelVersion(
        model_group_id=group.id, project_id=project.id, version_number=1,
        revision_code="P01", version_type="DESIGN", title=f"Stream revision {suffix}",
        original_filename="مخطط-معماري.ifc", storage_key=storage_key,
        file_hash=uuid.uuid4().hex + uuid.uuid4().hex, file_size=IFC_FIXTURE.stat().st_size,
        ifc_schema="IFC4", uploaded_by_id=manager.id, processing_status="READY",
        processing_progress=100, entity_count=1, model_summary_json={},
        geometry_status="GEOMETRY_READY", geometry_storage_key=geometry_key,
    )
    db.add(version)
    db.flush()

    created = {
        "manager": manager, "project": project, "group": group, "version": version,
        "storage_key": storage_key, "geometry_key": geometry_key,
    }
    db.commit()

    try:
        yield created
    finally:
        db.rollback()
        for key in (storage_key, geometry_key):
            private_storage.delete(key)
        db.query(IFCModelVersion).filter(IFCModelVersion.project_id == project.id).delete(synchronize_session=False)
        db.query(IFCModelGroup).filter(IFCModelGroup.project_id == project.id).delete(synchronize_session=False)
        db.query(ProjectMember).filter(ProjectMember.project_id == project.id).delete(synchronize_session=False)
        db.query(Project).filter(Project.id == project.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == manager.id).delete(synchronize_session=False)
        db.query(Company).filter(Company.id == office.id).delete(synchronize_session=False)
        db.commit()


def _auth(client, user) -> dict:
    login = client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def ifc_url(project_id, suffix: str = "") -> str:
    return f"/api/v1/projects/{project_id}/ifc{suffix}"


# --- a storage backend that behaves the way a remote one has to -------------


class _EphemeralPathStorage:
    """The local backend, but with a `local_path` that really is temporary.

    This is what `private_storage`'s own docstring says a remote backend must
    do: materialise the object into a temporary file and remove it when the
    context closes. Reads through `open()` are unaffected. Any handler that
    still routes a download through `local_path` breaks against this and works
    against the local backend, which is precisely the failure mode that could
    not be caught before.
    """

    def __init__(self, inner, tmp_path: Path):
        self._inner = inner
        self._tmp = tmp_path
        self.materialised: list[Path] = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    @contextmanager
    def local_path(self, key: str):
        target = self._tmp / f"{uuid.uuid4().hex}-{Path(key).name}"
        with self._inner.local_path(key) as source:
            shutil.copyfile(source, target)
        self.materialised.append(target)
        try:
            yield target
        finally:
            target.unlink(missing_ok=True)


@pytest.fixture()
def ephemeral_storage(monkeypatch, tmp_path):
    """Serve the IFC routes from a storage backend with a disappearing path."""
    wrapper = _EphemeralPathStorage(private_storage, tmp_path)
    monkeypatch.setattr(ifc_api, "private_storage", wrapper)
    return wrapper


# --- the download itself ----------------------------------------------------


def test_the_original_ifc_comes_back_byte_for_byte(client, world):
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{world['version'].id}/download"),
        headers=_auth(client, world["manager"]),
    )
    assert response.status_code == 200
    assert response.content == IFC_FIXTURE.read_bytes()
    assert response.headers["content-type"].startswith("application/x-step")


def test_the_download_survives_a_backend_whose_local_path_disappears(
    client, world, ephemeral_storage
):
    """The regression this change exists for.

    Against the previous implementation the file is deleted before Starlette
    streams it, so this is the test that separates "works on the developer's
    filesystem" from "works on object storage".
    """
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{world['version'].id}/download"),
        headers=_auth(client, world["manager"]),
    )
    assert response.status_code == 200
    assert response.content == IFC_FIXTURE.read_bytes()
    # Nothing was materialised through the temporary-path route at all.
    assert ephemeral_storage.materialised == []


def test_the_viewer_asset_survives_the_same_backend(client, world, ephemeral_storage):
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{world['version'].id}/geometry/asset"),
        headers=_auth(client, world["manager"]),
    )
    assert response.status_code == 200
    assert response.content == b"BIMGEO1\x00mock-geometry-payload"
    assert ephemeral_storage.materialised == []


def test_the_response_names_the_file_in_both_header_forms(client, world):
    # `original_filename` is Arabic, so a bare `filename=` cannot carry it.
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{world['version'].id}/download"),
        headers=_auth(client, world["manager"]),
    )
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename=" in disposition
    assert "filename*=utf-8''" in disposition
    assert "%D9%85" in disposition  # the Arabic name, percent-encoded


def test_an_ascii_name_is_not_given_a_redundant_second_form(client, db, world):
    db.query(IFCModelVersion).filter(IFCModelVersion.id == world["version"].id).update(
        {"original_filename": "tower.ifc"}, synchronize_session=False
    )
    db.commit()
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{world['version'].id}/download"),
        headers=_auth(client, world["manager"]),
    )
    assert response.headers["content-disposition"] == 'attachment; filename="tower.ifc"'


def test_a_filename_cannot_break_out_of_the_header(client, db, world):
    # A stored name is not sanitised on upload beyond stripping the directory,
    # so the header builder is the thing that has to be safe.
    db.query(IFCModelVersion).filter(IFCModelVersion.id == world["version"].id).update(
        {"original_filename": 'evil";\r\nX-Injected: yes\r\n.ifc'}, synchronize_session=False
    )
    db.commit()
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{world['version'].id}/download"),
        headers=_auth(client, world["manager"]),
    )
    assert response.status_code == 200
    assert "x-injected" not in {key.lower() for key in response.headers}
    assert "\n" not in response.headers["content-disposition"]


def test_the_response_declares_its_length(client, world):
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{world['version'].id}/download"),
        headers=_auth(client, world["manager"]),
    )
    assert int(response.headers["content-length"]) == IFC_FIXTURE.stat().st_size


def test_no_server_path_is_disclosed(client, world):
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{world['version'].id}/download"),
        headers=_auth(client, world["manager"]),
    )
    joined = " ".join(response.headers.values())
    assert world["storage_key"] not in joined
    assert str(settings.PRIVATE_UPLOAD_DIR) not in joined
    assert "ifc/" not in response.headers["content-disposition"]


def test_a_missing_stored_file_is_reported_rather_than_streamed(client, db, world):
    private_storage.delete(world["storage_key"])
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{world['version'].id}/download"),
        headers=_auth(client, world["manager"]),
    )
    assert response.status_code == 404
    assert response.content != IFC_FIXTURE.read_bytes()


def test_an_unknown_version_is_not_a_download(client, world):
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{uuid.uuid4()}/download"),
        headers=_auth(client, world["manager"]),
    )
    assert response.status_code == 404


def test_an_anonymous_caller_gets_no_bytes(client, world):
    response = client.get(
        ifc_url(world["project"].id, f"/versions/{world['version'].id}/download")
    )
    assert response.status_code == 401
    assert response.content != IFC_FIXTURE.read_bytes()


# --- the processing limit ---------------------------------------------------


@pytest.fixture()
def bounded_pool(monkeypatch):
    """A pool sized for the test, torn down afterwards."""
    def build(limit: int):
        monkeypatch.setattr(settings, "IFC_MAX_CONCURRENT_PROCESSING", limit)
        ifc_api.reset_processing_pool()
        return ifc_api.processing_pool()

    yield build
    ifc_api.reset_processing_pool()


def _burst(job, count: int) -> None:
    for _ in range(count):
        ifc_api._submit(job)


def test_the_pool_never_runs_more_jobs_than_the_configured_limit(bounded_pool):
    bounded_pool(2)
    gate = threading.Event()
    lock = threading.Lock()
    state = {"running": 0, "peak": 0, "completed": 0}

    def job():
        with lock:
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
        gate.wait(timeout=10)
        with lock:
            state["running"] -= 1
            state["completed"] += 1

    _burst(job, 8)
    # Wait for the pool to reach its ceiling, then give any extra worker a
    # generous chance to start before concluding that none can.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and state["peak"] < 2:
        time.sleep(0.02)
    time.sleep(0.3)

    assert state["peak"] == 2, f"{state['peak']} jobs ran at once against a limit of 2"

    gate.set()
    ifc_api.processing_pool().shutdown(wait=True)
    assert state["completed"] == 8, "every queued job must still run"


def test_raising_the_limit_lets_more_run(bounded_pool):
    # The counterpart: the cap is the setting, not an accident of the machine.
    bounded_pool(4)
    gate = threading.Event()
    lock = threading.Lock()
    state = {"running": 0, "peak": 0}

    def job():
        with lock:
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
        gate.wait(timeout=10)
        with lock:
            state["running"] -= 1

    _burst(job, 8)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and state["peak"] < 4:
        time.sleep(0.02)
    time.sleep(0.2)
    assert state["peak"] == 4

    gate.set()
    ifc_api.processing_pool().shutdown(wait=True)


def test_a_failing_job_neither_kills_the_pool_nor_holds_its_slot(bounded_pool):
    bounded_pool(1)
    done = threading.Event()
    seen: list[str] = []

    def failing():
        seen.append("failed")
        raise RuntimeError("parser exploded")

    def following():
        seen.append("ran after")
        done.set()

    ifc_api._submit(failing)
    ifc_api._submit(following)

    assert done.wait(timeout=10), "a raising job left the single slot occupied"
    assert seen == ["failed", "ran after"]


def test_submitting_returns_without_waiting_for_the_job(bounded_pool):
    """The caller must not block: the wait belongs to the pool, not to the
    Starlette threadpool the background task is running on."""
    bounded_pool(1)
    gate = threading.Event()
    started = threading.Event()

    def blocker():
        started.set()
        gate.wait(timeout=10)

    ifc_api._submit(blocker)
    assert started.wait(timeout=5)

    began = time.monotonic()
    ifc_api._submit(lambda: None)  # queued behind the blocker
    assert time.monotonic() - began < 1.0, "submitting waited for a free slot"

    gate.set()
    ifc_api.processing_pool().shutdown(wait=True)


def test_the_pool_is_rebuilt_from_the_current_setting(bounded_pool):
    first = bounded_pool(1)
    assert first._max_workers == 1
    second = bounded_pool(3)
    assert second is not first
    assert second._max_workers == 3


def test_the_background_entry_points_go_through_the_pool(bounded_pool, monkeypatch):
    """`_background_process` and `_background_geometry` are what the routes
    call; the limit is worthless if either one bypasses it."""
    bounded_pool(1)
    ran = threading.Event()
    calls: list[tuple] = []

    def fake_process(db, version_id, actor_id=None):
        calls.append(("process", version_id))
        ran.set()

    monkeypatch.setattr(ifc_api, "process_version", fake_process)
    ifc_api._background_process(uuid.uuid4(), uuid.uuid4())
    assert ran.wait(timeout=10)
    assert calls and calls[0][0] == "process"


def test_a_job_closes_its_database_session_even_when_processing_fails(monkeypatch):
    closed: list[bool] = []

    class _Session:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(ifc_api, "SessionLocal", lambda: _Session())

    def boom(db, version_id, actor_id=None):
        raise RuntimeError("processing exploded")

    monkeypatch.setattr(ifc_api, "process_version", boom)
    with pytest.raises(RuntimeError):
        ifc_api._process_job(uuid.uuid4(), uuid.uuid4())
    assert closed == [True], "a failed job must not leak its session"
