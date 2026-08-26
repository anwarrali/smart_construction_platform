"""Talking to the assistant, rather than filling in its form.

Three behaviours are pinned here, each one a failure seen on site:

  * A missing field is a **question**, not an error. "بدي أرفع مشكلة" used to
    fail schema validation and surface as "AI analysis is temporarily
    unavailable"; it must now ask what the problem is.
  * An answer to that question **continues the request**. "المهمة السادسة" is
    meaningless alone and complete in context, and the engineer must never have
    to repeat the whole sentence.
  * Nothing reaches **review** until it is complete, and nothing internal
    reaches the engineer at any point — no field paths, no action type names,
    no intent names, no confidence numbers.

The phrasing model is deliberately absent from these tests. Every assertion
holds on the deterministic fallbacks, which is the property that makes the
feature safe to ship with the provider switched off.
"""

import asyncio
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.ai.response_composer import sanitize_facts
from app.models.enums import TaskStatus, UserStatus, VoiceAnalysisStatus
from app.schemas.voice_analysis import (
    ConstructionVoiceResult,
    DetectedDiscipline,
    DetectedLocation,
    DetectedProgress,
    DetectedQuery,
    DetectedTask,
    SuggestedAction,
    SuggestedActionType,
    VoiceRequestKind,
)
from app.services import voice_command_service, voice_conversation_service
from app.services.voice_action_requirements import (
    TARGET_TASK,
    apply_answer,
    describe_understood,
    missing_fields,
)
from app.services.voice_entity_resolution import Person, match_people
from app.services.voice_language import reply_language
from app.services.voice_task_matcher import match_by_position, task_position


def task(code, name, *, status=TaskStatus.TODO, progress=0.0, discipline=None):
    return SimpleNamespace(
        id=uuid4(),
        task_code=code,
        name=name,
        description=None,
        discipline=discipline,
        status=status,
        progress_percentage=progress,
        review_required=False,
        assignees=[],
        dependencies=[],
        updated_at=SimpleNamespace(isoformat=lambda: "2026-08-25T08:00:00+00:00"),
        voice_evidence_requirements={},
    )


def project_tasks():
    """Six tasks, so "المهمة السادسة" has something to point at."""
    return [
        task("TSK-001", "Excavation", status=TaskStatus.DONE, progress=100),
        task("TSK-002", "Foundation Rebar", status=TaskStatus.IN_PROGRESS, progress=40),
        task("TSK-003", "Ground Floor Columns"),
        task("TSK-004", "Building B Plastering"),
        task("TSK-005", "Roof Waterproofing", status=TaskStatus.DONE, progress=100),
        task("TSK-006", "Order electrical materials", discipline="electrical"),
    ]


def result(**overrides):
    values = {
        "summary": "spoken content",
        "detected_task": DetectedTask(confidence=0.5),
        "progress": DetectedProgress(confidence=1.0),
        "discipline": DetectedDiscipline(value=None, confidence=0.0),
        "location": DetectedLocation(),
    }
    values.update(overrides)
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


