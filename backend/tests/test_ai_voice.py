import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.ai.action_analyzer import ActionAnalyzer
from app.ai.action_rules import validate_proposed_action
from app.ai.action_schemas import VoiceAction, VoiceActionType
from app.ai.exceptions import AIConfigurationError, InvalidAudioError
from app.ai.transcription_service import TranscriptionService, validate_audio
from app.ai.construction_analysis_service import (
    ConstructionVoiceAnalysisService,
    guard_measurements,
    validate_task_scope,
)
from app.api.ai import _read_limited_audio
from app.core.config import settings
from app.main import app
from app.schemas.voice_analysis import (
    ConstructionVoiceResult,
    DetectedDiscipline,
    DetectedLocation,
    DetectedProgress,
    DetectedTask,
    SuggestedAction,
    SuggestedActionType,
)
from app.services.voice_action_service import action_allowed_for_role
from app.services.voice_action_service import _execute_one
from app.services.voice_analysis_authorization import can_create_voice_analysis
from app.models.enums import UserRole, UserStatus


def valid_m4a() -> bytes:
    return b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 64


class TranscriptionServiceTests(TestCase):
    def test_rejects_empty_audio(self):
        with self.assertRaisesRegex(InvalidAudioError, "empty"):
            validate_audio("field.m4a", "audio/mp4", b"")

    def test_rejects_unsupported_audio(self):
        with self.assertRaisesRegex(InvalidAudioError, "Unsupported"):
            validate_audio("field.exe", "application/octet-stream", b"MZ")

    def test_rejects_content_that_does_not_match_extension(self):
        with self.assertRaisesRegex(InvalidAudioError, "does not match"):
            validate_audio("field.m4a", "audio/mp4", b"not-an-m4a")

    def test_missing_key_returns_clean_configuration_error(self):
        with patch.object(settings, "OPENAI_API_KEY", None):
            with self.assertRaisesRegex(AIConfigurationError, "OPENAI_API_KEY"):
                TranscriptionService().transcribe(
                    filename="field.m4a",
                    content_type="audio/mp4",
                    content=valid_m4a(),
                )

    def test_successful_transcription_uses_official_audio_client(self):
        create = Mock(return_value=SimpleNamespace(text="تم إنجاز سبعين بالمئة", language="ar"))
        client = SimpleNamespace(
            audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
        )
        result = TranscriptionService(client).transcribe(
            filename="field.m4a",
            content_type="audio/mp4",
            content=valid_m4a(),
        )
        self.assertTrue(result.success)
        self.assertEqual(result.language, "ar")
        self.assertIn("سبعين", result.transcript)
        create.assert_called_once()

    def test_upload_reader_rejects_empty_audio(self):
        upload = UploadFile(filename="empty.m4a", file=BytesIO(b""))
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(_read_limited_audio(upload))
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "Uploaded audio is empty.")


class ActionFoundationTests(TestCase):
    def test_progress_schema_rejects_out_of_range_values(self):
        with self.assertRaisesRegex(ValueError, "less than or equal to 100"):
            VoiceAction(
                action_type=VoiceActionType.UPDATE_TASK_PROGRESS,
                progress_percentage=120,
                confidence=0.9,
            )

    def test_task_name_requires_clarification_instead_of_guessing(self):
        project_id = uuid4()
        action = VoiceAction(
            action_type=VoiceActionType.UPDATE_TASK_PROGRESS,
            task_reference="electrical wiring",
            progress_percentage=70,
            confidence=0.94,
        )
        proposal, result = validate_proposed_action(
            action,
            selected_project_id=project_id,
            user_role="engineer",
        )
        self.assertEqual(proposal.project_id, project_id)
        self.assertTrue(proposal.requires_clarification)
        self.assertFalse(result.valid)

    def test_analysis_endpoint_foundation_never_marks_action_executable(self):
        parsed = VoiceAction(
            action_type=VoiceActionType.CREATE_ISSUE,
            description="Water leakage near the basement wall",
            confidence=0.91,
        )
        client = SimpleNamespace(
            responses=SimpleNamespace(
                parse=Mock(return_value=SimpleNamespace(output_parsed=parsed))
            )
        )
        result = ActionAnalyzer(client).analyze("Water leakage near the basement wall")
        self.assertEqual(result.action_type, VoiceActionType.CREATE_ISSUE)
        self.assertTrue(result.requires_confirmation)


