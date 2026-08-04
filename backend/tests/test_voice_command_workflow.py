from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.enums import UserRole, UserStatus, VoiceAnalysisStatus
from app.schemas.voice_analysis import (
    ConstructionVoiceResult,
    DetectedLocation,
    SuggestedAction,
    SuggestedActionType,
)
from app.services.voice_command_service import transition
from app.services.voice_rules_engine import VoiceRulesEngine


class VoiceStateMachineTests(TestCase):
    def test_cancelled_command_cannot_execute(self):
        command = SimpleNamespace(
            status=VoiceAnalysisStatus.CANCELLED,
            row_version=2,
        )
        with self.assertRaises(HTTPException):
            transition(command, VoiceAnalysisStatus.EXECUTING)

    def test_ready_command_requires_confirmation_before_execution(self):
        command = SimpleNamespace(
            status=VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
            row_version=3,
        )
        with self.assertRaises(HTTPException):
            transition(command, VoiceAnalysisStatus.EXECUTING)

    def test_valid_confirmation_increments_optimistic_version(self):
        command = SimpleNamespace(
            status=VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
            row_version=7,
        )
        transition(command, VoiceAnalysisStatus.CONFIRMED)
        self.assertEqual(command.status, VoiceAnalysisStatus.CONFIRMED)
        self.assertEqual(command.row_version, 8)


class StrictVoiceSchemaTests(TestCase):
    def test_structured_voice_objects_reject_additional_properties(self):
        with self.assertRaises(ValidationError):
            DetectedLocation.model_validate({
                "text": "Second floor",
                "untrustedOperation": "DELETE_PROJECT",
            })

    def test_action_payload_rejects_fields_outside_execution_allowlist(self):
        with self.assertRaises(ValidationError):
            SuggestedAction.model_validate({
                "type": SuggestedActionType.CREATE_ISSUE,
                "reason": "Synthetic issue",
                "confidence": 0.9,
                "payload": {
                    "title": "Synthetic issue",
                    "description": "Synthetic description",
                    "deleteProject": True,
                },
            })

    def test_openai_strict_schema_uses_typed_closed_action_payload(self):
        from openai.lib._pydantic import to_strict_json_schema

        schema = to_strict_json_schema(ConstructionVoiceResult)
        self.assertEqual(schema["properties"]["schemaVersion"]["type"], "string")
        payload = schema["$defs"]["SuggestedActionPayload"]
        self.assertFalse(payload["additionalProperties"])
        self.assertIn("progressPercentage", payload["properties"])
        self.assertEqual(set(payload["required"]), set(payload["properties"]))


class VoiceRulesEngineTests(TestCase):
    def _actor(self, role: UserRole):
        return SimpleNamespace(
            id=uuid4(),
            role=role,
            status=UserStatus.ACTIVE,
            engineer_affiliation=None,
        )

    def _command(self, actor):
        return SimpleNamespace(
            id=uuid4(),
            user_id=actor.id,
            project_id=uuid4(),
        )

    def test_worker_cannot_apply_official_progress(self):
        actor = self._actor(UserRole.WORKER)
        command = self._command(actor)
        draft = SimpleNamespace(
            action_type="UPDATE_TASK_PROGRESS",
            missing_fields=[],
            confidence=.99,
            user_edited_payload={"progressPercentage": 100},
        )
        with patch(
            "app.services.voice_rules_engine.user_has_project_access",
            return_value=True,
        ):
            with self.assertRaises(HTTPException) as raised:
                VoiceRulesEngine().validate(
                    Mock(), command=command, draft=draft, actor=actor,
                )
        self.assertEqual(raised.exception.status_code, 403)

    def test_low_confidence_requires_human_edit(self):
        actor = self._actor(UserRole.ENGINEER)
        command = self._command(actor)
        draft = SimpleNamespace(
            action_type="ADD_TASK_NOTE",
            missing_fields=[],
            confidence=.2,
            user_edited_payload=None,
        )
        with patch(
            "app.services.voice_rules_engine.user_has_project_access",
            return_value=True,
        ):
            with self.assertRaises(HTTPException) as raised:
                VoiceRulesEngine().validate(
                    Mock(), command=command, draft=draft, actor=actor,
                )
        self.assertIn("Low-confidence", raised.exception.detail)

    def test_missing_clarification_blocks_execution(self):
        actor = self._actor(UserRole.ENGINEER)
        command = self._command(actor)
        draft = SimpleNamespace(
            action_type="UPDATE_TASK_PROGRESS",
            missing_fields=["progressPercentage"],
            confidence=.9,
            user_edited_payload=None,
        )
        with patch(
            "app.services.voice_rules_engine.user_has_project_access",
            return_value=True,
        ):
            with self.assertRaises(HTTPException) as raised:
                VoiceRulesEngine().validate(
                    Mock(), command=command, draft=draft, actor=actor,
                )
        self.assertEqual(raised.exception.status_code, 409)

    def test_owner_receives_no_new_voice_mutation_permission(self):
        actor = self._actor(UserRole.OWNER)
        command = self._command(actor)
        draft = SimpleNamespace(
            action_type="CREATE_ISSUE",
            missing_fields=[],
            confidence=1,
            user_edited_payload={"title": "Issue", "description": "Details"},
        )
        with patch(
            "app.services.voice_rules_engine.user_has_project_access",
            return_value=True,
        ):
            with self.assertRaises(HTTPException) as raised:
                VoiceRulesEngine().validate(
                    Mock(), command=command, draft=draft, actor=actor,
                )
        self.assertEqual(raised.exception.status_code, 403)