def interpret(subject, analysis_result, tasks, *, pending=None, capable=True,
              people=None, correctable=None):
    """Run the real pipeline against in-memory rows.

    `capable` stands in for the capability registry's permission check, which
    reads the permission catalogue from the database. These cases are about
    interpretation; permission behaviour has its own tests below.
    """
    db = MagicMock()
    db.get.side_effect = lambda model, key: next(
        (item for item in tasks if getattr(item, "id", None) == key), None
    )
    with patch.object(
        voice_command_service, "authorized_voice_tasks", return_value=tasks
    ), patch.object(
        voice_command_service, "is_available", return_value=capable
    ), patch.object(
        # The registry reads the permission catalogue from the database; these
        # cases are about interpretation, so it offers nothing and the neutral
        # question stands on its own words.
        voice_command_service, "available_capabilities", return_value=[]
    ), patch.object(
        voice_command_service, "project_people", return_value=list(people or [])
    ), patch.object(
        # Assignment resolves against the people who may actually hold work,
        # which is a narrower database read than the whole team. These cases
        # are about interpretation, so both lists are the supplied people.
        voice_command_service, "assignable_people", return_value=list(people or [])
    ), patch.object(
        voice_command_service, "project_owner", return_value=None
    ), patch.object(
        voice_command_service, "authorized_issues", return_value=[]
    ), patch.object(
        voice_command_service.voice_conversation_service,
        "find_open_request",
        return_value=pending,
    ), patch.object(
        voice_command_service.voice_conversation_service,
        "find_correctable_request",
        return_value=correctable,
    ):
        voice_command_service.interpret_command(
            db, command=subject, result=analysis_result,
            user=SimpleNamespace(id=uuid4(), role=SimpleNamespace(value="engineer")),
        )
    return subject


class MissingInformationTests(TestCase):
    """An unsaid field produces a question, never a failure."""

    def test_an_issue_with_nothing_in_it_asks_what_the_problem_is(self):
        subject = interpret(
            command(raw_transcript="بدي أرفع مشكلة عن شغل اليوم"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="wants to report an issue",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.CREATE_ISSUE,
                    reason="Engineer wants to record a problem",
                    payload={},
                    confidence=0.9,
                )],
            ),
            project_tasks(),
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        self.assertEqual(len(subject.clarifications), 1)
        question = subject.clarifications[0]
        self.assertEqual(question.field_path, "payload.issue")
        self.assertTrue(question.question_ar.strip())
        self.assertTrue(question.question_en.strip())

    def test_a_progress_update_with_no_task_asks_which_task(self):
        subject = interpret(
            command(raw_transcript="خلصنا نص الشغل"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="half the work is done",
                progress=DetectedProgress(
                    mentioned=True, percentage=50, approximate=True, confidence=0.8
                ),
            ),
            project_tasks(),
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        self.assertEqual(subject.clarifications[0].field_path, TARGET_TASK)
        # The percentage it did hear is kept, so answering "المهمة السادسة"
        # completes the request instead of restarting it.
        draft = subject.action_drafts[0]
        self.assertEqual(draft.extracted_payload["progressPercentage"], 50.0)

    def test_an_incomplete_request_never_reaches_review(self):
        subject = interpret(
            command(raw_transcript="بدي أرفع تقرير موقع عن شغل اليوم"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="wants a site report",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.CREATE_SITE_REPORT_DRAFT,
                    reason="Engineer asked for a site report",
                    payload={},
                    confidence=0.9,
                )],
            ),
            project_tasks(),
        )
        self.assertNotEqual(
            subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION
        )
        self.assertTrue(subject.action_drafts[0].missing_fields)

    def test_the_outstanding_question_is_the_spoken_reply(self):
        subject = interpret(
            command(raw_transcript="بدي أرفع مشكلة"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="wants to report an issue",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.CREATE_ISSUE,
                    reason="Engineer wants to record a problem",
                    payload={},
                    confidence=0.9,
                )],
            ),
            project_tasks(),
        )
        answer = subject.structured_result["answer"]
        self.assertEqual(answer["language"], "ar")
        self.assertEqual(answer["text"], subject.clarifications[0].question_ar)

    def test_a_complete_request_still_goes_straight_to_review(self):
        tasks = project_tasks()
        subject = interpret(
            command(raw_transcript="خلصت نص المهمة السادسة"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="task six is half done",
                progress=DetectedProgress(
                    mentioned=True, percentage=50, approximate=True, confidence=0.9
                ),
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.UPDATE_TASK_PROGRESS,
                    reason="Progress stated for task six",
                    target_id=tasks[5].id,
                    payload={"progressPercentage": 50},
                    confidence=0.9,
                )],
            ),
            tasks,
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
        self.assertEqual(subject.action_drafts[0].target_entity_id, tasks[5].id)
        self.assertEqual(subject.clarifications, [])


