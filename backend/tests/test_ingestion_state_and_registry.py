"""The lifecycle and the dispatch table — the two things everything depends on.

Neither needs a database or a file. They are pure rules, and pinning them here
means a change to either shows up as a failing rule rather than as a strange
result three layers away.
"""

from __future__ import annotations

import pytest

from app.services.ingestion import state
from app.services.ingestion.categories import FileCategory
from app.services.ingestion.contracts import BaseProcessor, ProcessorOutcome
from app.services.ingestion.errors import ERRORS, NO_PROCESSOR, public_error
from app.services.ingestion.processors import PROCESSOR_CLASSES, build_registry


# --- The lifecycle ----------------------------------------------------------

def test_the_happy_path_is_walkable_end_to_end():
    path = [state.UPLOADED, state.VALIDATING, state.CLASSIFIED,
            state.QUEUED, state.PROCESSING, state.READY]
    for current, target in zip(path, path[1:]):
        state.assert_transition(current, target)


@pytest.mark.parametrize(
    "current,target",
    [
        (state.UPLOADED, state.READY),
        (state.UPLOADED, state.PROCESSING),
        (state.VALIDATING, state.QUEUED),
        (state.CLASSIFIED, state.PROCESSING),
        (state.READY, state.PROCESSING),
        (state.FAILED, state.READY),
        (state.PROCESSING, state.QUEUED),
    ],
)
def test_a_shortcut_through_the_lifecycle_is_refused(current, target):
    with pytest.raises(state.InvalidTransition):
        state.assert_transition(current, target)


def test_a_failed_file_can_be_retried_and_a_partial_one_can_be_reprocessed():
    """Both must re-enter the queue: a PARTIAL result is what a later
    processor upgrade is meant to improve, and refusing would strand every
    scanned PDF permanently."""
    state.assert_transition(state.FAILED, state.QUEUED)
    state.assert_transition(state.PARTIAL, state.QUEUED)
    state.assert_transition(state.READY, state.QUEUED)


def test_a_synchronous_run_may_settle_straight_from_the_queue():
    """Inline processing never observably passes through PROCESSING, and the
    two execution modes must not disagree about what is legal."""
    for target in (state.READY, state.PARTIAL, state.FAILED):
        state.assert_transition(state.QUEUED, target)


def test_staying_in_the_same_state_is_not_a_transition():
    state.assert_transition(state.PROCESSING, state.PROCESSING)


def test_every_state_has_a_progress_value():
    for name in state.TRANSITIONS:
        assert name in state.PROGRESS


def test_the_settled_states_are_exactly_the_three_outcomes():
    assert state.SETTLED_STATUSES == {state.READY, state.PARTIAL, state.FAILED}


# --- Outcomes ---------------------------------------------------------------

def test_a_failure_without_a_reason_is_a_programming_error():
    with pytest.raises(ValueError):
        ProcessorOutcome(status=state.FAILED)
    with pytest.raises(ValueError):
        ProcessorOutcome(status=state.PARTIAL)


def test_a_processor_cannot_leave_a_file_in_a_working_state():
    for status in (state.PROCESSING, state.QUEUED, state.UPLOADED):
        with pytest.raises(ValueError):
            ProcessorOutcome(status=status)


def test_every_error_code_has_a_publishable_sentence():
    for code in ERRORS:
        published = public_error(code)
        assert published["title"] and published["description"]
        assert published["suggestedAction"]
        assert isinstance(published["retryable"], bool)


def test_an_unknown_error_code_still_publishes_something_safe():
    published = public_error("SOMETHING_NEW")
    assert published["code"] == "SOMETHING_NEW"
    assert published["title"]


def test_no_failure_means_no_error_object():
    assert public_error(None) is None


def test_a_published_error_never_carries_internal_detail():
    """The whole point of the split: nothing an attacker can learn from."""
    for code in ERRORS:
        rendered = " ".join(str(value) for value in public_error(code).values())
        assert "Traceback" not in rendered
        assert "/" not in rendered.replace("and/or", "")


# --- The registry -----------------------------------------------------------

def test_every_category_resolves_to_exactly_one_processor():
    registry = build_registry()
    for category in FileCategory:
        processor = registry.for_category(category)
        assert processor is not None


def test_the_declared_categories_cover_the_whole_enum():
    """A category added to the enum but not to a processor would silently fall
    through to the passthrough, which is a worse answer than a loud one."""
    registry = build_registry()
    assert registry.categories == frozenset(FileCategory)


def test_two_processors_cannot_claim_the_same_category():
    registry = build_registry()

    class Impostor(BaseProcessor):
        name = "impostor"
        categories = frozenset({FileCategory.PDF})

    with pytest.raises(ValueError, match="already handled"):
        registry.register(Impostor())


def test_a_retired_category_on_an_old_row_falls_back_rather_than_raising():
    """Rows outlive code. An unlistable file list is worse than a fallback."""
    registry = build_registry()

    class Row:
        file_category = "SOMETHING_RETIRED"

    assert registry.select(Row()).name == "passthrough"


def test_every_processor_has_a_stable_name_and_they_are_all_distinct():
    names = [factory().name for factory in PROCESSOR_CLASSES]
    assert len(names) == len(set(names))
    assert all(name and name.islower() for name in names)


def test_the_registry_a_test_builds_is_its_own():
    """`build_registry` returns a fresh instance, so a suite that swaps in a
    fake processor cannot leave a global mutated for whatever runs next."""
    first, second = build_registry(), build_registry()
    assert first is not second
    assert first.for_category(FileCategory.PDF) is not second.for_category(FileCategory.PDF)


def test_the_fallback_reports_the_absence_of_a_processor_explicitly():
    registry = build_registry()
    passthrough = registry.for_category(FileCategory.OTHER)
    assert passthrough.name == "passthrough"
    assert NO_PROCESSOR in ERRORS
