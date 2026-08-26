"""Voice as an interface to the platform, not as a list of commands.

The rule this file defends: *anything a person can do through the UI, they can
ask for in their own words — and nothing else.* Both halves matter. A
capability the speaker holds must be reachable by however they phrase it; a
capability they do not hold must be refused in a sentence, not by letting them
confirm something the backend will reject a second later.

The cases are grouped by the thing that used to go wrong:

  * capabilities the registry must cover, and the permission it is bound to;
  * spoken values — dates, people, priorities — becoming real ones;
  * corrections rewriting the proposal on screen instead of stacking a second;
  * failures reaching the engineer as an explanation rather than a status code.

The phrasing model is absent throughout: every assertion holds on the
deterministic fallbacks.
"""

from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.ai.action_payload_contract import ACTION_CONTRACTS
from app.models.enums import TaskStatus, VoiceAnalysisStatus
from app.schemas.voice_analysis import (
    DetectedProgress,
    SuggestedAction,
    SuggestedActionType,
    VoiceRequestKind,
)
from app.services import voice_action_errors, voice_command_service
from app.services.voice_action_requirements import (
    TARGET_ISSUE,
    TARGET_TASK,
    issue_status_value,
    missing_fields,
    priority_value,
)
from app.services.voice_capabilities import (
    BY_ACTION,
    CAPABILITIES,
    DESTRUCTIVE,
    capability_for,
    render_catalogue,
)
from app.services.voice_dates import resolve_spoken_date
from app.services.voice_entity_resolution import Person
from tests.test_voice_conversation import command, interpret, project_tasks, result


class RegistryCoversThePlatform(TestCase):
    """Every proposable operation is described, permissioned and executable."""

    def test_every_action_type_is_a_registered_capability(self):
        for action in SuggestedActionType:
            self.assertIn(action, BY_ACTION, f"{action.value} has no capability entry")

    def test_every_capability_declares_its_payload_contract(self):
        for capability in CAPABILITIES:
            self.assertIn(capability.action, ACTION_CONTRACTS)

    def test_every_capability_teaches_the_model_how_people_ask(self):
        for capability in CAPABILITIES:
            self.assertTrue(
                capability.examples,
                f"{capability.action.value} has no spoken examples to generalize from",
            )

    def test_task_capabilities_that_change_the_plan_are_manager_only(self):
        for action in (
            SuggestedActionType.UPDATE_TASK_SCHEDULE,
            SuggestedActionType.UPDATE_TASK_ASSIGNMENT,
            SuggestedActionType.DELETE_TASK,
        ):
            self.assertEqual(capability_for(action).roles, frozenset({"project_manager"}))
            self.assertEqual(capability_for(action).permission_code, "task.edit")

    def test_deletion_is_the_only_destructive_capability_and_is_high_risk(self):
        self.assertEqual(DESTRUCTIVE, frozenset({SuggestedActionType.DELETE_TASK}))
        self.assertEqual(capability_for(SuggestedActionType.DELETE_TASK).risk.value, "HIGH")

    def test_the_catalogue_shown_to_the_model_is_only_what_the_speaker_holds(self):
        rendered = render_catalogue([capability_for(SuggestedActionType.CREATE_ISSUE)])
        self.assertIn("CREATE_ISSUE", rendered)
        self.assertNotIn("DELETE_TASK", rendered)
        self.assertNotIn("UPDATE_TASK_SCHEDULE", rendered)


