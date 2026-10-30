"""A large geometry result must not deadlock the parent.

The tessellator's result carries per-element bounds, so it grows with the
model. Collecting it with `join(timeout)` first and the queue second meant a
child holding more than a pipe buffer (~64 KB) of result could never exit, and
every model past roughly a thousand elements "timed out" after the full
geometry window — 900 seconds — although tessellation had finished in seconds.
Seen on two real models on 2026-10-14 (1,636 and 2,258 elements).
"""

import time

import pytest

from app.services import ifc_geometry_service as geometry


def large_result_worker(result_queue, args):
    """Stands in for the tessellator: a ~2 MB result, as a big model produces."""
    bounds = {step: {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]} for step in range(20000)}
    result_queue.put({"ok": True, "header": {"elementBounds": bounds}})


def dying_worker(result_queue, args):
    raise SystemExit(3)


def slow_worker(result_queue, args):
    time.sleep(30)


def test_a_result_larger_than_the_pipe_buffer_is_collected_promptly(monkeypatch):
    monkeypatch.setattr(geometry, "_geometry_worker", large_result_worker)
    started = time.monotonic()
    header = geometry._build_with_timeout((), timeout_seconds=60)
    assert len(header["elementBounds"]) == 20000
    # The old order waited out the whole window; a few seconds is spawn cost.
    assert time.monotonic() - started < 30


def test_a_worker_that_dies_is_reported_at_once(monkeypatch):
    monkeypatch.setattr(geometry, "_geometry_worker", dying_worker)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="exited without a result"):
        geometry._build_with_timeout((), timeout_seconds=60)
    assert time.monotonic() - started < 30


def test_a_worker_still_running_at_the_deadline_is_a_timeout(monkeypatch):
    monkeypatch.setattr(geometry, "_geometry_worker", slow_worker)
    with pytest.raises(TimeoutError):
        geometry._build_with_timeout((), timeout_seconds=3)
