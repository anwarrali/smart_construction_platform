"""Questions must be answered, not converted into actions.

Every case here comes from manual site testing where the assistant took a
sentence that asked for information and produced a mutation proposal — usually
`ADD_TASK_NOTE` built from the raw transcript, followed by "which task do you
mean?". The rule these tests defend is narrow and absolute: *mentioning* a task
is not *asking to change* a task.

The mirror-image rule matters just as much and is tested alongside: everything
that really is a mutation still goes through drafts and confirmation, unchanged.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.enums import TaskStatus, VoiceAnalysisStatus
from app.schemas.voice_analysis import (
    ConstructionVoiceResult,
    DetectedLocation,
    DetectedProgress,
    DetectedQuery,
    DetectedTask,
    SuggestedAction,
    SuggestedActionType,
    VoiceIntent,
    VoiceQueryTopic,
    VoiceRequestKind,
)
from app.services import voice_command_service
from app.services.voice_query_service import answer_query


def task(code, name, *, status=TaskStatus.TODO, progress=0.0, discipline=None,
         dependencies=(), assignees=(), review_required=False, description=None):
    return SimpleNamespace(
        id=uuid4(),
        task_code=code,
        name=name,
        description=description,
        discipline=discipline,
        status=status,
        progress_percentage=progress,
        review_required=review_required,
        assignees=list(assignees),
        dependencies=list(dependencies),
    )


def depends_on(other):
    return SimpleNamespace(depends_on_task_id=other.id, depends_on_task=other)


def project_tasks():
    excavation = task("TSK-001", "Excavation", status=TaskStatus.DONE, progress=100,
                      discipline="civil")
    foundation = task("TSK-002", "Foundation Rebar", status=TaskStatus.IN_PROGRESS,
                      progress=40, discipline="civil")
    columns = task("TSK-003", "Ground Floor Columns", status=TaskStatus.TODO,
                   discipline="civil")
    columns.dependencies = [depends_on(foundation)]
    plastering = task("TSK-004", "Building B Plastering", status=TaskStatus.TODO)
    fifth = task("TSK-005", "Roof Waterproofing", status=TaskStatus.DONE, progress=100)
    return [excavation, foundation, columns, plastering, fifth]


def result(**overrides):
    values = {
        "summary": "spoken content",
        "detected_task": DetectedTask(confidence=0.5),
        "progress": DetectedProgress(confidence=1.0),
        "discipline": SimpleNamespace(value=None, confidence=0.0),
        "location": DetectedLocation(),
    }
    values.update(overrides)
    # `discipline` must be the real model for validation; build via the schema.
    from app.schemas.voice_analysis import DetectedDiscipline
    if not hasattr(values["discipline"], "model_dump"):
        values["discipline"] = DetectedDiscipline(value=None, confidence=0.0)
    return ConstructionVoiceResult(**values)


def command(**overrides):
    values = {
        "id": uuid4(),
        "project_id": uuid4(),
        "task_id": None,
        "raw_transcript": "",
        "normalized_transcript": None,
        "detected_language": None,
        "structured_result": {},
        "provider_metadata": {},
        "status": VoiceAnalysisStatus.ANALYZING,
        "row_version": 1,
        "action_drafts": [],
        "clarifications": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class QueryAnsweringTests(TestCase):
    """The read path: answer from data, propose nothing, confirm nothing."""

    def test_task_status_question_is_answered_from_the_record(self):
        tasks = project_tasks()
        answer = answer_query(
            MagicMock(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.TASK_STATUS,
                                task_reference="excavation", confidence=0.9),
            tasks=tasks,
        )
        self.assertIsNotNone(answer)
        self.assertIn("100", answer.text_en)
        self.assertIn("done", answer.text_en.lower())
        self.assertIn("TSK-001", answer.text_en)

    def test_the_arabic_answer_carries_the_same_facts(self):
        answer = answer_query(
            MagicMock(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.TASK_STATUS,
                                task_reference="excavation", confidence=0.9),
            tasks=project_tasks(),
        )
        self.assertIn("100", answer.text_ar)
        self.assertIn("مكتملة", answer.text_ar)

    def test_remaining_work_is_a_project_question_and_never_asks_for_a_task(self):
        answer = answer_query(
            MagicMock(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.REMAINING_TASKS, confidence=0.9),
            tasks=project_tasks(),
        )
        self.assertTrue(answer.is_answered)
        self.assertEqual(answer.candidates, [])
        self.assertEqual(answer.data["count"], 3)

    def test_next_task_respects_dependencies_rather_than_row_order(self):
        tasks = project_tasks()
        answer = answer_query(
            MagicMock(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.NEXT_TASK, confidence=0.9),
            tasks=tasks,
        )
        # Columns depend on Foundation Rebar, which is not Done, so the next
        # task ready to start is the unblocked one.
        self.assertIn("TSK-004", answer.text_en)
        self.assertNotIn("TSK-003", answer.text_en)

    def test_blockers_question_explains_what_is_in_the_way(self):
        tasks = project_tasks()
        answer = answer_query(
            MagicMock(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.TASK_BLOCKERS,
                                task_reference="ground floor columns", confidence=0.9),
            tasks=tasks,
        )
        self.assertIn("TSK-002", answer.text_en)
        self.assertEqual(len(answer.data["blockers"]), 1)

    def test_an_unblocked_task_says_so_instead_of_inventing_a_blocker(self):
        answer = answer_query(
            MagicMock(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.TASK_BLOCKERS,
                                task_reference="building B plastering", confidence=0.9),
            tasks=project_tasks(),
        )
        self.assertEqual(answer.data["blockers"], [])
        self.assertIn("Nothing is blocking", answer.text_en)

    def test_an_ambiguous_task_question_offers_candidates_not_a_wrong_answer(self):
        tasks = [
            task("EL-101", "First Floor Electrical Installation"),
            task("EL-102", "First Floor Electrical Fixtures"),
            task("EL-103", "First Floor Electrical Inspection"),
        ]
        answer = answer_query(
            MagicMock(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.TASK_STATUS,
                                task_reference="electrical", confidence=0.9),
            tasks=tasks,
        )
        self.assertFalse(answer.is_answered)
        self.assertTrue(answer.candidates)
        self.assertLessEqual(len(answer.candidates), 5)

    def test_an_unclassified_question_is_not_answered_by_guesswork(self):
        self.assertIsNone(answer_query(
            MagicMock(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.UNKNOWN, confidence=0.2),
            tasks=project_tasks(),
        ))


class RoutingTests(TestCase):
    """`interpret_command` must send reads and writes down different paths."""

    def _run(self, analysis_result, tasks, subject=None):
        subject = subject or command()
        with patch.object(voice_command_service, "authorized_voice_tasks", return_value=tasks), \
             patch.object(
                 # The neutral question offers what this speaker could do about
                 # what they said; the registry reads that from the database,
                 # and these cases run on a Mock session with a stand-in user.
                 voice_command_service, "available_capabilities", return_value=[],
             ), \
             patch.object(voice_command_service, "build_action_drafts") as drafts:
            voice_command_service.interpret_command(
                MagicMock(), command=subject, result=analysis_result,
                user=SimpleNamespace(id=uuid4(), role=SimpleNamespace(value="engineer")),
            )
        return subject, drafts

    def test_a_question_never_reaches_the_action_pipeline(self):
        subject, drafts = self._run(
            result(
                request_kind=VoiceRequestKind.QUESTION,
                query=DetectedQuery(topic=VoiceQueryTopic.REMAINING_TASKS, confidence=0.9),
            ),
            project_tasks(),
        )
        drafts.assert_not_called()
        self.assertEqual(subject.status, VoiceAnalysisStatus.COMPLETED)
        self.assertEqual(subject.action_drafts, [])

    def test_an_answered_question_needs_no_confirmation(self):
        subject, _ = self._run(
            result(
                request_kind=VoiceRequestKind.QUESTION,
                query=DetectedQuery(topic=VoiceQueryTopic.PROJECT_PROGRESS, confidence=0.9),
            ),
            project_tasks(),
        )
        # COMPLETED, not READY_FOR_CONFIRMATION: there is nothing to confirm.
        self.assertNotEqual(subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
        self.assertIn("answer", subject.structured_result)
        self.assertTrue(subject.structured_result["answer"]["textEn"])

    def test_an_unanswerable_question_says_so_instead_of_proposing_anything(self):
        # Previously this fell through to the action pipeline, which is how
        # "شو ضايل علينا مهام؟" ended at a task picker. A question the system
        # cannot answer is still a question.
        subject, drafts = self._run(
            result(
                request_kind=VoiceRequestKind.QUESTION,
                query=DetectedQuery(topic=VoiceQueryTopic.UNKNOWN, confidence=0.1),
            ),
            project_tasks(),
        )
        drafts.assert_not_called()
        self.assertEqual(subject.status, VoiceAnalysisStatus.COMPLETED)
        self.assertEqual(subject.structured_result["answer"]["topic"], "UNANSWERED")

    def test_an_action_still_goes_through_drafts_and_confirmation(self):
        _, drafts = self._run(
            result(
                request_kind=VoiceRequestKind.ACTION,
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.CREATE_ISSUE,
                    reason="Rain delay reported",
                    confidence=0.93,
                    payload={"title": "Rain delay", "description": "Work stopped by rain"},
                )],
            ),
            project_tasks(),
        )
        drafts.assert_called_once()

    def test_an_unclassifiable_utterance_asks_neutrally_and_proposes_nothing(self):
        # Zero actions never means "add a note", and it never means "would you
        # like to add a note or report an issue?" either — that question showed
        # an engineer two mutations they had not asked for.
        subject, drafts = self._run(result(), project_tasks())
        drafts.assert_not_called()
        self.assertEqual(subject.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        question = subject.clarifications[0]
        for word in ("note", "issue", "ملاحظة", "مشكلة"):
            self.assertNotIn(word, question.question_en + question.question_ar)

    def test_a_proposed_action_still_reaches_drafts_and_confirmation(self):
        # The mirror-image guarantee: real mutations are untouched.
        _, drafts = self._run(
            result(suggested_actions=[SuggestedAction(
                type=SuggestedActionType.START_TASK,
                target_id=uuid4(),
                reason="Explicit start",
                confidence=0.9,
            )]),
            project_tasks(),
        )
        drafts.assert_called_once()


class ContradictionTests(TestCase):
    """A statement that disagrees with the record becomes a question."""

    def test_stopped_versus_recorded_complete_asks_instead_of_recording(self):
        tasks = project_tasks()
        subject = command(raw_transcript="المهمة الخامسة متوقفة")
        with patch.object(voice_command_service, "authorized_voice_tasks", return_value=tasks), \
             patch.object(
                 # The neutral question offers what this speaker could do about
                 # what they said; the registry reads that from the database,
                 # and these cases run on a Mock session with a stand-in user.
                 voice_command_service, "available_capabilities", return_value=[],
             ), \
             patch.object(voice_command_service, "build_action_drafts") as drafts:
            voice_command_service.interpret_command(
                MagicMock(),
                command=subject,
                result=result(
                    request_kind=VoiceRequestKind.STATEMENT,
                    detected_intents=[VoiceIntent.PAUSE_TASK],
                    detected_task=DetectedTask(confidence=0.9, task_title="Roof Waterproofing"),
                ),
                user=SimpleNamespace(id=uuid4(), role=SimpleNamespace(value="engineer")),
            )
        drafts.assert_not_called()
        self.assertEqual(subject.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        question = subject.clarifications[0]
        self.assertIn("100", question.question_en)
        self.assertIn("متوقفة", question.question_ar)

    def test_a_statement_matching_the_record_is_left_to_the_normal_path(self):
        tasks = project_tasks()
        subject = command(raw_transcript="foundation rebar is in progress")
        with patch.object(voice_command_service, "authorized_voice_tasks", return_value=tasks), \
             patch.object(
                 # The neutral question offers what this speaker could do about
                 # what they said; the registry reads that from the database,
                 # and these cases run on a Mock session with a stand-in user.
                 voice_command_service, "available_capabilities", return_value=[],
             ), \
             patch.object(voice_command_service, "build_action_drafts") as drafts:
            voice_command_service.interpret_command(
                MagicMock(),
                command=subject,
                result=result(
                    request_kind=VoiceRequestKind.STATEMENT,
                    detected_intents=[VoiceIntent.PAUSE_TASK],
                    detected_task=DetectedTask(confidence=0.9, task_title="Foundation Rebar"),
                ),
                user=SimpleNamespace(id=uuid4(), role=SimpleNamespace(value="engineer")),
            )
        # No contradiction to raise, and the model proposed nothing, so the
        # reply is a neutral question rather than an invented note.
        drafts.assert_not_called()
        self.assertEqual(subject.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)


class ApproximateProgressTests(TestCase):
    def test_an_inferred_percentage_is_marked_approximate(self):
        progress = DetectedProgress(
            mentioned=True, percentage=50, approximate=True, confidence=0.8
        )
        self.assertTrue(progress.approximate)
        self.assertEqual(progress.percentage, 50)

    def test_an_unmentioned_progress_clears_both_fields(self):
        progress = DetectedProgress(
            mentioned=False, percentage=95, approximate=True, confidence=0.4
        )
        self.assertIsNone(progress.percentage)
        self.assertFalse(progress.approximate)

    def test_a_vague_statement_can_carry_no_percentage_at_all(self):
        # "خلص تقريباً كله" — mentioned, but no defensible number.
        progress = DetectedProgress(mentioned=True, percentage=None, confidence=0.5)
        self.assertIsNone(progress.percentage)


class ReasoningTests(TestCase):
    """Explanations combine facts; they never propose a mutation.

    "ليش ما بنقدر نبدأ؟" cannot be answered by reading one column. These tests
    pin that the answer reaches for the dependency graph, the open issues and
    the schedule together, and that wanting an explanation never turns into a
    proposal to change something.
    """

    def _issue_query(self, count=0):
        db = MagicMock()
        issues = [
            SimpleNamespace(id=uuid4(), title=f"Issue {index}", severity="high")
            for index in range(count)
        ]
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = issues
        return db

    def test_why_blocked_names_the_dependency_that_is_in_the_way(self):
        answer = answer_query(
            self._issue_query(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.WHY_BLOCKED, confidence=0.9),
            tasks=project_tasks(),
        )
        # Ground Floor Columns waits on Foundation Rebar.
        self.assertIn("TSK-003", answer.text_en)
        self.assertIn("TSK-002", answer.text_en)
        self.assertEqual(answer.data["blockedCount"], 1)

    def test_why_blocked_folds_open_issues_into_the_explanation(self):
        answer = answer_query(
            self._issue_query(count=2), user=SimpleNamespace(id=uuid4()),
            project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.WHY_DELAYED, confidence=0.9),
            tasks=project_tasks(),
        )
        self.assertIn("Issue 0", answer.text_en)
        self.assertEqual(answer.data["openIssueCount"], 2)

    def test_an_explanation_ends_with_something_actionable(self):
        answer = answer_query(
            self._issue_query(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.WHY_BLOCKED, confidence=0.9),
            tasks=project_tasks(),
        )
        # Naming the task to finish first, not "resolve your blockers".
        self.assertIn("unblock", answer.text_en.lower())

    def test_a_clear_project_says_so_rather_than_inventing_a_cause(self):
        clear = [
            task("A-1", "Site Setup", status=TaskStatus.DONE, progress=100),
            task("A-2", "Fencing", status=TaskStatus.IN_PROGRESS, progress=30),
        ]
        answer = answer_query(
            self._issue_query(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.WHY_BLOCKED, confidence=0.9),
            tasks=clear,
        )
        self.assertIn("Nothing in the project data", answer.text_en)
        self.assertEqual(answer.data["blockedCount"], 0)

    def test_priority_focus_recommends_clearing_the_blocking_task(self):
        answer = answer_query(
            self._issue_query(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(topic=VoiceQueryTopic.PRIORITY_FOCUS, confidence=0.9),
            tasks=project_tasks(),
        )
        self.assertIn("TSK-002", answer.text_en)
        self.assertIn("TSK-002", answer.text_ar)

    def test_both_languages_are_produced(self):
        for topic in (VoiceQueryTopic.WHY_BLOCKED, VoiceQueryTopic.PRIORITY_FOCUS,
                      VoiceQueryTopic.RECOMMENDED_NEXT_STEP, VoiceQueryTopic.WHY_DELAYED):
            answer = answer_query(
                self._issue_query(), user=SimpleNamespace(id=uuid4()),
                project_id=uuid4(),
                query=DetectedQuery(topic=topic, confidence=0.9),
                tasks=project_tasks(),
            )
            self.assertTrue(answer.text_en.strip(), topic.value)
            self.assertTrue(answer.text_ar.strip(), topic.value)

    def test_reasoning_never_reaches_the_action_pipeline(self):
        from app.services import voice_command_service
        from app.schemas.voice_analysis import VoiceRequestKind

        subject = command()
        with patch.object(voice_command_service, "authorized_voice_tasks",
                          return_value=project_tasks()), \
             patch.object(voice_command_service, "build_action_drafts") as drafts, \
             patch.object(voice_command_service, "answer_query",
                          return_value=None) as answering:
            voice_command_service.interpret_command(
                MagicMock(), command=subject,
                result=result(request_kind=VoiceRequestKind.REASONING),
                user=SimpleNamespace(id=uuid4(), role=SimpleNamespace(value="engineer")),
            )
        drafts.assert_not_called()
        answering.assert_called_once()
        # Even unanswerable, it ends as a reply — not as a proposal.
        self.assertEqual(subject.status, VoiceAnalysisStatus.COMPLETED)
