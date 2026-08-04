from unittest import TestCase
from uuid import uuid4

from app.ai.construction_analysis_service import validate_recipient_scope
from app.schemas.voice_analysis import (
    ConstructionVoiceResult,
    DetectedDiscipline,
    DetectedLocation,
    DetectedProgress,
    DetectedTask,
    SuggestedAction,
    SuggestedActionType,
    VoiceIntent,
)
from app.services.voice_action_policy import action_risk, requires_detailed_confirmation


def result_with(action):
    return ConstructionVoiceResult(
        summary="Prepared action",
        detected_intents=[VoiceIntent.SEND_OWNER_UPDATE],
        detected_task=DetectedTask(confidence=0),
        progress=DetectedProgress(confidence=0),
        discipline=DetectedDiscipline(confidence=0),
        location=DetectedLocation(),
        suggested_actions=[action],
    )


class VoiceAssistantV2PolicyTests(TestCase):
    def test_owner_update_is_high_risk(self):
        self.assertTrue(requires_detailed_confirmation(SuggestedActionType.SEND_OWNER_UPDATE))

    def test_worker_submission_is_low_risk(self):
        self.assertEqual(action_risk(SuggestedActionType.CREATE_FIELD_SUBMISSION).value, "LOW")

    def test_design_change_cannot_be_spoken_as_approved(self):
        with self.assertRaisesRegex(ValueError, "approved"):
            SuggestedAction(
                type=SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT,
                reason="Routing changed",
                payload={"title": "Routing", "description": "Changed", "approved": True},
                confidence=.9,
            )

    def test_recipient_injection_is_rejected(self):
        allowed, injected = uuid4(), uuid4()
        action = SuggestedAction(
            type=SuggestedActionType.SEND_PROJECT_MESSAGE,
            reason="Send update",
            payload={"content": "Update", "recipientIds": [injected]},
            confidence=.9,
        )
        with self.assertRaisesRegex(ValueError, "recipient outside"):
            validate_recipient_scope(result_with(action), {str(allowed)})

    def test_exact_candidate_recipient_is_allowed(self):
        allowed = uuid4()
        action = SuggestedAction(
            type=SuggestedActionType.SEND_PROJECT_MESSAGE,
            reason="Send update",
            payload={"content": "Update", "recipientIds": [allowed]},
            confidence=.9,
        )
        validate_recipient_scope(result_with(action), {str(allowed)})
