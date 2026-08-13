"""The private storage abstraction that keeps IFC logic independent of the backend."""

from pathlib import Path

import pytest

from app.core.config import settings
from app.services.private_storage import (
    LocalFilesystemStorage,
    PrivateStorage,
    private_storage,
)


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PRIVATE_UPLOAD_DIR", str(tmp_path))
    return LocalFilesystemStorage()


def test_the_local_backend_satisfies_the_storage_contract():
    assert isinstance(private_storage, PrivateStorage)
    for name in ("save", "exists", "size", "open", "delete", "local_path", "writable_local_path", "put_local_file"):
        assert callable(getattr(private_storage, name)), name


def test_a_written_object_can_be_read_back(storage):
    with storage.writable_local_path("ifc/model.ifc") as target:
        target.write_bytes(b"ISO-10303-21;")
    assert storage.exists("ifc/model.ifc")
    assert storage.size("ifc/model.ifc") == 13
    with storage.open("ifc/model.ifc") as handle:
        assert handle.read() == b"ISO-10303-21;"


def test_writable_path_creates_missing_directories(storage):
    with storage.writable_local_path("ifc_geometry/nested/deep/asset.bimgeom") as target:
        target.write_bytes(b"geometry")
    assert storage.exists("ifc_geometry/nested/deep/asset.bimgeom")


def test_local_path_yields_a_real_file_for_tools_that_need_one(storage):
    with storage.writable_local_path("ifc/a.ifc") as target:
        target.write_bytes(b"data")
    with storage.local_path("ifc/a.ifc") as path:
        assert isinstance(path, Path)
        assert path.read_bytes() == b"data"


def test_delete_removes_the_object_and_tolerates_a_missing_one(storage):
    with storage.writable_local_path("ifc/gone.ifc") as target:
        target.write_bytes(b"x")
    storage.delete("ifc/gone.ifc")
    assert not storage.exists("ifc/gone.ifc")
    storage.delete("ifc/gone.ifc")  # must not raise


def test_missing_object_reports_absence_rather_than_raising(storage):
    assert storage.exists("ifc/never.ifc") is False
    assert storage.size("ifc/never.ifc") is None


def test_keys_cannot_escape_the_storage_root(storage):
    for key in ("../escape.ifc", "ifc/../../escape.ifc", "/etc/passwd"):
        assert storage.exists(key) is False
        with pytest.raises(ValueError):
            with storage.local_path(key):
                pass


def test_put_local_file_moves_a_produced_file_under_its_key(storage, tmp_path):
    source = tmp_path / "produced.bin"
    source.write_bytes(b"produced bytes")
    size = storage.put_local_file(source, "ifc_geometry/out.bimgeom")
    assert size == 14
    assert storage.exists("ifc_geometry/out.bimgeom")
    assert not source.exists(), "the temporary source is consumed"


def test_an_unknown_backend_name_fails_loudly(monkeypatch):
    from app.services import private_storage as module

    monkeypatch.setattr(settings, "PRIVATE_STORAGE_BACKEND", "cloudflare-r2")
    with pytest.raises(ValueError, match="Unsupported PRIVATE_STORAGE_BACKEND"):
        module._build()
