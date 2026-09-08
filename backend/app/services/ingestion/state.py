"""The ingestion lifecycle, written down as a table rather than as `if`s.

    UPLOADED ──► VALIDATING ──► CLASSIFIED ──► QUEUED ──► PROCESSING ──┬─► READY
         │            │                                               ├─► PARTIAL
         └────────────┴──────────────────────────────────────────────►└─► FAILED
                                                                          │
                                                        QUEUED ◄──────────┘ (retry)

Modelled on `ifc_processing_service.VERSION_TRANSITIONS`, deliberately: the IFC
subsystem already proved that an explicit transition table catches the bug an
`if status == ...` chain hides — a job that writes READY over a FAILED row
because two workers raced. This is the same mechanism for the general pipeline,
not a competing one.

**PARTIAL is a success, not a failure.** It means the processor ran to
completion and delivered less than its declared capability: a scanned PDF with
no text layer, a DWG that is stored but not parsed. The file is usable, the
metadata is trustworthy as far as it goes, and the reason is recorded. Calling
that FAILED would push people to retry something that will never succeed.
"""

from __future__ import annotations

UPLOADED = "UPLOADED"
VALIDATING = "VALIDATING"
CLASSIFIED = "CLASSIFIED"
QUEUED = "QUEUED"
PROCESSING = "PROCESSING"
READY = "READY"
PARTIAL = "PARTIAL"
FAILED = "FAILED"

#: Terminal states a processor may report as its own outcome.
OUTCOME_STATUSES = frozenset({READY, PARTIAL, FAILED})

#: States in which the file is finished with and safe to read.
SETTLED_STATUSES = frozenset({READY, PARTIAL, FAILED})

TRANSITIONS: dict[str, frozenset[str]] = {
    UPLOADED: frozenset({VALIDATING, FAILED}),
    VALIDATING: frozenset({CLASSIFIED, FAILED}),
    CLASSIFIED: frozenset({QUEUED, FAILED}),
    # QUEUED → READY/PARTIAL directly is allowed: a synchronous run (tests, and
    # deployments with background processing switched off) never observably
    # passes through PROCESSING, and forbidding it would make the two execution
    # modes behave differently for no benefit.
    QUEUED: frozenset({PROCESSING, READY, PARTIAL, FAILED}),
    PROCESSING: frozenset({READY, PARTIAL, FAILED}),
    # A retry re-enters the queue. READY and PARTIAL may be re-processed too:
    # a PARTIAL result is exactly what a later processor upgrade is meant to
    # improve, and refusing would strand every scanned PDF forever.
    READY: frozenset({QUEUED}),
    PARTIAL: frozenset({QUEUED}),
    FAILED: frozenset({QUEUED}),
}

#: Progress reported to the client, per state. Purely cosmetic; the status is
#: the truth. Kept here so the API and the worker cannot drift apart on it.
PROGRESS: dict[str, int] = {
    UPLOADED: 5, VALIDATING: 15, CLASSIFIED: 30, QUEUED: 40,
    PROCESSING: 60, READY: 100, PARTIAL: 100, FAILED: 100,
}


class InvalidTransition(ValueError):
    """A state change the lifecycle does not allow."""


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


def assert_transition(current: str, target: str) -> None:
    if current == target:
        return
    if not can_transition(current, target):
        raise InvalidTransition(f"Invalid ingestion transition {current} -> {target}")