class AIEndpointSecurityTests(TestCase):
    def test_transcription_requires_authentication(self):
        response = TestClient(app).post("/api/v1/ai/transcribe")
        self.assertEqual(response.status_code, 401)

    def test_voice_analysis_upload_requires_authentication(self):
        response = TestClient(app).post("/api/v1/ai/voice-analyses")
        self.assertEqual(response.status_code, 401)


def structured_result(*, progress=70, actions=None, task_id=None):
    return ConstructionVoiceResult(
        summary="Electrical installation update",
        detected_task=DetectedTask(
            task_id=task_id, task_title="Electrical Floor 2", confidence=.9,
        ),
        progress=DetectedProgress(
            mentioned=progress is not None, percentage=progress, confidence=.9,
        ),
        discipline=DetectedDiscipline(value="electrical", confidence=.95),
        location=DetectedLocation(text="Second floor"),
        work_completed=["Electrical rough-in"],
        problems=[],
        materials=[],
        suggested_actions=actions or [],
    )


class StructuredConstructionAnalysisTests(TestCase):
    def test_malformed_provider_action_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "progressPercentage"):
            SuggestedAction(
                type=SuggestedActionType.UPDATE_TASK_PROGRESS,
                target_id=uuid4(),
                reason="Progress mentioned",
                payload={"progressPercentage": "seventy"},
                confidence=.9,
            )

    def test_progress_is_bounded_zero_to_one_hundred(self):
        with self.assertRaises(ValueError):
            DetectedProgress(mentioned=True, percentage=101, confidence=.8)

    def test_quantity_is_not_promoted_to_progress(self):
        task_id = uuid4()
        action = SuggestedAction(
            type=SuggestedActionType.UPDATE_TASK_PROGRESS,
            target_id=task_id,
            reason="Number interpreted",
            payload={"progressPercentage": 70},
            confidence=.8,
        )
        guarded = guard_measurements(
            "We need 70 meters of cable in the eastern section.",
            structured_result(progress=70, actions=[action], task_id=task_id),
        )
        self.assertFalse(guarded.progress.mentioned)
        self.assertEqual(guarded.suggested_actions, [])

    def test_explicit_percentage_survives_measurement_guard(self):
        result = guard_measurements(
            "Electrical is 70 percent complete.",
            structured_result(progress=70),
        )
        self.assertEqual(result.progress.percentage, 70)

    def test_cross_project_task_suggestion_is_rejected(self):
        outside = uuid4()
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_task_scope(
                structured_result(progress=None, task_id=outside),
                {str(uuid4())},
            )

    def test_ai_cannot_invent_action_names(self):
        with self.assertRaises(ValueError):
            SuggestedAction.model_validate({
                "type": "DELETE_PROJECT",
                "reason": "unsafe",
                "confidence": 1,
                "payload": {},
            })

    def test_analysis_output_is_only_a_proposal(self):
        result = structured_result(
            actions=[
                SuggestedAction(
                    type=SuggestedActionType.CREATE_ISSUE,
                    reason="Material missing",
                    payload={"title": "Cable delay", "description": "Cable not delivered"},
                    confidence=.9,
                )
            ],
        )
        self.assertEqual(len(result.suggested_actions), 1)
        self.assertFalse(hasattr(result, "execute"))

    def test_original_mixed_language_transcript_is_preserved(self):
        parsed = structured_result(progress=60)
        client = SimpleNamespace(
            responses=SimpleNamespace(
                parse=Mock(return_value=SimpleNamespace(output_parsed=parsed))
            )
        )
        transcript = "خلصنا 60% من الـ electrical rough-in"
        result = ConstructionVoiceAnalysisService(client).analyze(
            transcript=transcript,
            user_role="contractor_engineer",
            authorized_tasks=[],
        )
        self.assertEqual(result.progress.percentage, 60)
        sent = client.responses.parse.call_args.kwargs["input"][1]["content"]
        self.assertIn(transcript, sent)


