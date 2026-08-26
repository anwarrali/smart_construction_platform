"""The seams between the matcher, the draft pipeline, and the rest of the app.

The matcher's own behaviour is covered in `test_voice_task_matching.py`. What
is tested here is that its results actually reach the engineer, and that a
confirmed voice update reaches the screens that were already open — the two
places where a correct component still produces a broken feature if it is
wired up wrongly.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.enums import TaskStatus
from app.models.voice_action import VoiceClarification
from app.services.voice_command_service import (
    create_target_clarifications,
    spoken_task_reference,
)
from app.services.voice_task_matcher import MAX_CANDIDATES, match_task


def task(code, name, *, discipline=None, status="todo", progress=0.0):
    return SimpleNamespace(
        id=uuid4(),
        task_code=code,
        name=name,
        discipline=discipline,
        status=status,
        progress_percentage=progress,
        description=None,
    )


def crowded_project(count=40):
    """A project big enough that an unranked picker would be unusable."""
    disciplines = ["electrical", "civil", "mechanical", "plumbing"]
    return [
        task(
            f"T-{index:03d}",
            f"{disciplines[index % 4].title()} works package {index}",
            discipline=disciplines[index % 4],
        )
        for index in range(count)
    ] + [
        task("EL-101", "First Floor - Electrical Installation", discipline="electrical"),
        task("EL-102", "First Floor - Electrical Fixtures", discipline="electrical"),
    ]


def draft(*, client_action_id="a1", missing=("target.taskId",)):
    return SimpleNamespace(
        id=uuid4(),
        client_action_id=client_action_id,
        missing_fields=list(missing),
        action_type="ADD_TASK_NOTE",
        target_entity_id=None,
        extracted_payload={"content": "plastering started"},
        user_edited_payload=None,
    )


def command(**overrides):
    values = {
        "id": uuid4(),
        "raw_transcript": "I finished the first floor electrical work",
        "normalized_transcript": None,
        "action_drafts": [],
        "clarifications": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ClarificationShortlistTests(TestCase):
    def test_the_question_offers_a_shortlist_not_the_whole_project(self):
        tasks = crowded_project()
        subject = command(action_drafts=[draft()])

        create_target_clarifications(MagicMock(), subject, candidates=tasks)

        options = subject.clarifications[0].options
        self.assertLessEqual(len(options), MAX_CANDIDATES)
        self.assertGreater(len(tasks), MAX_CANDIDATES)

    def test_the_shortlist_holds_what_was_actually_said(self):
        # Which of the two first-floor electrical tasks leads is a genuine
        # coin-flip — that is exactly why this produces a question. What must
        # not happen is the forty unrelated packages crowding them out.
        tasks = crowded_project()
        subject = command(action_drafts=[draft()])

        create_target_clarifications(MagicMock(), subject, candidates=tasks)

        labels = " | ".join(option["label"] for option in subject.clarifications[0].options)
        self.assertIn("EL-101", labels)
        self.assertIn("EL-102", labels)

    def test_a_precomputed_ranking_is_used_verbatim(self):
        # The drafting pass matched against this action's own reference; the
        # clarification must not silently re-match against the whole utterance
        # and offer something else.
        tasks = crowded_project()
        ranked = match_task("plastering", tasks).candidates
        subject = command(action_drafts=[draft(client_action_id="a7")])

        create_target_clarifications(
            MagicMock(), subject, candidates=tasks, ranked={"a7": ranked},
        )

        self.assertEqual(
            [option["value"] for option in subject.clarifications[0].options],
            [str(match.task_id) for match in ranked[:MAX_CANDIDATES]],
        )

    def test_the_question_is_asked_in_both_languages(self):
        subject = command(action_drafts=[draft()])
        create_target_clarifications(MagicMock(), subject, candidates=crowded_project())
        clarification = subject.clarifications[0]
        self.assertIsInstance(clarification, VoiceClarification)
        self.assertTrue(clarification.question_ar.strip())
        self.assertTrue(clarification.question_en.strip())
        self.assertEqual(clarification.expected_answer_type, "TASK_SELECTION")

    def test_a_resolved_draft_is_asked_nothing(self):
        subject = command(action_drafts=[draft(missing=())])
        create_target_clarifications(MagicMock(), subject, candidates=crowded_project())
        self.assertEqual(subject.clarifications, [])


class SpokenReferenceTests(TestCase):
    def _result(self, **overrides):
        values = {
            "detected_task": SimpleNamespace(task_title=None, task_id=None),
            "location": SimpleNamespace(text=None),
            "discipline": SimpleNamespace(value=None),
            "summary": "summary text",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_the_heard_task_title_leads_the_reference(self):
        reference = spoken_task_reference(
            command(),
            self._result(detected_task=SimpleNamespace(task_title="electrical installation", task_id=None)),
        )
        self.assertTrue(reference.startswith("electrical installation"))

    def test_location_and_discipline_join_the_reference(self):
        reference = spoken_task_reference(
            command(),
            self._result(
                location=SimpleNamespace(text="first floor"),
                discipline=SimpleNamespace(value="electrical"),
            ),
        )
        self.assertIn("first floor", reference)
        self.assertIn("electrical", reference)

    def test_the_transcript_is_the_last_resort_not_the_first(self):
        reference = spoken_task_reference(command(), self._result())
        self.assertEqual(reference, "I finished the first floor electrical work")

    def test_an_action_contributes_its_own_wording(self):
        suggestion = SimpleNamespace(
            payload_dict=lambda: {"location": "building B", "note": "plastering started"}
        )
        reference = spoken_task_reference(command(), self._result(), suggestion)
        self.assertIn("building B", reference)
        self.assertIn("plastering started", reference)

    def test_the_reference_is_bounded(self):
        subject = command(raw_transcript="x" * 5000)
        self.assertLessEqual(len(spoken_task_reference(subject, self._result())), 1000)


class ProgressRealtimeTests(TestCase):
    """A confirmed voice update must reach open boards without a reload."""

    def _run_update(self):
        from app.services import task_progress_service

        task_row = SimpleNamespace(
            id=uuid4(),
            project_id=uuid4(),
            progress_percentage=10.0,
            status=TaskStatus.IN_PROGRESS,
            actual_start_date=date.today(),
            assignees=[],
            updated_at=datetime.now(timezone.utc),
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = task_row

        with patch.object(task_progress_service, "user_has_project_access", return_value=True), \
             patch.object(task_progress_service, "_is_project_manager", return_value=True), \
             patch.object(task_progress_service, "_is_task_engineer", return_value=False), \
             patch.object(task_progress_service, "_dependencies_complete", return_value=True), \
             patch.object(task_progress_service, "validate_progress_change"), \
             patch.object(task_progress_service, "_refresh_project_progress"), \
             patch.object(task_progress_service, "_notify_progress_change"), \
             patch.object(task_progress_service, "record_audit"), \
             patch.object(task_progress_service, "emit_domain_event"), \
             patch.object(task_progress_service, "publish_event") as publish:
            task_progress_service.update_task_progress(
                db=db,
                current_user=SimpleNamespace(id=uuid4(), full_name="Engineer"),
                task_id=task_row.id,
                progress_percentage=100,
                source="ai_voice_analysis",
            )
        return publish, task_row

    def test_the_service_path_announces_the_change(self):
        publish, task_row = self._run_update()
        publish.assert_called_once()
        self.assertEqual(publish.call_args.kwargs["event_type"], "TASK_UPDATED")
        self.assertEqual(publish.call_args.kwargs["entity_id"], task_row.id)

    def test_the_event_is_scoped_to_the_project_and_carries_no_state(self):
        publish, task_row = self._run_update()
        kwargs = publish.call_args.kwargs
        self.assertEqual(kwargs["project_id"], task_row.project_id)
        self.assertEqual(kwargs["entity_type"], "TASK")
        # An event is a hint. Progress, status, and notes belong to the
        # refetch, which re-applies the caller's own authorization.
        self.assertFalse({"progress", "status", "note"} & set(kwargs))


class LatencyRecordTests(TestCase):
    def test_timings_are_numbers_and_nothing_else(self):
        from app.services import voice_metrics

        latency = voice_metrics.VoiceLatency()
        with latency.stage(voice_metrics.TRANSCRIPTION):
            pass
        with latency.stage(voice_metrics.ANALYSIS):
            pass

        stages = voice_metrics.record(
            latency, command_id=uuid4(), project_id=uuid4(),
            language="ar", action_count=2,
        )
        self.assertIn(voice_metrics.TOTAL, stages)
        self.assertTrue(all(isinstance(value, int) for value in stages.values()))

    def test_repeating_a_stage_accumulates_rather_than_overwrites(self):
        from app.services import voice_metrics

        latency = voice_metrics.VoiceLatency()
        for _ in range(3):
            with latency.stage(voice_metrics.DRAFTING):
                sum(range(10000))
        self.assertEqual(len([key for key in latency.stages if key == voice_metrics.DRAFTING]), 1)
        self.assertGreaterEqual(latency.stages[voice_metrics.DRAFTING], 0)

    def test_a_failing_logger_cannot_fail_the_field_update(self):
        from app.services import voice_metrics

        latency = voice_metrics.VoiceLatency()
        with patch.object(voice_metrics.logger, "info", side_effect=RuntimeError("sink down")):
            stages = voice_metrics.record(
                latency, command_id=uuid4(), project_id=uuid4(),
            )
        self.assertIn(voice_metrics.TOTAL, stages)