class RequirementTableTests(TestCase):
    def test_each_action_reports_only_what_it_actually_needs(self):
        self.assertEqual(
            missing_fields(SuggestedActionType.CREATE_ISSUE, {}, has_target=False),
            ["payload.issue"],
        )
        self.assertEqual(
            missing_fields(
                SuggestedActionType.CREATE_ISSUE,
                {"title": "Materials did not arrive"},
                has_target=False,
            ),
            [],
        )
        self.assertEqual(
            missing_fields(
                SuggestedActionType.UPDATE_TASK_PROGRESS, {}, has_target=False
            ),
            [TARGET_TASK, "payload.progressPercentage"],
        )

    def test_one_spoken_sentence_fills_both_halves_of_an_issue(self):
        payload = apply_answer("payload.issue", {}, "المواد الكهربائية ما وصلت")
        self.assertEqual(payload["title"], "المواد الكهربائية ما وصلت")
        self.assertEqual(payload["description"], "المواد الكهربائية ما وصلت")

    def test_what_is_understood_is_described_in_words_not_field_names(self):
        described = describe_understood(
            SuggestedActionType.UPDATE_TASK_PROGRESS,
            {"progressPercentage": 50},
            task_label="TSK-006 — Order electrical materials",
        )
        self.assertIn("update how far along a task is", described.values())
        self.assertNotIn("UPDATE_TASK_PROGRESS", str(described))
        self.assertNotIn("progressPercentage", str(described))


class PositionalReferenceTests(TestCase):
    def test_an_ordinal_names_the_task_at_that_position(self):
        tasks = project_tasks()
        self.assertIs(match_by_position("المهمة السادسة", tasks), tasks[5])
        self.assertIs(match_by_position("task 6", tasks), tasks[5])
        self.assertIs(match_by_position("السادسة", tasks), tasks[5])

    def test_a_floor_is_not_a_task(self):
        self.assertIsNone(task_position("الطابق السادس"))

    def test_a_position_past_the_end_of_the_list_resolves_to_nothing(self):
        self.assertIsNone(match_by_position("المهمة العاشرة", project_tasks()))