class VoiceConfirmationPolicyTests(TestCase):
    def test_engineer_may_confirm_progress(self):
        self.assertTrue(action_allowed_for_role(
            "engineer", SuggestedActionType.UPDATE_TASK_PROGRESS,
        ))

    def test_worker_cannot_confirm_official_progress(self):
        self.assertFalse(action_allowed_for_role(
            "worker", SuggestedActionType.UPDATE_TASK_PROGRESS,
        ))

    def test_worker_may_confirm_unverified_field_submission(self):
        self.assertTrue(action_allowed_for_role(
            "worker", SuggestedActionType.CREATE_FIELD_SUBMISSION,
        ))

    def test_worker_cannot_confirm_issue_or_message(self):
        self.assertFalse(action_allowed_for_role(
            "worker", SuggestedActionType.CREATE_ISSUE,
        ))
        self.assertFalse(action_allowed_for_role(
            "worker", SuggestedActionType.CREATE_TASK_MESSAGE,
        ))

    def test_site_report_action_is_draft_only(self):
        self.assertIn(
            "DRAFT", SuggestedActionType.CREATE_SITE_REPORT_DRAFT.value,
        )

    def test_engineer_confirmation_calls_normal_progress_service(self):
        user = SimpleNamespace(
            id=uuid4(), role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
            engineer_affiliation="main_contractor", full_name="Engineer",
        )
        project_id, task_id, analysis_id = uuid4(), uuid4(), uuid4()
        analysis = SimpleNamespace(id=analysis_id, project_id=project_id)
        action = SuggestedAction(
            type=SuggestedActionType.UPDATE_TASK_PROGRESS,
            target_id=task_id, reason="Progress reported",
            payload={"progressPercentage": 65}, confidence=.9,
        )
        with (
            patch("app.services.voice_action_service.user_has_project_access", return_value=True),
            patch("app.services.voice_action_service._task", return_value=SimpleNamespace(id=task_id)),
            patch(
                "app.services.voice_action_service.update_task_progress",
                return_value=SimpleNamespace(id=task_id),
            ) as update,
        ):
            result = _execute_one(
                Mock(), analysis=analysis, current_user=user,
                action=action, action_index=0,
            )
        self.assertTrue(result.success)
        self.assertEqual(update.call_args.kwargs["audit_metadata"]["analysis_id"], str(analysis_id))
        self.assertEqual(update.call_args.kwargs["progress_percentage"], 65)

    def test_worker_execution_rejects_official_progress(self):
        user = SimpleNamespace(
            id=uuid4(), role=UserRole.WORKER, status=UserStatus.ACTIVE,
            full_name="Worker",
        )
        action = SuggestedAction(
            type=SuggestedActionType.UPDATE_TASK_PROGRESS,
            target_id=uuid4(), reason="Worker reported progress",
            payload={"progressPercentage": 80}, confidence=.9,
        )
        with patch(
            "app.services.voice_action_service.user_has_project_access",
            return_value=True,
        ):
            with self.assertRaises(HTTPException) as raised:
                _execute_one(
                    Mock(),
                    analysis=SimpleNamespace(id=uuid4(), project_id=uuid4()),
                    current_user=user, action=action, action_index=0,
                )
        self.assertIn("cannot confirm", raised.exception.detail)

    def test_worker_confirmation_creates_unverified_field_submission(self):
        user_id, project_id, task_id, submission_id = (
            uuid4(), uuid4(), uuid4(), uuid4(),
        )
        user = SimpleNamespace(
            id=user_id, role=UserRole.WORKER, status=UserStatus.ACTIVE,
            full_name="Worker",
        )
        analysis = SimpleNamespace(
            id=uuid4(), project_id=project_id, field_submission_id=None,
        )
        task = SimpleNamespace(id=task_id, task_code="EL-02")
        submission = SimpleNamespace(id=submission_id, status=None)
        db = Mock()
        db.get.return_value = SimpleNamespace(project_manager_id=user_id)
        action = SuggestedAction(
            type=SuggestedActionType.CREATE_FIELD_SUBMISSION,
            target_id=task_id, reason="Worker evidence",
            payload={"description": "First waterproofing layer completed"},
            confidence=.9,
        )
        with (
            patch("app.services.voice_action_service.user_has_project_access", return_value=True),
            patch("app.services.voice_action_service._task", return_value=task),
            patch("app.services.voice_action_service.can_worker_submit_evidence", return_value=True),
            patch("app.services.voice_action_service.authorized_engineer_ids", return_value=set()),
            patch("app.services.voice_action_service.FieldSubmission", return_value=submission),
            patch("app.services.voice_action_service.record_audit"),
        ):
            result = _execute_one(
                db, analysis=analysis, current_user=user,
                action=action, action_index=0,
            )
        self.assertTrue(result.success)
        self.assertEqual(result.entity_id, submission_id)
        self.assertEqual(analysis.field_submission_id, submission_id)
        db.commit.assert_called_once()

    def test_engineer_can_start_analysis_for_assigned_task(self):
        user = SimpleNamespace(
            id=uuid4(), role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
            engineer_affiliation="main_contractor",
        )
        task = SimpleNamespace(project_id=uuid4(), assignees=[user])
        with patch(
            "app.services.voice_analysis_authorization.user_has_project_access",
            return_value=True,
        ):
            self.assertTrue(
                can_create_voice_analysis(Mock(), user, task.project_id, task)
            )

    def test_worker_can_start_analysis_for_assigned_task(self):
        user = SimpleNamespace(
            id=uuid4(), role=UserRole.WORKER, status=UserStatus.ACTIVE,
        )
        task = SimpleNamespace(project_id=uuid4())
        with (
            patch(
                "app.services.voice_analysis_authorization.user_has_project_access",
                return_value=True,
            ),
            patch(
                "app.services.voice_analysis_authorization.can_worker_submit_evidence",
                return_value=True,
            ),
        ):
            self.assertTrue(
                can_create_voice_analysis(Mock(), user, task.project_id, task)
            )

    def test_inaccessible_project_cannot_start_analysis(self):
        user = SimpleNamespace(
            id=uuid4(), role=UserRole.WORKER, status=UserStatus.ACTIVE,
        )
        with patch(
            "app.services.voice_analysis_authorization.user_has_project_access",
            return_value=False,
        ):
            self.assertFalse(
                can_create_voice_analysis(Mock(), user, uuid4(), None)
            )

    def test_issue_confirmation_uses_existing_issue_domain_fields(self):
        user = SimpleNamespace(
            id=uuid4(), role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
            engineer_affiliation="main_contractor", full_name="Engineer",
        )
        analysis = SimpleNamespace(id=uuid4(), project_id=uuid4())
        issue_id = uuid4()
        issue = SimpleNamespace(id=issue_id, title="Cable delivery delay")
        db = Mock()
        db.get.return_value = SimpleNamespace(project_manager_id=user.id)
        action = SuggestedAction(
            type=SuggestedActionType.CREATE_ISSUE,
            reason="Material is missing",
            payload={
                "title": issue.title,
                "description": "Cables have not arrived",
                "category": "material_delay",
                "severity": "high",
            },
            confidence=.94,
        )
        with (
            patch("app.services.voice_action_service.user_has_project_access", return_value=True),
            patch("app.services.voice_action_service._optional_task", return_value=None),
            patch("app.services.voice_action_service.Issue", return_value=issue) as issue_model,
            patch("app.services.voice_action_service.record_audit"),
        ):
            result = _execute_one(
                db, analysis=analysis, current_user=user,
                action=action, action_index=0,
            )
        self.assertTrue(result.success)
        self.assertEqual(issue_model.call_args.kwargs["category"], "material_delay")
        self.assertEqual(issue_model.call_args.kwargs["severity"].value, "high")

    def test_site_report_confirmation_always_creates_draft(self):
        user = SimpleNamespace(
            id=uuid4(), role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
            engineer_affiliation="main_contractor", full_name="Engineer",
        )
        analysis = SimpleNamespace(id=uuid4(), project_id=uuid4())
        report = SimpleNamespace(id=uuid4())
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = object()
        action = SuggestedAction(
            type=SuggestedActionType.CREATE_SITE_REPORT_DRAFT,
            reason="Enough daily report detail",
            payload={"summaryText": "Electrical works progressed today."},
            confidence=.85,
        )
        with (
            patch("app.services.voice_action_service.user_has_project_access", return_value=True),
            patch("app.services.voice_action_service._optional_task", return_value=None),
            patch("app.services.voice_action_service.SiteReport", return_value=report) as report_model,
            patch("app.services.voice_action_service.record_audit"),
        ):
            result = _execute_one(
                db, analysis=analysis, current_user=user,
                action=action, action_index=0,
            )
        self.assertTrue(result.success)
        self.assertEqual(report_model.call_args.kwargs["review_status"], "draft")
        self.assertEqual(report_model.call_args.kwargs["voice_analysis_id"], analysis.id)

    def test_action_analysis_requires_authentication(self):
        response = TestClient(app).post(
            "/api/v1/ai/analyze-command",
            json={"transcript": "Update wiring to 70 percent", "projectId": str(uuid4())},
        )
        self.assertEqual(response.status_code, 401)
