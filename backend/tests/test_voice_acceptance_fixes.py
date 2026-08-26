"""The five defects found in the Voice acceptance pass, pinned so they stay fixed.

Every case here was observed on a real device against real project data. They
are grouped by the report they came from, and each one asserts the *behaviour*
the engineer sees rather than the internals that produce it — a test that
pinned the internals would pass again the next time the same failure came back
wearing different plumbing.

  1. **A site report is a document.** "اعطيني آخر تقرير موقع" came back as a
     project summary, because a filed report had no topic to go to and the
     nearest ones — PROJECT_PROGRESS, REPORT_READINESS — are about the project
     and about whether a report *could* be written.
  2. **A suspicion is not a fact.** "أتوقع إنه في مشكلة في المشروع" was read as
     an assertion, so the assistant offered to record it instead of looking.
  3. **A person is an identity or a question.** A spoken name resolved against
     the whole team rather than the people who may hold work, and a name that
     matched nobody produced a bare "who?" that named nothing.
  4. **A failure says what failed.** An execution refusal the backend had a
     precise reason for reached the engineer as "something is missing".
  5. **An answered question stays answered.** The reply to "لأي تاريخ؟" was
     sometimes read as a brand-new request, which lost the task the request had
     already resolved and asked for it again — the loop.

The phrasing model is off for the whole suite (see `tests/conftest.py`), so
every assertion holds on the deterministic wording, which is what must be true
when the provider is unavailable.
"""