class ContinuationTests(TestCase):
    """The answer to a question completes the request that asked it."""

    def _pending(self, tasks, *, missing=(TARGET_TASK,), payload=None,
                 action=SuggestedActionType.UPDATE_TASK_PROGRESS):
        draft = SimpleNamespace(
            id=uuid4(),
            client_action_id="a1",
            action_type=action.value,
            target_entity_id=None,
            target_snapshot=None,
            extracted_payload=payload if payload is not None else {"progressPercentage": 50},
            user_edited_payload=None,
            confidence=0.8,
            risk_level="MEDIUM",
            required_evidence=[],
            warnings=[],
            missing_fields=list(missing),
        )
        return command(
            raw_transcript="خلصنا نص الشغل",
            status=VoiceAnalysisStatus.NEEDS_CLARIFICATION,
            action_drafts=[draft],
        )

    def test_an_ordinal_answer_completes_the_earlier_progress_update(self):
        tasks = project_tasks()
        pending = self._pending(tasks)
        subject = interpret(
            command(raw_transcript="المهمة السادسة"),
            result(request_kind=VoiceRequestKind.ACTION, summary="task six"),
            tasks,
            pending=pending,
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
        draft = subject.action_drafts[0]
        self.assertEqual(draft.action_type, "UPDATE_TASK_PROGRESS")
        self.assertEqual(draft.target_entity_id, tasks[5].id)
        # The percentage from the *first* utterance survives, which is the whole
        # point: the engineer said it once.
        self.assertEqual(draft.extracted_payload["progressPercentage"], 50)
        self.assertEqual(pending.status, VoiceAnalysisStatus.CANCELLED)

    def test_a_described_problem_completes_the_earlier_issue(self):
        tasks = project_tasks()
        pending = self._pending(
            tasks, missing=("payload.issue",), payload={},
            action=SuggestedActionType.CREATE_ISSUE,
        )
        subject = interpret(
            command(raw_transcript="المواد الكهربائية ما وصلت"),
            result(request_kind=VoiceRequestKind.STATEMENT, summary="materials late"),
            tasks,
            pending=pending,
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
        self.assertEqual(
            subject.action_drafts[0].extracted_payload["title"],
            "المواد الكهربائية ما وصلت",
        )

    def test_an_unrelated_question_leaves_the_pending_request_alone(self):
        tasks = project_tasks()
        pending = self._pending(tasks)
        subject = interpret(
            command(raw_transcript="شو المهام اللي لسه ضايلة؟"),
            result(
                request_kind=VoiceRequestKind.QUESTION,
                summary="what is left",
                query=DetectedQuery(topic="REMAINING_TASKS", confidence=0.9),
            ),
            tasks,
            pending=pending,
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.COMPLETED)
        self.assertEqual(subject.action_drafts, [])
        self.assertEqual(pending.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)

    def test_a_question_is_never_matched_against_the_open_request(self):
        """A read asked mid-flow is a read.

        Without this the question's own words are scored against the project's
        tasks to fill the open request's missing target, and a question about
        the electrical work would silently answer "which task?" with a task.
        """
        tasks = project_tasks()
        pending = self._pending(tasks)
        subject = interpret(
            command(raw_transcript="شو وضع مهمة المواد الكهربائية؟"),
            result(
                request_kind=VoiceRequestKind.QUESTION,
                summary="status of the electrical materials task",
                query=DetectedQuery(
                    topic="TASK_STATUS",
                    task_reference="المواد الكهربائية",
                    confidence=0.9,
                ),
            ),
            tasks,
            pending=pending,
        )
        self.assertEqual(subject.action_drafts, [])
        self.assertEqual(pending.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        self.assertTrue(pending.action_drafts[0].missing_fields)

    def test_a_new_instruction_supersedes_an_abandoned_question(self):
        tasks = project_tasks()
        pending = self._pending(tasks)
        subject = interpret(
            command(raw_transcript="ابدأ مهمة أعمدة الطابق الأرضي"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="start the columns",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.START_TASK,
                    reason="Explicit instruction",
                    target_id=tasks[2].id,
                    payload={},
                    confidence=0.9,
                )],
            ),
            tasks,
            pending=pending,
        )
        self.assertTrue(subject.action_drafts)
        self.assertEqual(pending.status, VoiceAnalysisStatus.CANCELLED)


class RecipientResolutionTests(TestCase):
    """A person is resolved against the project's team, or asked about."""

    people = [
        Person(uuid4(), "Layla Haddad", "engineer"),
        Person(uuid4(), "Omar Sabbagh", "project_manager"),
        Person(uuid4(), "Rami Khalil", "engineer"),
    ]

    def test_a_spoken_name_finds_one_person(self):
        matched = match_people("ابعتها لعمر صباغ", [
            Person(self.people[1].user_id, "عمر صباغ", "project_manager"), *self.people,
        ])
        self.assertEqual([person.name for person in matched], ["عمر صباغ"])

    def test_a_role_word_finds_everyone_holding_it(self):
        matched = match_people("للمهندسين", self.people)
        self.assertEqual(
            sorted(person.name for person in matched),
            ["Layla Haddad", "Rami Khalil"],
        )

    def test_a_name_nobody_has_resolves_to_nobody(self):
        self.assertEqual(match_people("للمقاول الخارجي", self.people), [])


class NoSilentStateTests(TestCase):
    """Every input leaves something on the screen.

    The bug these defend against: an engineer says "في تأخير في وصول المواد
    لمهمة اليوم", is asked to clarify, answers "المواد الكهربائية تأخرت" — and
    the screen goes blank. The clarification was attached to no draft, so the
    answer had no field to go into; it was recorded and never read. The command
    then carried no unanswered question, no proposal and a stale reply, which
    is three cards' worth of nothing.
    """

    def _clarified(self, *, drafts=(), clarifications=(), answer=None):
        return command(
            raw_transcript="في تأخير في وصول المواد لمهمة اليوم",
            status=VoiceAnalysisStatus.NEEDS_CLARIFICATION,
            action_drafts=list(drafts),
            clarifications=list(clarifications),
            structured_result={"answer": answer} if answer else {},
        )

    def test_a_command_with_nothing_to_show_is_detected(self):
        answered = SimpleNamespace(
            answer_text="المواد الكهربائية تأخرت",
            question_ar="ما فهمت قصدك",
            question_en="I did not catch that",
        )
        # An answered question renders nothing on its own: the card that
        # carried it is gone the moment it has an answer. With no draft and no
        # reply beside it, that is a blank screen.
        self.assertFalse(
            voice_command_service.renders_something(
                self._clarified(clarifications=[answered])
            )
        )

    def test_the_fallback_reply_is_added_rather_than_leaving_a_blank_screen(self):
        subject = self._clarified()
        voice_command_service.ensure_visible_state(subject, language="ar")
        text = subject.structured_result["answer"]["text"]
        self.assertTrue(text.strip())
        self.assertEqual(subject.structured_result["answer"]["language"], "ar")
        # A sentence about this exchange, not about the system.
        for internal in ("None", "null", "Exception", "500", "status"):
            self.assertNotIn(internal, text)

    def test_a_command_that_already_says_something_is_left_alone(self):
        for subject in (
            self._clarified(answer={"text": "المشروع منجز 45%.", "language": "ar"}),
            self._clarified(clarifications=[SimpleNamespace(
                answer_text=None, question_ar="أي مهمة؟", question_en="Which task?",
            )]),
            self._clarified(drafts=[SimpleNamespace(missing_fields=[])]),
        ):
            self.assertTrue(voice_command_service.renders_something(subject))
            before = dict(subject.structured_result)
            voice_command_service.ensure_visible_state(subject, language="ar")
            self.assertEqual(subject.structured_result, before)

    def test_interpretation_never_returns_a_silent_command(self):
        """Even when every path declines to say anything."""
        tasks = project_tasks()
        subject = command(raw_transcript="مممم")
        with patch.object(
            voice_command_service, "_route_command", return_value=None
        ):
            interpret(subject, result(summary="unintelligible"), tasks)
        self.assertTrue(voice_command_service.renders_something(subject))

    def test_an_answer_with_no_draft_asks_the_caller_to_re_interpret(self):
        """The signal that drives the fix, at the seam where it is produced."""
        db = MagicMock()
        db.get.return_value = None
        question = SimpleNamespace(
            id=uuid4(),
            voice_analysis_id=None,
            voice_action_draft_id=None,
            field_path="intent",
            expected_answer_type="TEXT",
            answer_text=None,
            answer_source=None,
            answered_at=None,
        )
        subject = self._clarified(clarifications=[question])
        subject.user_id = uuid4()
        question.voice_analysis_id = subject.id
        user = SimpleNamespace(
            id=subject.user_id, status=UserStatus.ACTIVE,
            role=SimpleNamespace(value="engineer"),
        )
        with patch.object(
            voice_command_service, "assert_command_access", return_value=None
        ), patch.object(
            voice_command_service, "authorized_voice_tasks", return_value=[]
        ), patch.object(voice_command_service, "record_audit", return_value=None):
            needs_interpretation = voice_command_service.answer_clarification(
                db, command=subject, clarification=question,
                answer="المواد الكهربائية تأخرت.", user=user,
            )
        self.assertTrue(needs_interpretation)
        self.assertEqual(question.answer_text, "المواد الكهربائية تأخرت.")


class ClarifiedRequestNeverEndsInSilence(TestCase):
    """The endpoint path that re-reads a request together with its answer."""

    def _pending(self):
        subject = command(
            raw_transcript="في تأخير في وصول المواد لمهمة اليوم",
            status=VoiceAnalysisStatus.NEEDS_CLARIFICATION,
            provider_metadata={"replyLanguage": "ar"},
        )
        subject.task_id = None
        subject.detected_language = None
        return subject

    def test_a_provider_failure_still_leaves_a_sentence_on_the_screen(self):
        """An outage is a sentence, never a blank card and never a stack trace."""
        from app.ai.exceptions import AIProviderError
        from app.api import voice as voice_api

        subject = self._pending()
        db = MagicMock()
        db.get.return_value = subject
        with patch.object(
            voice_api.VoiceContextBuilder, "build", return_value={"tasks": []}
        ), patch.object(
            voice_api.ConstructionVoiceAnalysisService, "analyze",
            side_effect=AIProviderError("provider down"),
        ):
            asyncio.run(voice_api._interpret_clarified_request(
                db, command=subject,
                user=SimpleNamespace(
                    id=uuid4(), role=SimpleNamespace(value="engineer"),
                    engineer_affiliation=None,
                ),
                original="في تأخير في وصول المواد لمهمة اليوم",
                answer="المواد الكهربائية تأخرت.",
            ))
        answer = subject.structured_result["answer"]
        self.assertTrue(answer["text"].strip())
        self.assertEqual(answer["language"], "ar")
        # Nothing technical reaches the person.
        for internal in ("provider", "AIProviderError", "500", "Traceback"):
            self.assertNotIn(internal, answer["text"])
        self.assertTrue(voice_command_service.renders_something(subject))


class LanguageTests(TestCase):
    def test_the_reply_follows_the_speaker_not_the_interface(self):
        self.assertEqual(reply_language("شو نسبة تقدم المشروع؟"), "ar")
        self.assertEqual(reply_language("What is the project progress?"), "en")
        # An Arabic sentence carrying English technical terms is still Arabic.
        self.assertEqual(reply_language("شو وضع الـHVAC ductwork؟"), "ar")

    def test_an_english_question_is_answered_in_english(self):
        subject = interpret(
            command(raw_transcript="Which tasks are still open?"),
            result(
                request_kind=VoiceRequestKind.QUESTION,
                summary="open tasks",
                query=DetectedQuery(topic="REMAINING_TASKS", confidence=0.9),
            ),
            project_tasks(),
        )
        answer = subject.structured_result["answer"]
        self.assertEqual(answer["language"], "en")
        self.assertIn("Ground Floor Columns", answer["text"])


class NothingInternalLeaksTests(TestCase):
    def test_identifiers_and_bookkeeping_never_reach_the_phrasing_model(self):
        facts = sanitize_facts({
            "taskId": str(uuid4()),
            "taskCode": "TSK-006",
            "confidence": 0.42,
            "topic": "PROJECT_PROGRESS",
            "openTasks": [{"taskId": str(uuid4()), "name": "Order electrical materials"}],
        })
        self.assertEqual(
            facts,
            {"taskCode": "TSK-006", "openTasks": [{"name": "Order electrical materials"}]},
        )

    def test_a_question_the_data_cannot_answer_says_so_without_internals(self):
        subject = interpret(
            command(raw_transcript="شو موعد التسليم النهائي؟"),
            result(
                request_kind=VoiceRequestKind.QUESTION,
                summary="delivery date",
                query=DetectedQuery(topic="UNKNOWN", confidence=0.4),
            ),
            project_tasks(),
        )
        text = subject.structured_result["answer"]["text"]
        for internal in ("UNKNOWN", "topic", "intent", "None", "null"):
            self.assertNotIn(internal, text)