class SpokenValuesBecomeRealOnes(TestCase):
    def test_a_spoken_date_reaches_the_draft_as_a_real_day(self):
        tasks = project_tasks()
        subject = interpret(
            command(raw_transcript="خلّي موعد المهمة السادسة الأسبوع الجاي"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="move task six to next week",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.UPDATE_TASK_SCHEDULE,
                    reason="Schedule change requested",
                    target_id=tasks[5].id,
                    payload={"dueDate": "الأسبوع الجاي"},
                    confidence=0.9,
                )],
            ),
            tasks,
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
        stored = subject.action_drafts[0].extracted_payload["dueDate"]
        # A real date, not the words — and one the engineer can check on the
        # card before anything is written.
        self.assertRegex(stored, r"^\d{4}-\d{2}-\d{2}$")
        self.assertGreater(date.fromisoformat(stored), date.today())

    def test_a_date_nobody_said_is_asked_for_rather_than_invented(self):
        tasks = project_tasks()
        subject = interpret(
            command(raw_transcript="غير موعد المهمة السادسة"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="change the date of task six",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.UPDATE_TASK_SCHEDULE,
                    reason="Schedule change requested",
                    target_id=tasks[5].id,
                    payload={},
                    confidence=0.9,
                )],
            ),
            tasks,
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        self.assertEqual(subject.clarifications[0].field_path, "payload.dueDate")
        self.assertEqual(subject.clarifications[0].expected_answer_type, "DATE")
        self.assertNotIn("dueDate", subject.action_drafts[0].extracted_payload)

    def test_an_ambiguous_weekday_offers_both_days_instead_of_choosing(self):
        # A bare weekday on that same weekday could be today or next week.
        today = date(2026, 8, 26)  # a Wednesday
        spoken = resolve_spoken_date("الأربعاء", today=today)
        self.assertFalse(spoken.is_resolved)
        self.assertEqual(spoken.options, (today, date(2026, 9, 2)))

    def test_a_date_is_never_written_onto_an_action_that_has_no_date_field(self):
        """An issue that mentions "اليوم" is not a schedule change.

        Resolution hunts the whole sentence for a due date, because people say
        "خلّي المهمة السادسة الأسبوع الجاي" without repeating it into a field.
        Doing that for every capability would put `dueDate` on an issue report,
        whose contract forbids it — and the rules engine would then reject the
        whole action at execution for a field nobody asked for.
        """
        tasks = project_tasks()
        subject = interpret(
            command(raw_transcript="سجل مشكلة إن المواد ما وصلت اليوم"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="materials did not arrive today",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.CREATE_ISSUE,
                    reason="Problem reported",
                    payload={"title": "المواد ما وصلت", "description": "المواد ما وصلت اليوم"},
                    confidence=0.9,
                )],
            ),
            tasks,
        )
        payload = subject.action_drafts[0].extracted_payload
        self.assertNotIn("dueDate", payload)
        self.assertLessEqual(
            set(payload), ACTION_CONTRACTS[SuggestedActionType.CREATE_ISSUE].allowed,
        )

    def test_spoken_priority_and_issue_state_map_onto_platform_values(self):
        self.assertEqual(priority_value("خلي الأولوية خطر"), "critical")
        self.assertEqual(priority_value("make it high"), "high")
        self.assertEqual(issue_status_value("المشكلة انحلت"), "resolved")
        self.assertEqual(issue_status_value("سكّرها"), "closed")
        self.assertIsNone(priority_value("something else entirely"))

    def test_a_named_person_becomes_an_identifier_from_the_project_team(self):
        tasks = project_tasks()
        layla = Person(uuid4(), "Layla Haddad", "engineer")
        subject = interpret(
            command(raw_transcript="assign the sixth task to Layla Haddad"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="assign task six",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.UPDATE_TASK_ASSIGNMENT,
                    reason="Assignment requested",
                    target_id=tasks[5].id,
                    payload={},
                    confidence=0.9,
                )],
            ),
            tasks,
            people=[layla, Person(uuid4(), "Omar Sabbagh", "worker")],
        )
        self.assertEqual(
            subject.action_drafts[0].extracted_payload["assigneeIds"],
            [str(layla.user_id)],
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)

    def test_two_people_with_the_same_name_are_asked_about_never_guessed(self):
        tasks = project_tasks()
        people = [
            Person(uuid4(), "أحمد خليل", "engineer"),
            Person(uuid4(), "أحمد سعيد", "engineer"),
        ]
        subject = interpret(
            command(raw_transcript="عيّن أحمد على المهمة السادسة"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="assign task six to Ahmad",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.UPDATE_TASK_ASSIGNMENT,
                    reason="Assignment requested",
                    target_id=tasks[5].id,
                    payload={},
                    confidence=0.9,
                )],
            ),
            tasks,
            people=people,
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        question = subject.clarifications[0]
        self.assertEqual(question.field_path, "payload.assignee")
        self.assertEqual(
            sorted(option["label"] for option in question.options),
            sorted(person.name for person in people),
        )