from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.models.enums import TaskStatus, VoiceAnalysisStatus
from app.schemas.voice_analysis import (
    DetectedProblem,
    DetectedProgress,
    DetectedQuery,
    ProblemType,
    SuggestedAction,
    SuggestedActionType,
    VoiceIntent,
    VoiceQueryTopic,
    VoiceRequestKind,
)
from app.services import voice_action_errors, voice_command_service
from app.services.voice_action_errors import (
    ASSIGNEE_NOT_ELIGIBLE,
    ASSIGNEE_REQUIRED,
    CLARIFICATION_REQUIRED,
    TARGET_TASK_NOT_FOUND,
    TARGET_TASK_REQUIRED,
    VoiceActionError,
    classify,
    missing_field_failure,
)
from app.services.voice_action_requirements import TARGET_TASK
from app.services.voice_entity_resolution import Person, named_person_reference
from app.services.voice_query_service import (
    PROJECT_LEVEL_TOPICS,
    SITE_REPORT_TOPICS,
    answer_query,
)
from app.services.voice_router import VoiceRoute, route_request
from app.services.voice_rules_engine import VoiceRulesEngine
from tests.test_voice_conversation import command, interpret, project_tasks, result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def site_report(**overrides):
    """One filed site report, with the fields an answer is allowed to state."""
    values = {
        "id": uuid4(),
        "report_date": date(2026, 8, 24),
        "submitted_by_id": uuid4(),
        "review_status": "submitted",
        "summary_text": "صب الخرسانة للطابق الثاني",
        "work_completed": None,
        "work_in_progress": None,
        "delays": None,
        "issues_summary": None,
        "notes": None,
        "weather_conditions": None,
        "workers_count": None,
        "progress_percentage_reported": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def answer_about_reports(topic, reports, *, author="سامي حداد"):
    """Run the real read path with the site-report table stubbed."""
    db = MagicMock()
    db.get.return_value = SimpleNamespace(full_name=author) if author else None
    with patch(
        "app.services.voice_analysis_authorization.authorized_site_reports",
        return_value=list(reports),
    ):
        return answer_query(
            db,
            user=SimpleNamespace(id=uuid4()),
            project_id=uuid4(),
            query=DetectedQuery(topic=topic, confidence=0.9),
            tasks=[],
        )


def spoken_result(transcript, **overrides):
    """An interpreted utterance that remembers what was actually said.

    `original_transcript` matters here rather than being decoration: the
    uncertainty check reads the words, because the qualifier that changes a
    sentence's meaning does not survive into any classified field.
    """
    values = {"original_transcript": transcript, "summary": transcript}
    values.update(overrides)
    return result(**values)


# ---------------------------------------------------------------------------
# 1 & 2. Site reports, and telling them apart from a project summary
# ---------------------------------------------------------------------------

class LatestSiteReportTests(TestCase):
    """A request for the filed report is answered from the filed report."""

    def test_the_latest_site_report_is_answered_from_the_site_report_record(self):
        answer = answer_about_reports(
            VoiceQueryTopic.LATEST_SITE_REPORT, [site_report()]
        )
        self.assertTrue(answer.is_answered)
        self.assertEqual(answer.data["siteReport"]["reportDate"], "2026-08-24")
        self.assertEqual(answer.data["siteReport"]["submittedBy"], "سامي حداد")
        # The report's own words, not a summary of the project's tasks.
        self.assertIn("صب الخرسانة للطابق الثاني", answer.text_ar)
        self.assertIn("صب الخرسانة للطابق الثاني", answer.text_en)

    def test_the_answer_names_the_document_it_came_from(self):
        """Date, author and review state, so it cannot be mistaken for a summary."""
        answer = answer_about_reports(
            VoiceQueryTopic.LATEST_SITE_REPORT,
            [site_report(review_status="approved")],
        )
        self.assertIn("تقرير موقع", answer.text_ar)
        self.assertIn("site report", answer.text_en.lower())
        self.assertIn("سامي حداد", answer.text_ar)
        self.assertIn("معتمد", answer.text_ar)
        self.assertIn("approved", answer.text_en)

    def test_the_newest_report_is_the_one_answered(self):
        newest = site_report(report_date=date(2026, 8, 25), summary_text="أحدث تقرير")
        answer = answer_about_reports(
            VoiceQueryTopic.LATEST_SITE_REPORT,
            # `authorized_site_reports` orders newest-first; the answer takes
            # the head of that list rather than re-sorting it.
            [newest, site_report(summary_text="تقرير أقدم")],
        )
        self.assertIn("أحدث تقرير", answer.text_ar)
        self.assertNotIn("تقرير أقدم", answer.text_ar)

    def test_a_report_whose_summary_is_empty_still_answers(self):
        """People fill in the field that fits the day, not the one named first."""
        answer = answer_about_reports(
            VoiceQueryTopic.LATEST_SITE_REPORT,
            [site_report(summary_text=None, work_completed="تركيب الحديد")],
        )
        self.assertIn("تركيب الحديد", answer.text_ar)

    def test_delays_and_issues_are_carried_when_the_report_has_them(self):
        answer = answer_about_reports(
            VoiceQueryTopic.LATEST_SITE_REPORT,
            [site_report(delays="تأخير المواد", issues_summary="تسرب مياه")],
        )
        self.assertIn("تأخير المواد", answer.text_ar)
        self.assertIn("تسرب مياه", answer.text_ar)

    def test_no_reports_says_so_rather_than_falling_back_to_a_summary(self):
        answer = answer_about_reports(VoiceQueryTopic.LATEST_SITE_REPORT, [])
        self.assertTrue(answer.is_answered)
        self.assertEqual(answer.data["siteReportCount"], 0)
        self.assertIn("ما في ولا تقرير موقع", answer.text_ar)
        self.assertIn("no site reports", answer.text_en.lower())

    def test_several_reports_can_be_listed(self):
        answer = answer_about_reports(
            VoiceQueryTopic.SITE_REPORTS,
            [site_report(report_date=date(2026, 8, 25)), site_report()],
        )
        self.assertEqual(answer.data["siteReportCount"], 2)
        self.assertIn("2026-08-25", answer.text_en)

    def test_a_site_report_question_is_a_read_and_proposes_nothing(self):
        decision = route_request(spoken_result(
            "اعطيني آخر تقرير موقع",
            request_kind=VoiceRequestKind.QUESTION,
            query=DetectedQuery(
                topic=VoiceQueryTopic.LATEST_SITE_REPORT, confidence=0.9
            ),
            detected_intents=[VoiceIntent.REQUEST_INFORMATION],
        ))
        self.assertEqual(decision.route, VoiceRoute.ANSWER)
        self.assertEqual(decision.topic, VoiceQueryTopic.LATEST_SITE_REPORT)


class SiteReportIsNotAProjectSummaryTests(TestCase):
    """The two answers must be impossible to confuse for each other."""

    def test_the_site_report_topics_are_not_the_project_summary_topics(self):
        self.assertFalse(SITE_REPORT_TOPICS & PROJECT_LEVEL_TOPICS)
        self.assertIn(VoiceQueryTopic.PROJECT_PROGRESS, PROJECT_LEVEL_TOPICS)
        self.assertIn(VoiceQueryTopic.REPORT_READINESS, PROJECT_LEVEL_TOPICS)

    def test_a_project_progress_answer_never_claims_to_be_a_report(self):
        tasks = project_tasks()
        answer = answer_query(
            MagicMock(), user=SimpleNamespace(id=uuid4()), project_id=uuid4(),
            query=DetectedQuery(
                topic=VoiceQueryTopic.PROJECT_PROGRESS, confidence=0.9
            ),
            tasks=tasks,
        )
        self.assertNotIn("siteReport", answer.data)
        self.assertNotIn("تقرير موقع", answer.text_ar)

    def test_a_site_report_answer_carries_no_task_counts(self):
        """The failure in reverse: an answer that is really a summary."""
        answer = answer_about_reports(
            VoiceQueryTopic.LATEST_SITE_REPORT, [site_report()]
        )
        self.assertNotIn("completedCount", answer.data)
        self.assertNotIn("openCount", answer.data)

    def test_the_prompt_separates_the_report_topics_from_the_summary_ones(self):
        """The model must be told the distinction, not left to infer it."""
        from app.ai.construction_analysis_service import SYSTEM_PROMPT

        self.assertIn("LATEST_SITE_REPORT", SYSTEM_PROMPT)
        self.assertIn("SITE_REPORTS", SYSTEM_PROMPT)
        self.assertIn(
            "Never answer a request for a site report with PROJECT_PROGRESS",
            SYSTEM_PROMPT,
        )


# ---------------------------------------------------------------------------
# 3. A question, a statement, and a belief are three different things
# ---------------------------------------------------------------------------

def uncertain(transcript, **overrides):
    values = {
        "request_kind": VoiceRequestKind.STATEMENT,
        "detected_intents": [VoiceIntent.REPORT_TASK_BLOCKER],
    }
    values.update(overrides)
    return spoken_result(transcript, **values)


class UncertaintyIsAQuestionTests(TestCase):
    """A hedged sentence is the engineer asking, not the engineer reporting."""

    def test_a_hedged_belief_is_answered_rather_than_recorded(self):
        decision = route_request(uncertain("أتوقع إنه في مشكلة في المشروع"))
        self.assertEqual(decision.route, VoiceRoute.ANSWER)
        self.assertEqual(decision.topic, VoiceQueryTopic.OPEN_ISSUES)

    def test_the_phrasings_from_acceptance_testing_all_reach_the_record(self):
        for transcript in (
            "أتوقع إنه في مشكلة في المشروع، صح؟",
            "أعتقد إنه في مشكلة بالمشروع، شو رأيك؟",
            "بظن في مشكلة بالمشروع",
            "I think there is a problem on this project",
            "not sure, maybe there is a problem here",
        ):
            with self.subTest(transcript=transcript):
                decision = route_request(uncertain(transcript))
                self.assertEqual(decision.route, VoiceRoute.ANSWER)

    def test_an_explicit_question_is_unchanged(self):
        for transcript in ("في مشكلة بالمشروع؟", "هل في مشاكل بالمشروع؟",
                           "شو المشاكل الموجودة بالمشروع؟"):
            with self.subTest(transcript=transcript):
                decision = route_request(spoken_result(
                    transcript,
                    request_kind=VoiceRequestKind.QUESTION,
                    query=DetectedQuery(
                        topic=VoiceQueryTopic.OPEN_ISSUES, confidence=0.9
                    ),
                ))
                self.assertEqual(decision.route, VoiceRoute.ANSWER)
                self.assertEqual(decision.topic, VoiceQueryTopic.OPEN_ISSUES)

    def test_a_first_hand_report_is_still_a_statement(self):
        """The mirror rule. Weakening this would lose real site information."""
        for transcript in ("في مشكلة في وصول المواد.",
                           "المواد الكهربائية ما وصلت."):
            with self.subTest(transcript=transcript):
                decision = route_request(uncertain(
                    transcript,
                    problems=[DetectedProblem(
                        type=ProblemType.MATERIAL_DELAY,
                        description="المواد ما وصلت",
                        confidence=0.9,
                    )],
                ))
                self.assertNotEqual(decision.route, VoiceRoute.ANSWER)

    def test_a_hedge_inside_an_instruction_is_still_the_instruction(self):
        """"أتوقع" must never by itself turn a request into a question."""
        decision = route_request(spoken_result(
            "أتوقع نخلص بكرة، سجّل ملاحظة إننا بنخلص بكرة",
            request_kind=VoiceRequestKind.ACTION,
            suggested_actions=[SuggestedAction(
                type=SuggestedActionType.ADD_TASK_NOTE,
                reason="Engineer asked for a note",
                payload={"content": "بنخلص بكرة"},
                confidence=0.9,
            )],
        ))
        self.assertEqual(decision.route, VoiceRoute.ACTION)

    def test_the_domains_most_common_words_are_not_read_as_hedges(self):
        """"مشكلة" folds to "مشكله", which contains "شكله"; "بشكل" contains "بشك".

        A loose substring test would have marked the most ordinary sentences on
        a construction site as uncertain, which would have turned every real
        problem report into a question instead of a record.
        """
        for transcript in (
            "في مشكلة بالموقع",
            "المشكلة إن المواد ما وصلت",
            "الشغل ماشي بشكل عام منيح",
            "بشكل يومي منراجع الموقع",
        ):
            with self.subTest(transcript=transcript):
                decision = route_request(uncertain(transcript))
                self.assertNotEqual(
                    decision.reason, "uncertain statement answered from the record"
                )

    def test_a_hedge_carried_by_a_clitic_is_still_a_hedge(self):
        """Arabic attaches "و" to the front of the next word."""
        decision = route_request(uncertain("المواد وصلت، وأتوقع في مشكلة بالكهرباء"))
        self.assertEqual(decision.route, VoiceRoute.ANSWER)

    def test_uncertainty_about_delay_asks_about_the_delay(self):
        decision = route_request(uncertain(
            "بظن في تأخير بالجدول",
            query=DetectedQuery(topic=VoiceQueryTopic.WHY_DELAYED, confidence=0.7),
        ))
        self.assertEqual(decision.topic, VoiceQueryTopic.WHY_DELAYED)

    def test_a_suspicion_produces_no_draft_and_finishes_the_command(self):
        subject = interpret(
            command(raw_transcript="أتوقع إنه في مشكلة في المشروع"),
            uncertain("أتوقع إنه في مشكلة في المشروع"),
            project_tasks(),
        )
        self.assertEqual(subject.action_drafts, [])
        self.assertEqual(subject.status, VoiceAnalysisStatus.COMPLETED)
        self.assertTrue(subject.structured_result["answer"]["text"].strip())

    def test_the_prompt_teaches_the_distinction_rather_than_a_keyword(self):
        from app.ai.construction_analysis_service import SYSTEM_PROMPT

        self.assertIn("UNCERTAINTY IS NOT A STATEMENT", SYSTEM_PROMPT)
        self.assertIn("Read the whole sentence, not one word", SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# 4. Who the engineer meant
# ---------------------------------------------------------------------------

def assignment(transcript, people, tasks=None):
    tasks = tasks or project_tasks()
    return interpret(
        command(raw_transcript=transcript),
        result(
            request_kind=VoiceRequestKind.ACTION,
            summary="assign a task",
            suggested_actions=[SuggestedAction(
                type=SuggestedActionType.UPDATE_TASK_ASSIGNMENT,
                reason="Assignment requested",
                payload={},
                confidence=0.9,
            )],
        ),
        tasks,
        people=people,
    )


class AssigneeResolutionTests(TestCase):
    """A name becomes an identity, a question, or an explanation. Never a guess."""

    def test_a_person_on_the_project_becomes_an_identifier_before_review(self):
        noor = Person(uuid4(), "نور علي", "engineer")
        subject = assignment(
            "عيّن المهمة السادسة لنور علي",
            [noor, Person(uuid4(), "خالد سعيد", "worker")],
        )
        draft = subject.action_drafts[0]
        self.assertEqual(draft.extracted_payload["assigneeIds"], [str(noor.user_id)])
        self.assertEqual(draft.missing_fields, [])
        self.assertEqual(subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)

    def test_the_review_card_never_carries_a_name_instead_of_an_identity(self):
        noor = Person(uuid4(), "نور علي", "engineer")
        subject = assignment("عيّن المهمة السادسة لنور علي", [noor])
        payload = subject.action_drafts[0].extracted_payload
        self.assertNotIn("نور", str(payload.get("assigneeIds")))

    def test_a_name_nobody_has_is_explained_rather_than_asked_around(self):
        subject = assignment(
            "عيّن المهمة السادسة لأحمد",
            [Person(uuid4(), "نور علي", "engineer")],
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        question = subject.clarifications[0]
        self.assertEqual(question.field_path, "payload.assignee")
        # The engineer hears *which* name could not be found, in their words.
        self.assertIn("أحمد", question.question_ar)
        self.assertIn("ما لقيت", question.question_ar)
        # The name is quoted back as it was said, in either language's half.
        self.assertIn("أحمد", question.question_en)
        self.assertIn("could not find", question.question_en)

    def test_the_unfound_name_reaches_the_spoken_reply_too(self):
        """A client that renders only the reply text must still hear the reason."""
        subject = assignment(
            "عيّن المهمة السادسة لأحمد",
            [Person(uuid4(), "نور علي", "engineer")],
        )
        self.assertIn("أحمد", subject.structured_result["answer"]["text"])

    def test_nothing_is_assigned_when_the_person_could_not_be_found(self):
        subject = assignment(
            "عيّن المهمة السادسة لأحمد",
            [Person(uuid4(), "نور علي", "engineer")],
        )
        draft = subject.action_drafts[0]
        self.assertNotIn("assigneeIds", draft.extracted_payload)
        self.assertIn("payload.assignee", draft.missing_fields)

    def test_two_people_who_fit_the_name_are_asked_about(self):
        people = [
            Person(uuid4(), "أحمد خليل", "engineer"),
            Person(uuid4(), "أحمد سعيد", "engineer"),
        ]
        subject = assignment("عيّن المهمة السادسة لأحمد", people)
        self.assertEqual(subject.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        question = subject.clarifications[0]
        self.assertEqual(question.field_path, "payload.assignee")
        self.assertEqual(
            sorted(option["label"] for option in question.options),
            sorted(person.name for person in people),
        )
        # Both of them *were* found, so nothing says otherwise.
        self.assertNotIn("ما لقيت", question.question_ar)

    def test_a_spoken_name_is_read_out_of_the_sentence_it_was_said_in(self):
        self.assertEqual(named_person_reference("عيّن المهمة السادسة لأحمد"), "أحمد")
        self.assertEqual(
            named_person_reference("عيّن المهمة السادسة لنور علي"), "نور علي"
        )
        self.assertEqual(
            named_person_reference("assign task six to Ahmad Khalil"), "Ahmad Khalil"
        )

    def test_a_sentence_with_no_person_in_it_names_nobody(self):
        """A false positive here would invent a person the engineer never said."""
        for transcript in (
            "حدثلي المهمة السادسة وخلي تاريخها 19 سبتمبر",
            "لازم نخلص الشغل اليوم",
            "ليش المهمة متأخرة",
            "بدي أرفع مشكلة",
        ):
            with self.subTest(transcript=transcript):
                self.assertIsNone(named_person_reference(transcript))


class AssignableTeamTests(TestCase):
    """Assignment resolves against people who may hold work, not the whole team."""

    def test_an_ineligible_person_is_refused_before_anything_executes(self):
        eligible = Person(uuid4(), "نور علي", "engineer")
        with patch(
            "app.services.voice_entity_resolution.assignable_people",
            return_value=[eligible],
        ):
            with self.assertRaises(VoiceActionError) as raised:
                VoiceRulesEngine._validated_assignees(
                    MagicMock(),
                    SimpleNamespace(project_id=uuid4()),
                    {"assigneeIds": [str(uuid4())]},
                )
        self.assertEqual(raised.exception.error_code, ASSIGNEE_NOT_ELIGIBLE)
        self.assertIn("مهندس", raised.exception.text_ar)

    def test_an_eligible_person_passes(self):
        eligible = Person(uuid4(), "نور علي", "engineer")
        with patch(
            "app.services.voice_entity_resolution.assignable_people",
            return_value=[eligible],
        ):
            VoiceRulesEngine._validated_assignees(
                MagicMock(),
                SimpleNamespace(project_id=uuid4()),
                {"assigneeIds": [str(eligible.user_id)]},
            )

    def test_an_empty_assignee_list_says_who_it_is_waiting_for(self):
        with patch(
            "app.services.voice_entity_resolution.assignable_people",
            return_value=[],
        ):
            with self.assertRaises(VoiceActionError) as raised:
                VoiceRulesEngine._validated_assignees(
                    MagicMock(), SimpleNamespace(project_id=uuid4()), {}
                )
        self.assertEqual(raised.exception.error_code, ASSIGNEE_REQUIRED)
        self.assertIn("مين", raised.exception.text_ar)


# ---------------------------------------------------------------------------
# 5. A failure that says what failed
# ---------------------------------------------------------------------------

class ExecutionFeedbackTests(TestCase):
    """The engineer must learn what failed, why, and what to do next."""

    def test_an_outstanding_field_is_named_rather_than_called_missing_data(self):
        failure = classify(missing_field_failure([TARGET_TASK]))
        self.assertEqual(failure.error_code, CLARIFICATION_REQUIRED)
        self.assertIn("أي مهمة تقصد؟", failure.text_ar)
        self.assertIn("Which task", failure.text_en)
        self.assertEqual(failure.details["missingFields"], [TARGET_TASK])

    def test_a_missing_date_asks_for_the_date(self):
        failure = classify(missing_field_failure(["payload.dueDate"]))
        self.assertIn("تاريخ", failure.text_ar)
        self.assertIn("date", failure.text_en.lower())

    def test_the_backend_sentences_map_onto_reasons_a_person_can_act_on(self):
        for detail, status, code in (
            ("A target task is required", 422, TARGET_TASK_REQUIRED),
            ("Target task is unavailable", 404, TARGET_TASK_NOT_FOUND),
            ("No assignee was selected", 422, ASSIGNEE_REQUIRED),
            (
                "Every assignee must be an active Engineer, Worker, Consultant, "
                "or assigned Project Manager on this project",
                400,
                ASSIGNEE_NOT_ELIGIBLE,
            ),
            ("No new date was provided", 422, voice_action_errors.DATE_REQUIRED),
            (
                "Only a To Do task can be started",
                409,
                voice_action_errors.TASK_NOT_STARTABLE,
            ),
            (
                "Progress must be 100% before review submission",
                409,
                voice_action_errors.REVIEW_NOT_COMPLETE,
            ),
            (
                "Task progress is locked by workflow",
                409,
                voice_action_errors.PROGRESS_LOCKED,
            ),
        ):
            with self.subTest(detail=detail):
                failure = classify(HTTPException(status_code=status, detail=detail))
                self.assertEqual(failure.error_code, code)

    def test_no_failure_message_leaks_anything_internal(self):
        forbidden = (
            "HTTPException", "Traceback", "SELECT", "payload.", "target.",
            "sqlalchemy", "422", "500", "UPDATE_TASK",
        )
        messages = [
            *(text for pair in voice_action_errors._MESSAGES.values() for text in pair),
            classify(missing_field_failure([TARGET_TASK])).text_ar,
            classify(missing_field_failure([TARGET_TASK])).text_en,
        ]
        for message in messages:
            for token in forbidden:
                self.assertNotIn(token, message)

    def test_an_unrecognised_failure_is_never_dressed_up_as_a_known_one(self):
        failure = classify(HTTPException(status_code=418, detail="teapot"))
        self.assertEqual(failure.error_code, voice_action_errors.ACTION_FAILED)
        self.assertIn("ما تغيّر إشي", failure.text_ar)

    def test_the_developer_sentence_is_kept_for_the_log_and_never_shown(self):
        failure = classify(HTTPException(
            status_code=404, detail="Target task is unavailable"
        ))
        self.assertEqual(failure.detail, "Target task is unavailable")
        self.assertNotIn("Target task is unavailable", failure.text_en)
        self.assertNotIn("Target task is unavailable", failure.text_ar)


# ---------------------------------------------------------------------------
# 6. The date conversation, in one breath and in three
# ---------------------------------------------------------------------------

def schedule_action(payload=None, target_id=None):
    return SuggestedAction(
        type=SuggestedActionType.UPDATE_TASK_SCHEDULE,
        reason="Reschedule requested",
        target_id=target_id,
        payload=payload or {},
        confidence=0.9,
    )


def rearm(subject):
    """Give the carried drafts the identity a database row would have.

    `interpret` builds rows without flushing, so a draft that is about to be
    the *pending* request in the next turn needs the id its clarification
    would have been attached to.
    """
    for draft in subject.action_drafts:
        draft.id = uuid4()
        draft.user_edited_payload = None
    return subject


class DateUpdateTests(TestCase):
    """One complete proposal, reached once, however many turns it took."""

    def test_one_turn_reaches_review_with_the_task_and_the_date(self):
        tasks = project_tasks()
        subject = interpret(
            command(raw_transcript="حدثلي المهمة السادسة وخلي تاريخها 19 سبتمبر"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="move task six to 19 September",
                suggested_actions=[schedule_action({"dueDate": "19 سبتمبر"})],
            ),
            tasks,
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
        self.assertEqual(len(subject.action_drafts), 1)
        draft = subject.action_drafts[0]
        self.assertEqual(draft.action_type, "UPDATE_TASK_SCHEDULE")
        self.assertEqual(draft.target_entity_id, tasks[5].id)
        self.assertEqual(draft.extracted_payload["dueDate"], "2026-09-19")
        self.assertEqual(draft.missing_fields, [])
        self.assertEqual(subject.clarifications, [])

    def test_the_date_the_engineer_said_is_the_date_on_the_card(self):
        """The one failure a schedule change must never have."""
        subject = interpret(
            command(raw_transcript="خلي تاريخ المهمة السادسة 19 سبتمبر"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="move task six",
                suggested_actions=[schedule_action({"dueDate": "19 سبتمبر"})],
            ),
            project_tasks(),
        )
        self.assertEqual(
            subject.action_drafts[0].extracted_payload["dueDate"], "2026-09-19"
        )

    def _three_turns(self, third_result):
        """"بدي أغير موعد مهمة" → "المهمة السادسة" → "19 سبتمبر"."""
        tasks = project_tasks()
        first = interpret(
            command(raw_transcript="بدي أغير موعد مهمة"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="wants to change a task date",
                suggested_actions=[schedule_action()],
            ),
            tasks,
        )
        second = interpret(
            command(raw_transcript="المهمة السادسة"),
            result(request_kind=VoiceRequestKind.ACTION, summary="task six"),
            tasks,
            pending=rearm(first),
        )
        third = interpret(
            command(raw_transcript="19 سبتمبر"),
            third_result,
            tasks,
            pending=rearm(second),
        )
        return tasks, first, second, third

    def test_the_first_turn_asks_only_which_task(self):
        """One question at a time, and it is the one an engineer can answer.

        Asserted after all three turns have run, so the status is the
        *retired* one a continued request ends in — the durable evidence of
        what was asked is the clarification itself.
        """
        _, first, _, _ = self._three_turns(
            result(request_kind=VoiceRequestKind.ACTION, summary="19 september")
        )
        self.assertEqual(len(first.clarifications), 1)
        self.assertEqual(first.clarifications[0].field_path, TARGET_TASK)
        self.assertEqual(first.status, VoiceAnalysisStatus.CANCELLED)
        self.assertEqual(first.provider_metadata["closedReason"], "continued")

    def test_the_second_turn_keeps_the_request_and_asks_only_for_the_date(self):
        _, _, second, _ = self._three_turns(
            result(request_kind=VoiceRequestKind.ACTION, summary="19 september")
        )
        self.assertEqual(len(second.clarifications), 1)
        self.assertEqual(second.clarifications[0].field_path, "payload.dueDate")
        self.assertEqual(second.action_drafts[0].missing_fields, ["payload.dueDate"])
        self.assertEqual(second.provider_metadata["closedReason"], "continued")

    def test_the_answered_date_completes_the_request_rather_than_starting_one(self):
        tasks, _, _, third = self._three_turns(
            result(request_kind=VoiceRequestKind.ACTION, summary="19 september")
        )
        self.assertEqual(third.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
        self.assertEqual(len(third.action_drafts), 1)
        self.assertEqual(third.action_drafts[0].target_entity_id, tasks[5].id)
        self.assertEqual(
            third.action_drafts[0].extracted_payload["dueDate"], "2026-09-19"
        )

    def test_a_date_answered_by_restating_the_action_does_not_start_the_loop(self):
        """The observed loop, exactly.

        The model answers "لأي تاريخ بدك تخليه؟" by proposing the whole
        schedule change again, with the date and no task. Read as a new
        request that is a request with no target — so it asked "أي مهمة
        تقصد؟" again, and the engineer went round the same three turns.
        """
        tasks, _, _, third = self._three_turns(result(
            request_kind=VoiceRequestKind.ACTION,
            summary="19 september",
            suggested_actions=[schedule_action({"dueDate": "19 سبتمبر"})],
        ))
        self.assertEqual(third.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
        self.assertEqual(third.action_drafts[0].target_entity_id, tasks[5].id)
        self.assertEqual(
            third.action_drafts[0].extracted_payload["dueDate"], "2026-09-19"
        )
        self.assertEqual(
            [item.field_path for item in third.clarifications], []
        )

    def test_the_completed_request_reaches_review_exactly_once(self):
        _, _, _, third = self._three_turns(result(
            request_kind=VoiceRequestKind.ACTION,
            summary="19 september",
            suggested_actions=[schedule_action({"dueDate": "19 سبتمبر"})],
        ))
        self.assertEqual(len(third.action_drafts), 1)
        self.assertEqual(third.structured_result["answer"]["topic"], "REVIEW")
        self.assertEqual(third.clarifications, [])

    def test_a_task_that_is_already_known_is_never_asked_about_again(self):
        _, _, second, third = self._three_turns(result(
            request_kind=VoiceRequestKind.ACTION,
            summary="19 september",
            suggested_actions=[schedule_action({"dueDate": "19 سبتمبر"})],
        ))
        asked = [item.field_path for item in second.clarifications + third.clarifications]
        self.assertEqual(asked.count(TARGET_TASK), 0)

    def test_a_genuinely_new_request_is_not_swallowed_by_the_open_one(self):
        """The rule the continuation must not break.

        A second request of the same kind that names a *different* task is a
        new instruction, and merging it would silently reschedule the wrong
        work.
        """
        tasks = project_tasks()
        first = interpret(
            command(raw_transcript="بدي أغير موعد المهمة السادسة"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="change task six date",
                suggested_actions=[schedule_action(target_id=tasks[5].id)],
            ),
            tasks,
        )
        second = interpret(
            command(raw_transcript="خلي المهمة الثالثة الأسبوع الجاي"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="move task three",
                suggested_actions=[schedule_action({"dueDate": "الأسبوع الجاي"})],
            ),
            tasks,
            pending=rearm(first),
        )
        self.assertEqual(second.action_drafts[0].target_entity_id, tasks[2].id)

    def test_a_different_operation_is_never_merged_into_the_open_one(self):
        tasks = project_tasks()
        first = interpret(
            command(raw_transcript="بدي أغير موعد مهمة"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="change a date",
                suggested_actions=[schedule_action()],
            ),
            tasks,
        )
        second = interpret(
            command(raw_transcript="سجل مشكلة إن المواد ما وصلت"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="record an issue",
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.CREATE_ISSUE,
                    reason="Problem reported",
                    payload={"title": "المواد ما وصلت"},
                    confidence=0.9,
                )],
            ),
            tasks,
            pending=rearm(first),
        )
        self.assertEqual(second.action_drafts[0].action_type, "CREATE_ISSUE")


# ---------------------------------------------------------------------------
# 7. Conversational state, which all of the above depends on
# ---------------------------------------------------------------------------

class NoSilentStateTests(TestCase):
    """Whatever happened, the engineer is looking at something."""

    def test_every_reported_scenario_leaves_something_on_the_screen(self):
        tasks = project_tasks()
        subjects = [
            interpret(
                command(raw_transcript="أتوقع إنه في مشكلة في المشروع"),
                uncertain("أتوقع إنه في مشكلة في المشروع"),
                tasks,
            ),
            assignment(
                "عيّن المهمة السادسة لأحمد",
                [Person(uuid4(), "نور علي", "engineer")],
            ),
            interpret(
                command(raw_transcript="حدثلي المهمة السادسة وخلي تاريخها 19 سبتمبر"),
                result(
                    request_kind=VoiceRequestKind.ACTION,
                    summary="move task six",
                    suggested_actions=[schedule_action({"dueDate": "19 سبتمبر"})],
                ),
                tasks,
            ),
        ]
        for subject in subjects:
            with self.subTest(transcript=subject.raw_transcript):
                self.assertTrue(voice_command_service.renders_something(subject))
                self.assertTrue(
                    str(subject.structured_result["answer"]["text"]).strip()
                )

    def test_the_neutral_question_is_not_repeated_word_for_word(self):
        """Asking the same words twice reads as an assistant that is not listening."""
        tasks = project_tasks()
        first = interpret(
            command(raw_transcript="المواد الكهربائية"),
            result(request_kind=VoiceRequestKind.ACTION, summary="materials"),
            tasks,
        )
        second = interpret(
            command(raw_transcript="يعني المواد"),
            result(request_kind=VoiceRequestKind.ACTION, summary="materials again"),
            tasks,
            pending=first,
        )
        self.assertEqual(first.clarifications[0].field_path, "intent")
        self.assertEqual(second.clarifications[0].field_path, "intent")
        self.assertNotEqual(
            first.clarifications[0].question_ar,
            second.clarifications[0].question_ar,
        )

    def test_a_superseded_request_stops_competing_for_the_next_answer(self):
        tasks = project_tasks()
        first = interpret(
            command(raw_transcript="المواد الكهربائية"),
            result(request_kind=VoiceRequestKind.ACTION, summary="materials"),
            tasks,
        )
        interpret(
            command(raw_transcript="يعني المواد"),
            result(request_kind=VoiceRequestKind.ACTION, summary="materials again"),
            tasks,
            pending=first,
        )
        self.assertEqual(first.status, VoiceAnalysisStatus.CANCELLED)

    def test_a_half_finished_request_survives_one_unclear_sentence(self):
        """Only a *bodiless* question is retired when another one replaces it.

        A pending request that is waiting on a field is still answerable, and
        closing it because one sentence in between was unclear would throw
        away an instruction the engineer had already half given.
        """
        tasks = project_tasks()
        first = interpret(
            command(raw_transcript="بدي أغير موعد مهمة"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="change a date",
                suggested_actions=[schedule_action()],
            ),
            tasks,
        )
        interpret(
            command(raw_transcript="المواد الكهربائية"),
            result(request_kind=VoiceRequestKind.ACTION, summary="materials"),
            tasks,
            pending=rearm(first),
        )
        self.assertEqual(first.status, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        self.assertTrue(first.action_drafts[0].missing_fields)


class ExistingBehaviourIsUnchangedTests(TestCase):
    """The flows that already worked must still work, unchanged."""

    def test_a_progress_update_still_drafts_confirms_and_waits(self):
        tasks = project_tasks()
        subject = interpret(
            command(raw_transcript="خلص 60% من المهمة السادسة"),
            result(
                request_kind=VoiceRequestKind.ACTION,
                summary="task six is at 60%",
                progress=DetectedProgress(
                    mentioned=True, percentage=60, confidence=0.9
                ),
                suggested_actions=[SuggestedAction(
                    type=SuggestedActionType.UPDATE_TASK_PROGRESS,
                    reason="Progress reported",
                    target_id=tasks[5].id,
                    payload={"progressPercentage": 60},
                    confidence=0.9,
                )],
            ),
            tasks,
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
        self.assertEqual(
            subject.action_drafts[0].extracted_payload["progressPercentage"], 60
        )

    def test_a_task_question_is_still_answered_and_never_proposes_a_change(self):
        tasks = project_tasks()
        subject = interpret(
            command(raw_transcript="شو حالة المهمة السادسة؟"),
            result(
                request_kind=VoiceRequestKind.QUESTION,
                summary="asks about task six",
                query=DetectedQuery(
                    topic=VoiceQueryTopic.TASK_STATUS,
                    task_reference="المهمة السادسة",
                    confidence=0.9,
                ),
                detected_intents=[VoiceIntent.REQUEST_TASK_INFORMATION],
            ),
            tasks,
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.COMPLETED)
        self.assertEqual(subject.action_drafts, [])

    def test_a_project_question_is_still_answered_from_the_task_graph(self):
        subject = interpret(
            command(raw_transcript="شو ضايل علينا مهام؟"),
            result(
                request_kind=VoiceRequestKind.QUESTION,
                summary="what is left",
                query=DetectedQuery(
                    topic=VoiceQueryTopic.REMAINING_TASKS, confidence=0.9
                ),
            ),
            project_tasks(),
        )
        self.assertEqual(subject.status, VoiceAnalysisStatus.COMPLETED)
        self.assertEqual(subject.action_drafts, [])

    def test_an_incomplete_issue_still_asks_what_the_problem_is(self):
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
        self.assertEqual(subject.clarifications[0].field_path, "payload.issue")

    def test_the_previously_added_query_topics_still_route_the_same_way(self):
        for topic in (VoiceQueryTopic.PROJECT_PROGRESS, VoiceQueryTopic.OPEN_ISSUES,
                      VoiceQueryTopic.REPORT_READINESS, VoiceQueryTopic.NEXT_TASK):
            with self.subTest(topic=topic):
                decision = route_request(spoken_result(
                    "question",
                    request_kind=VoiceRequestKind.QUESTION,
                    query=DetectedQuery(topic=topic, confidence=0.9),
                ))
                self.assertEqual(decision.route, VoiceRoute.ANSWER)
                self.assertEqual(decision.topic, topic)
