"""The AI action payload contract, and the ordering that identifies actions.

Both of these pin a real production failure. One voice note produced
`UPDATE_TASK_PROGRESS` and `SUBMIT_TASK_FOR_REVIEW`; the review action is the
one that reaches the consultant. Nothing executed, and the consultant was
never notified, because:

  * the model emitted payload fields the rules engine forbade — it had never
    been told the contract it would be judged against; and
  * `VoiceAnalysis.action_drafts` was ordered by `created_at`, which is
    identical for every draft of one analysis, so the "order" was a tie that
    could come back differently between two requests of one confirmation.
"""

from types import SimpleNamespace
from unittest import TestCase

from app.ai.action_payload_contract import (
    ACTION_CONTRACTS,
    allowed_fields,
    rejection_detail,
    render_prompt_contract,
)
from app.ai.construction_analysis_service import PROMPT_VERSION, SYSTEM_PROMPT
from app.models.voice_analysis import VoiceAnalysis
from app.schemas.voice_analysis import SuggestedActionType
from app.schemas.voice_command import VoiceDraftOut


class ActionPayloadContractTests(TestCase):
    def test_every_action_type_has_a_contract(self):
        # A new action type without a contract would raise a KeyError inside
        # the validator at execution time — the worst possible moment.
        for action_type in SuggestedActionType:
            self.assertIn(action_type, ACTION_CONTRACTS, action_type.value)

    def test_required_fields_are_allowed_fields(self):
        for action_type, contract in ACTION_CONTRACTS.items():
            for field in contract.required:
                self.assertIn(field, contract.allowed, action_type.value)

    def test_the_two_actions_from_the_production_failure(self):
        self.assertEqual(
            allowed_fields(SuggestedActionType.UPDATE_TASK_PROGRESS),
            {"progressPercentage", "note", "correctionConfirmed"},
        )
        self.assertEqual(
            allowed_fields(SuggestedActionType.SUBMIT_TASK_FOR_REVIEW),
            {"completionNote"},
        )

    def test_the_fields_the_model_actually_emitted_are_still_refused(self):
        # The contract is not relaxed to accommodate the model: these actions
        # perform real project operations, and an invented field is evidence
        # the model misunderstood the request.
        for field in ("subject", "location", "recipientRoles", "sourceDiscipline"):
            self.assertNotIn(
                field, allowed_fields(SuggestedActionType.SUBMIT_TASK_FOR_REVIEW)
            )
        self.assertNotIn(
            "location", allowed_fields(SuggestedActionType.UPDATE_TASK_PROGRESS)
        )

    def test_rejection_names_both_the_offence_and_the_contract(self):
        detail = rejection_detail(
            SuggestedActionType.UPDATE_TASK_PROGRESS,
            {"location", "subject"},
        )
        # What was wrong...
        self.assertIn("location", detail)
        self.assertIn("subject", detail)
        # ...and what would have been right. The old message gave only the
        # former, which taught neither the user nor the model anything.
        self.assertIn("Allowed fields", detail)
        self.assertIn("progressPercentage", detail)

    def test_an_action_with_no_payload_says_so(self):
        detail = rejection_detail(SuggestedActionType.START_TASK, {"note"})
        self.assertIn("none", detail)


class PromptContractTests(TestCase):
    def test_the_prompt_states_the_payload_contract(self):
        # The prompt described action *types* but never their payload fields,
        # which is the gap the model fell through.
        self.assertIn("ACTION PAYLOAD CONTRACT", SYSTEM_PROMPT)

    def test_every_action_and_its_allowed_fields_reach_the_prompt(self):
        rendered = render_prompt_contract()
        for action_type, contract in ACTION_CONTRACTS.items():
            self.assertIn(action_type.value, rendered)
            for field in contract.allowed:
                self.assertIn(field, rendered)

    def test_the_prompt_forbids_moving_fields_between_actions(self):
        rendered = render_prompt_contract()
        self.assertIn("Never move a field from one", rendered)
        self.assertIn("resolves recipients itself", rendered)

    def test_prompt_version_was_bumped_with_the_contract(self):
        # A cached v2 response set predates the contract and is no longer
        # representative of what the model is now told.
        self.assertEqual(PROMPT_VERSION, "construction_voice_assistant_v3")

    def test_rendering_is_stable(self):
        # An unstable prompt would defeat provider-side prompt caching.
        self.assertEqual(render_prompt_contract(), render_prompt_contract())

    def test_the_prompt_is_derived_not_duplicated(self):
        # Adding a field to the contract must change the prompt, or the two
        # definitions have drifted apart again.
        self.assertIn(
            "completionNote",
            render_prompt_contract(),
        )


class DraftOrderingTests(TestCase):
    def test_drafts_are_ordered_by_sequence_not_by_timestamp(self):
        relationship = VoiceAnalysis.__mapper__.relationships["action_drafts"]
        order_by = [str(item) for item in relationship.order_by]
        self.assertEqual(
            order_by,
            ["voice_action_drafts.sequence"],
            "created_at is identical for every draft of one analysis, so "
            "ordering by it is a tie and the list can reorder between "
            "requests",
        )

    def test_sequence_is_exposed_to_clients(self):
        # A client cannot bind a reviewed action to its draft without a
        # stable identifier; position in the serialized list is not one.
        self.assertIn("sequence", VoiceDraftOut.model_fields)

    def test_sequence_survives_serialization(self):
        payload = VoiceDraftOut.model_validate(
            SimpleNamespace(
                id="00000000-0000-0000-0000-000000000001",
                client_action_id="a2-abc",
                sequence=1,
                action_type=SuggestedActionType.SUBMIT_TASK_FOR_REVIEW,
                target_entity_type="TASK",
                target_entity_id=None,
                extracted_payload={"completionNote": "x"},
                user_edited_payload=None,
                target_snapshot=None,
                confidence=0.98,
                missing_fields=[],
                warnings=[],
                risk_level="HIGH",
                required_evidence=[],
                selected_for_execution=True,
                execution_status="DRAFT",
                execution_error=None,
                created_at="2026-08-17T17:00:57Z",
                updated_at="2026-08-17T17:00:57Z",
            )
        ).model_dump(by_alias=True)
        self.assertEqual(payload["sequence"], 1)