class PermissionIsAnswerdInWords(TestCase):
    def test_a_capability_this_person_lacks_is_declined_not_drafted(self):
        tasks = project_tasks()
        subject = interpret(
            command(raw_transcript="احذف المهمة السادسة"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="delete task six",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.DELETE_TASK,
                    reason="Deletion requested",
                    target_id=tasks[5].id,
                    payload={},
                    confidence=0.9,
                )],
            ),
            tasks,
            capable=False,
        )
        self.assertEqual(subject.action_drafts, [])
        self.assertEqual(subject.status, VoiceAnalysisStatus.COMPLETED)
        answer = subject.structured_result["answer"]
        self.assertEqual(answer["topic"], "NOT_PERMITTED")
        self.assertIn("صلاحية", answer["text"])
        # Nothing internal in the refusal: no action name, no permission code.
        self.assertNotIn("DELETE_TASK", answer["text"])
        self.assertNotIn("task.edit", answer["text"])


class CorrectionsRewriteTheProposalOnScreen(TestCase):
    def _reviewed(self, tasks, payload=None,
                  action=SuggestedActionType.UPDATE_TASK_PROGRESS):
        draft = SimpleNamespace(
            id=uuid4(),
            client_action_id="a1",
            action_type=action.value,
            target_entity_type="TASK",
            target_entity_id=tasks[5].id,
            target_snapshot=None,
            extracted_payload=payload if payload is not None else {"progressPercentage": 50},
            user_edited_payload=None,
            confidence=0.9,
            risk_level="MEDIUM",
            required_evidence=[],
            warnings=[],
            missing_fields=[],
        )
        return command(
            raw_transcript="خلصت نص المهمة السادسة",
            status=VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
            action_drafts=[draft],
        )

    def test_no_i_meant_the_seventh_moves_the_proposal_not_a_second_one(self):
        tasks = project_tasks()
        reviewed = self._reviewed(tasks)
        subject = interpret(
            command(raw_transcript="لا، قصدي المهمة الثالثة"),
            result(request_kind=VoiceRequestKind.ACTION, summary="correction"),
            tasks,
            correctable=reviewed,
        )
        self.assertEqual(len(subject.action_drafts), 1)
        draft = subject.action_drafts[0]
        self.assertEqual(draft.target_entity_id, tasks[2].id)
        # The value that was *not* corrected survives untouched.
        self.assertEqual(draft.extracted_payload["progressPercentage"], 50)
        self.assertEqual(reviewed.status, VoiceAnalysisStatus.CANCELLED)
        self.assertEqual(subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)

    def test_a_corrected_date_replaces_the_one_under_review(self):
        tasks = project_tasks()
        reviewed = self._reviewed(
            tasks,
            payload={"dueDate": "2026-09-15"},
            action=SuggestedActionType.UPDATE_TASK_SCHEDULE,
        )
        subject = interpret(
            command(raw_transcript="لا، خليها 20 سبتمبر"),
            result(request_kind=VoiceRequestKind.ACTION, summary="correction"),
            tasks,
            correctable=reviewed,
        )
        self.assertEqual(
            subject.action_drafts[0].extracted_payload["dueDate"][-5:], "09-20"
        )

    def test_an_ordinary_instruction_is_not_treated_as_a_correction(self):
        tasks = project_tasks()
        reviewed = self._reviewed(tasks)
        subject = interpret(
            command(raw_transcript="سجل مشكلة إن المواد ما وصلت"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="report an issue",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.CREATE_ISSUE,
                    reason="Problem reported",
                    payload={"title": "المواد ما وصلت", "description": "المواد ما وصلت"},
                    confidence=0.9,
                )],
            ),
            tasks,
            correctable=reviewed,
        )
        self.assertEqual(subject.action_drafts[0].action_type, "CREATE_ISSUE")


