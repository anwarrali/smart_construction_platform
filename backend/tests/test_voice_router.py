"""The routing decision, tested without a database.

`route_request` is pure, which is the point: "what did the engineer want" is
decided from the structured result alone, and "what is true" is answered
afterwards by whichever capability the route names. Testing it in isolation is
what makes the decision boundary inspectable instead of emergent.

The rule every test here defends: **an empty action list is a decision, not a
gap.** Filling it with a note — or with a question offering a note — was the
original architectural bug in two successive disguises.
"""

from unittest import TestCase
from uuid import uuid4

from app.schemas.voice_analysis import (
    ConstructionVoiceResult,
    DetectedDiscipline,
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
from app.services.voice_router import VoiceRoute, needs_progress_draft, route_request


def result(**overrides) -> ConstructionVoiceResult:
    values = {
        "summary": "spoken content",
        "detected_task": DetectedTask(confidence=0.5),
        "progress": DetectedProgress(confidence=1.0),
        "discipline": DetectedDiscipline(confidence=0.0),
        "location": DetectedLocation(),
    }
    values.update(overrides)
    return ConstructionVoiceResult(**values)


def action(kind: SuggestedActionType, **payload) -> SuggestedAction:
    defaults = {
        SuggestedActionType.START_TASK: {"target_id": uuid4()},
        SuggestedActionType.CREATE_ISSUE: {
            "payload": {"title": "Rain delay", "description": "Work stopped"}
        },
        # The schema requires a recipient for owner updates; the router runs
        # after that validation, so the fixture has to satisfy it.
        SuggestedActionType.SEND_OWNER_UPDATE: {
            "payload": {
                "content": "Rain has delayed the works",
                "recipientIds": [str(uuid4())],
            }
        },
        SuggestedActionType.SEND_PROJECT_MESSAGE: {
            "payload": {
                "content": "Materials have not arrived",
                "recipientIds": [str(uuid4())],
            }
        },
        SuggestedActionType.UPDATE_TASK_PROGRESS: {
            "target_id": uuid4(), "payload": {"progressPercentage": 50}
        },
    }
    values = {"type": kind, "reason": "spoken", "confidence": 0.9}
    values.update(defaults.get(kind, {}))
    values.update(payload)
    return SuggestedAction(**values)


class ActionRoutingTests(TestCase):
    """A proposed handler is a mutation and keeps its confirmation step."""

    def test_a_proposed_handler_routes_to_the_action_path(self):
        decision = route_request(result(
            suggested_actions=[action(SuggestedActionType.START_TASK)]
        ))
        self.assertEqual(decision.route, VoiceRoute.ACTION)

    def test_an_issue_proposal_is_an_action_not_a_question(self):
        decision = route_request(result(
            suggested_actions=[action(SuggestedActionType.CREATE_ISSUE)],
            detected_intents=[VoiceIntent.REPORT_TASK_BLOCKER],
        ))
        self.assertEqual(decision.route, VoiceRoute.ACTION)

    def test_a_proposal_outranks_a_stray_question_classification(self):
        # If the model both proposed a mutation and called it a question, the
        # proposal wins: routing it to the answer path would silently discard
        # a mutation the engineer may have asked for.
        decision = route_request(result(
            request_kind=VoiceRequestKind.QUESTION,
            suggested_actions=[action(SuggestedActionType.START_TASK)],
        ))
        self.assertEqual(decision.route, VoiceRoute.ACTION)


class QuestionRoutingTests(TestCase):
    def test_an_explicit_question_routes_to_the_answer_path(self):
        decision = route_request(result(
            request_kind=VoiceRequestKind.QUESTION,
            query=DetectedQuery(topic=VoiceQueryTopic.REMAINING_TASKS, confidence=0.9),
        ))
        self.assertEqual(decision.route, VoiceRoute.ANSWER)
        self.assertEqual(decision.topic, VoiceQueryTopic.REMAINING_TASKS)

    def test_an_information_intent_alone_is_enough(self):
        # `request_kind` left at its ACTION default, but the semantic taxonomy
        # says this is a request for information. One wrong field must not
        # reroute the utterance — this is the corroboration the first version
        # lacked, and the reason "شو ضايل علينا مهام؟" reached a task picker.
        decision = route_request(result(
            detected_intents=[VoiceIntent.REQUEST_INFORMATION],
        ))
        self.assertEqual(decision.route, VoiceRoute.ANSWER)

    def test_a_topic_is_recovered_from_intent_when_the_field_is_unset(self):
        decision = route_request(result(
            request_kind=VoiceRequestKind.QUESTION,
            detected_intents=[VoiceIntent.REQUEST_TASK_INFORMATION],
            query=DetectedQuery(topic=VoiceQueryTopic.UNKNOWN, confidence=0.3),
        ))
        self.assertEqual(decision.route, VoiceRoute.ANSWER)
        self.assertEqual(decision.topic, VoiceQueryTopic.TASK_STATUS)
        self.assertIn("inferred", decision.reason)

    def test_an_explicit_topic_is_preferred_over_the_intent_fallback(self):
        decision = route_request(result(
            request_kind=VoiceRequestKind.QUESTION,
            detected_intents=[VoiceIntent.REQUEST_TASK_INFORMATION],
            query=DetectedQuery(topic=VoiceQueryTopic.TASK_BLOCKERS, confidence=0.9),
        ))
        self.assertEqual(decision.topic, VoiceQueryTopic.TASK_BLOCKERS)


class CommunicationRoutingTests(TestCase):
    def test_an_owner_update_is_communication_not_a_task_action(self):
        decision = route_request(result(
            suggested_actions=[action(SuggestedActionType.SEND_OWNER_UPDATE)],
        ))
        self.assertEqual(decision.route, VoiceRoute.COMMUNICATION)

    def test_a_communication_intent_without_a_handler_still_routes_there(self):
        # "بدي أبعت للمالك رسالة" with no recipient resolved yet. The missing
        # piece is a recipient, so asking "which task do you mean?" is the one
        # reply guaranteed to be wrong.
        decision = route_request(result(
            request_kind=VoiceRequestKind.COMMUNICATION,
            detected_intents=[VoiceIntent.SEND_OWNER_UPDATE],
        ))
        self.assertEqual(decision.route, VoiceRoute.COMMUNICATION)

    def test_a_task_scoped_message_stays_on_the_action_path(self):
        # CREATE_TASK_MESSAGE needs a task and already works; moving it would
        # change behaviour that is not broken.
        decision = route_request(result(
            suggested_actions=[action(
                SuggestedActionType.CREATE_TASK_MESSAGE,
                target_id=uuid4(),
                payload={"content": "Please check the rebar spacing"},
            )],
        ))
        self.assertEqual(decision.route, VoiceRoute.ACTION)


class ProgressRoutingTests(TestCase):
    def test_a_stated_percentage_without_a_handler_reaches_the_progress_path(self):
        # "وصلنا لنص الشغل" with several plausible tasks: the model extracted a
        # figure but could not name a target. That belongs to progress, with the
        # normal target clarification — not to a note.
        subject = result(
            progress=DetectedProgress(
                mentioned=True, percentage=50, approximate=True, confidence=0.8
            ),
        )
        self.assertEqual(route_request(subject).route, VoiceRoute.ACTION)
        self.assertTrue(needs_progress_draft(subject))

    def test_a_vague_progress_statement_does_not_manufacture_an_action(self):
        # "خلص تقريباً كله" — mentioned, but no defensible number, so there is
        # nothing to propose and nothing to confirm.
        subject = result(
            progress=DetectedProgress(mentioned=True, percentage=None, confidence=0.4),
        )
        self.assertEqual(route_request(subject).route, VoiceRoute.CLARIFICATION)
        self.assertFalse(needs_progress_draft(subject))

    def test_synthesis_never_fires_when_the_model_already_proposed_something(self):
        subject = result(
            suggested_actions=[action(SuggestedActionType.UPDATE_TASK_PROGRESS)],
            progress=DetectedProgress(mentioned=True, percentage=50, confidence=0.9),
        )
        self.assertFalse(needs_progress_draft(subject))


class FallbackTests(TestCase):
    """The behaviour this whole redesign exists to change."""

    def test_nothing_identifiable_asks_rather_than_proposing(self):
        decision = route_request(result())
        self.assertEqual(decision.route, VoiceRoute.CLARIFICATION)

    def test_zero_actions_never_routes_to_a_mutation(self):
        # Across every empty-action shape, no route is ACTION unless a real
        # progress figure justified it.
        shapes = [
            result(),
            result(request_kind=VoiceRequestKind.STATEMENT),
            result(detected_intents=[VoiceIntent.NO_ACTION_REQUIRED]),
            result(detected_intents=[VoiceIntent.NEEDS_CLARIFICATION]),
            result(summary="workers were on site today"),
        ]
        for subject in shapes:
            self.assertNotEqual(
                route_request(subject).route,
                VoiceRoute.ACTION,
                msg=f"empty-action result routed to a mutation: {subject.summary}",
            )

    def test_every_decision_names_its_reason(self):
        # The reason is recorded on the command; a route nobody can explain is
        # a route nobody can fix.
        for subject in [
            result(),
            result(request_kind=VoiceRequestKind.QUESTION),
            result(suggested_actions=[action(SuggestedActionType.START_TASK)]),
            result(suggested_actions=[action(SuggestedActionType.SEND_OWNER_UPDATE)]),
        ]:
            self.assertTrue(route_request(subject).reason.strip())

    def test_routing_is_total(self):
        # Every shape produces exactly one of the four routes; there is no
        # implicit fall-through.
        routes = {
            route_request(subject).route
            for subject in [
                result(),
                result(request_kind=VoiceRequestKind.QUESTION),
                result(request_kind=VoiceRequestKind.COMMUNICATION,
                       detected_intents=[VoiceIntent.SEND_MESSAGE]),
                result(suggested_actions=[action(SuggestedActionType.START_TASK)]),
            ]
        }
        self.assertTrue(routes <= set(VoiceRoute))
        self.assertEqual(len(routes), 4)
