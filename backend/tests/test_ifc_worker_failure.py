"""What the pipeline reports when the isolated parser worker dies.

IfcOpenShell is a native library and does not always raise. A truncated IFC —
the shape an interrupted export or transfer leaves behind — segfaults it, so
the worker vanishes without putting anything on the result queue.

Waiting on the queue alone cannot tell that apart from a model that is simply
slow, so the failure surfaced as `IFC_PARSE_TIMEOUT` only after the whole
window had elapsed: ten minutes of a held worker, followed by advice to upload
a smaller model, for a file that was never readable in the first place.
"""

import os
import signal
import sys
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.ifc_parser import IFCParseError
from app.services.ifc_policy import ERRORS, friendly_ifc_error
from app.services import ifc_processing_service as service


FIXTURES = Path(__file__).parent / "fixtures"


class _DeadProcess:
    """A worker that has already exited without reporting anything."""

    def __init__(self, exitcode: int):
        self.exitcode = exitcode
        self.terminated = False

    def start(self):
        return None

    def is_alive(self):
        return False

    def join(self, timeout=None):
        return None

    def terminate(self):
        self.terminated = True


class _SilentQueue:
    """A result queue nothing was ever written to."""

    def __init__(self):
        self.closed = False

    def get(self, timeout=None):
        from queue import Empty

        raise Empty

    def close(self):
        self.closed = True


def _with_dead_worker(monkeypatch, exitcode: int):
    process = _DeadProcess(exitcode)
    queue = _SilentQueue()
    monkeypatch.setattr(
        service, "get_context",
        lambda _: type("Ctx", (), {"Queue": lambda self, maxsize: queue,
                                   "Process": lambda self, **kwargs: process})(),
    )
    return process, queue


def test_a_crashed_parser_worker_is_reported_as_a_bad_file(monkeypatch):
    _with_dead_worker(monkeypatch, exitcode=-11)  # SIGSEGV
    monkeypatch.setattr(settings, "IFC_PARSE_TIMEOUT_SECONDS", 600)
    with pytest.raises(IFCParseError) as failure:
        service.parse_with_timeout("ifc/whatever.ifc")
    assert str(failure.value) == "IFC_FILE_CORRUPTED"


def test_a_crashed_worker_does_not_wait_out_the_timeout_window(monkeypatch):
    from time import perf_counter

    _with_dead_worker(monkeypatch, exitcode=-11)
    monkeypatch.setattr(settings, "IFC_PARSE_TIMEOUT_SECONDS", 600)
    started = perf_counter()
    with pytest.raises(IFCParseError):
        service.parse_with_timeout("ifc/whatever.ifc")
    # The grace drain is the only wait; the 600-second window is never entered.
    assert perf_counter() - started < service.PARSE_EXIT_GRACE_SECONDS + 5


def test_a_worker_killed_for_memory_says_so_instead_of_blaming_the_file(monkeypatch):
    kill_signal = getattr(signal, "SIGKILL", 9)
    _with_dead_worker(monkeypatch, exitcode=-kill_signal)
    monkeypatch.setattr(settings, "IFC_PARSE_TIMEOUT_SECONDS", 600)
    with pytest.raises(IFCParseError) as failure:
        service.parse_with_timeout("ifc/whatever.ifc")
    assert str(failure.value) == "IFC_PARSER_OUT_OF_MEMORY"


def test_a_worker_still_running_at_the_deadline_is_still_a_timeout(monkeypatch):
    class _HungProcess(_DeadProcess):
        def is_alive(self):
            return True

    process = _HungProcess(exitcode=None)
    queue = _SilentQueue()
    monkeypatch.setattr(
        service, "get_context",
        lambda _: type("Ctx", (), {"Queue": lambda self, maxsize: queue,
                                   "Process": lambda self, **kwargs: process})(),
    )
    monkeypatch.setattr(settings, "IFC_PARSE_TIMEOUT_SECONDS", 0.1)
    with pytest.raises(IFCParseError) as failure:
        service.parse_with_timeout("ifc/whatever.ifc")
    assert str(failure.value) == "IFC_PARSE_TIMEOUT"
    assert process.terminated


@pytest.mark.parametrize(
    "code",
    ["IFC_FILE_CORRUPTED", "IFC_PARSER_UNAVAILABLE", "IFC_ENTITY_LIMIT_EXCEEDED",
     "IFC_PARSE_TIMEOUT", "IFC_PARSER_OUT_OF_MEMORY", "IFC_PROCESSING_FAILED",
     "IFC_GEOMETRY_FAILED", "IFC_DUPLICATE", "IFC_COMPARISON_GROUP_MISMATCH"],
)
def test_every_code_the_pipeline_emits_has_user_facing_text(code):
    # A code without an entry falls back to "IFC operation failed", which tells
    # the user nothing and gives them nothing to do.
    assert code in ERRORS
    friendly = friendly_ifc_error(code, "support-1")
    assert friendly["title"] and friendly["description"] and friendly["suggestedAction"]
    assert friendly["supportLogId"] == "support-1"


def test_out_of_memory_advice_differs_from_corrupt_file_advice():
    # The two crash causes need opposite next steps; identical copy would make
    # distinguishing them pointless.
    assert (friendly_ifc_error("IFC_PARSER_OUT_OF_MEMORY")["suggestedAction"]
            != friendly_ifc_error("IFC_FILE_CORRUPTED")["suggestedAction"])


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal semantics")
def test_exit_code_mapping_matches_real_signals():
    assert service._worker_death_code(-signal.SIGSEGV) == "IFC_FILE_CORRUPTED"
    assert service._worker_death_code(-signal.SIGKILL) == "IFC_PARSER_OUT_OF_MEMORY"
    assert service._worker_death_code(1) == "IFC_FILE_CORRUPTED"
    assert service._worker_death_code(None) == "IFC_FILE_CORRUPTED"


@pytest.mark.skipif(
    os.environ.get("IFC_NATIVE_CRASH_TEST") != "1",
    reason="spawns a real IfcOpenShell worker that segfaults; opt in explicitly",
)
def test_a_real_truncated_ifc_is_reported_as_corrupt_not_as_a_timeout(tmp_path, monkeypatch):
    """The end-to-end proof, kept opt-in because it crashes a child process."""
    pytest.importorskip("ifcopenshell")
    source = (FIXTURES / "multi_discipline_ifc4.ifc").read_bytes()
    root = tmp_path / "private"
    (root / "ifc").mkdir(parents=True)
    (root / "ifc" / "truncated.ifc").write_bytes(source[: len(source) // 2])
    monkeypatch.setattr(settings, "PRIVATE_UPLOAD_DIR", str(root))
    monkeypatch.setattr(settings, "IFC_PARSE_TIMEOUT_SECONDS", 120)
    with pytest.raises(IFCParseError) as failure:
        service.parse_with_timeout("ifc/truncated.ifc")
    assert str(failure.value) == "IFC_FILE_CORRUPTED"