class QuestionsDoNotCancelWhatIsInFlight(TestCase):
    def test_answering_a_question_reminds_the_speaker_what_is_still_open(self):
        tasks = project_tasks()
        pending = command(
            raw_transcript="غير موعد المهمة السادسة",
            status=VoiceAnalysisStatus.NEEDS_CLARIFICATION,
            clarifications=[SimpleNamespace(
                answer_text=None,
                question_ar="لأي تاريخ بدك تخليه؟",
                question_en="What date should it be?",
            )],
            action_drafts=[SimpleNamespace(missing_fields=["payload.dueDate"])],
        )
        subject = interpret(
            command(raw_transcript="بالمناسبة، شو وضع المشروع؟"),
            result(
                request_kind=VoiceRequestKind.QUESTION,
                summary="project status",
                query=voice_command_service.VoiceQueryTopic and __import__(
                    "app.schemas.voice_analysis", fromlist=["DetectedQuery"]
                ).DetectedQuery(topic="PROJECT_PROGRESS", confidence=0.9),
            ),
            tasks,
            pending=pending,
        )
        text = subject.structured_result["answer"]["text"]
        self.assertIn("لأي تاريخ", text)
        # The pending request is untouched: a question is a read.
        self.assertEqual(pending.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)


class FailuresAreExplainedNotPrinted(TestCase):
    def test_every_failure_class_has_a_sentence_in_both_languages(self):
        for status, expected in (
            (403, voice_action_errors.PERMISSION_DENIED),
            (404, voice_action_errors.NOT_FOUND),
            (409, voice_action_errors.WORKFLOW_CONFLICT),
            (422, voice_action_errors.VALIDATION_ERROR),
            (503, voice_action_errors.SERVICE_UNAVAILABLE),
        ):
            failure = voice_action_errors.classify(
                HTTPException(status_code=status, detail="internal wording")
            )
            self.assertEqual(failure.error_code, expected)
            self.assertTrue(failure.text_ar.strip())
            self.assertTrue(failure.text_en.strip())
            # The backend's own words are kept for the log and never shown.
            self.assertEqual(failure.detail, "internal wording")
            self.assertNotIn("internal wording", failure.text_for("ar"))
            self.assertNotIn("internal wording", failure.text_for("en"))

    def test_a_missing_recipient_is_a_question_not_a_validation_error(self):
        failure = voice_action_errors.classify(HTTPException(
            status_code=422, detail="At least one authorized recipient is required",
        ))
        self.assertEqual(failure.error_code, voice_action_errors.RECIPIENT_REQUIRED)
        self.assertIn("لمين", failure.text_for("ar"))

    def test_an_unreachable_recipient_says_so_specifically(self):
        failure = voice_action_errors.classify(HTTPException(
            status_code=403,
            detail="One or more recipients are outside your authorized project contacts",
        ))
        self.assertEqual(failure.error_code, voice_action_errors.RECIPIENT_NOT_ALLOWED)

    def test_success_is_narrated_per_capability(self):
        self.assertIn("موعد", voice_action_errors.success_message("UPDATE_TASK_SCHEDULE", "ar"))
        self.assertIn("sent", voice_action_errors.success_message("SEND_OWNER_UPDATE", "en"))
        # Every capability has a sentence rather than falling back to "Done".
        for action in SuggestedActionType:
            self.assertNotEqual(
                voice_action_errors.success_message(action.value, "en"), "Done.",
            )


class RequirementsFollowTheRegistry(TestCase):
    def test_a_new_capability_reports_what_it_needs_without_its_own_table(self):
        self.assertEqual(
            missing_fields(SuggestedActionType.UPDATE_TASK_SCHEDULE, {}, has_target=False),
            [TARGET_TASK, "payload.dueDate"],
        )
        self.assertEqual(
            missing_fields(SuggestedActionType.UPDATE_ISSUE_STATUS, {}, has_target=False),
            [TARGET_ISSUE, "payload.issueStatus"],
        )
        self.assertEqual(
            missing_fields(
                SuggestedActionType.UPDATE_TASK_PRIORITY,
                {"priority": "high"},
                has_target=True,
            ),
            [],
        )

    def test_a_message_with_nobody_to_send_it_to_asks_who(self):
        self.assertEqual(
            missing_fields(
                SuggestedActionType.SEND_PROJECT_MESSAGE,
                {"content": "المواد تأخرت"},
                has_target=False,
            ),
            ["payload.recipients"],
        )
