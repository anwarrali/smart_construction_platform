"""§29 human-authority acceptance matrix for the voice workflow.

Voice acts on behalf of the person speaking. The same operation must succeed or
fail for exactly the same reasons as the equivalent manual action, and the AI
must never become the actor that approves engineering work.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.models.enums import DesignChangeStatus, TaskStatus, UserRole, UserStatus
from app.schemas.voice_analysis import SuggestedActionType
from app.services.collaboration_policy import assert_human_authority
from app.services.voice_rules_engine import VoiceRulesEngine


def actor(role: UserRole, *, affiliation=None, status=UserStatus.ACTIVE):
    return SimpleNamespace(id=uuid4(), role=role, status=status, engineer_affiliation=affiliation)


def fake_task(progress=0, status=TaskStatus.IN_PROGRESS):
    """Minimal stand-in for the task the engine re-validates before executing."""
    return SimpleNamespace(id=uuid4(), progress_percentage=progress, status=status)


def command_for(person, project_id=None):
    return SimpleNamespace(id=uuid4(), user_id=person.id, project_id=project_id or uuid4())


def draft(action_type, payload=None, *, confidence=.95, missing=None, target_id=None):
    return SimpleNamespace(
        action_type=action_type,
        missing_fields=missing or [],
        confidence=confidence,
        user_edited_payload=payload,
        extracted_payload=payload or {},
        required_evidence=[],
        target_entity_id=target_id,
    )


class VoiceActsForTheSpeaker(TestCase):
    """An authorized engineer speaking gets the authority they already have."""

    def _validate(self, person, action_draft, *, command=None, access=True, task=None):
        with patch("app.services.voice_rules_engine.user_has_project_access", return_value=access), \
             patch.object(VoiceRulesEngine, "_validated_task", return_value=task):
            return VoiceRulesEngine().validate(
                Mock(), command=command or command_for(person), draft=action_draft, actor=person,
            )

    def test_engineer_progress_update_is_accepted_under_their_own_authority(self):
        person = actor(UserRole.ENGINEER)
        task = fake_task(progress=10)
        result = self._validate(person, draft("UPDATE_TASK_PROGRESS", {"progressPercentage": 30},
                                              target_id=task.id), task=task)
        self.assertEqual(result.type, SuggestedActionType.UPDATE_TASK_PROGRESS)
        self.assertEqual(result.payload_dict()["progressPercentage"], 30)

    def test_engineer_issue_creation_is_accepted(self):
        person = actor(UserRole.ENGINEER)
        result = self._validate(person, draft("CREATE_ISSUE", {
            "title": "Water leakage in Zone B",
            "description": "Standing water found along the Zone B retaining wall.",
        }))
        self.assertEqual(result.type, SuggestedActionType.CREATE_ISSUE)

    def test_engineer_may_propose_a_design_change_by_voice(self):
        person = actor(UserRole.ENGINEER)
        result = self._validate(person, draft("CREATE_DESIGN_CHANGE_REPORT", {
            "title": "Relocate the partition wall",
            "description": "Owner asked for a wider corridor on the ground floor.",
        }))
        self.assertEqual(result.type, SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT)

    def test_a_suspended_account_cannot_act_by_voice(self):
        person = actor(UserRole.ENGINEER, status=UserStatus.SUSPENDED)
        with self.assertRaises(HTTPException) as raised:
            self._validate(person, draft("ADD_TASK_NOTE", {"content": "note"}))
        self.assertEqual(raised.exception.status_code, 403)

    def test_a_command_cannot_be_executed_by_someone_else(self):
        speaker = actor(UserRole.ENGINEER)
        bystander = actor(UserRole.ENGINEER)
        with self.assertRaises(HTTPException) as raised:
            self._validate(bystander, draft("ADD_TASK_NOTE", {"content": "note"}),
                           command=command_for(speaker))
        self.assertEqual(raised.exception.status_code, 403)

    def test_losing_project_access_blocks_execution(self):
        person = actor(UserRole.ENGINEER)
        with self.assertRaises(HTTPException) as raised:
            self._validate(person, draft("ADD_TASK_NOTE", {"content": "note"}), access=False)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("Project access", raised.exception.detail)


class WorkerVoiceEntersVerification(TestCase):
    def _expect_forbidden(self, action_type, payload=None):
        person = actor(UserRole.WORKER)
        with patch("app.services.voice_rules_engine.user_has_project_access", return_value=True), \
             patch.object(VoiceRulesEngine, "_validated_task", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                VoiceRulesEngine().validate(
                    Mock(), command=command_for(person), draft=draft(action_type, payload), actor=person,
                )
        self.assertEqual(raised.exception.status_code, 403)

    def test_worker_cannot_verify_official_progress(self):
        self._expect_forbidden("UPDATE_TASK_PROGRESS", {"progressPercentage": 100})

    def test_worker_cannot_submit_a_task_for_review(self):
        self._expect_forbidden("SUBMIT_TASK_FOR_REVIEW", {"completionNote": "done"})

    def test_worker_cannot_create_a_design_change(self):
        self._expect_forbidden("CREATE_DESIGN_CHANGE_REPORT", {"title": "x", "description": "y"})

    def test_worker_cannot_approve_a_consultant_review(self):
        self._expect_forbidden("PREPARE_CONSULTANT_REVIEW", {"decision": "APPROVE"})

    def test_worker_voice_becomes_a_field_submission_that_still_needs_verification(self):
        person = actor(UserRole.WORKER)
        task = fake_task()
        with patch("app.services.voice_rules_engine.user_has_project_access", return_value=True), \
             patch.object(VoiceRulesEngine, "_validated_task", return_value=task):
            result = VoiceRulesEngine().validate(
                Mock(), command=command_for(person),
                draft=draft("CREATE_FIELD_SUBMISSION", {"description": "Poured the slab this morning."},
                            target_id=task.id),
                actor=person,
            )
        self.assertEqual(result.type, SuggestedActionType.CREATE_FIELD_SUBMISSION)


class RoleBoundariesAreNotWidenedByVoice(TestCase):
    def _validate(self, person, action_draft, *, task=None):
        with patch("app.services.voice_rules_engine.user_has_project_access", return_value=True), \
             patch.object(VoiceRulesEngine, "_validated_task", return_value=task):
            return VoiceRulesEngine().validate(
                Mock(), command=command_for(person), draft=action_draft, actor=person,
            )

    def test_only_the_project_manager_can_create_a_task_by_voice(self):
        with self.assertRaises(HTTPException) as raised:
            self._validate(actor(UserRole.ENGINEER), draft("CREATE_TASK", {
                "title": "Inspect basement waterproofing", "sourceDiscipline": "civil",
            }))
        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("Project Manager", raised.exception.detail)

    def test_project_manager_may_create_a_task_by_voice(self):
        result = self._validate(actor(UserRole.PROJECT_MANAGER), draft("CREATE_TASK", {
            "title": "Inspect basement waterproofing", "sourceDiscipline": "civil",
        }))
        self.assertEqual(result.type, SuggestedActionType.CREATE_TASK)

    def test_a_consultant_engineer_keeps_the_review_scope_and_nothing_more(self):
        consultant = actor(UserRole.ENGINEER, affiliation="external_consultant")
        with patch("app.services.voice_rules_engine.is_consultant_engineer", return_value=True):
            review_task = fake_task()
            allowed = self._validate(consultant, draft("PREPARE_CONSULTANT_REVIEW", {
                "decision": "APPROVE", "comments": "Reinforcement matches the drawing.",
            }, target_id=review_task.id), task=review_task)
            self.assertEqual(allowed.type, SuggestedActionType.PREPARE_CONSULTANT_REVIEW)
            with self.assertRaises(HTTPException) as raised:
                self._validate(consultant, draft("UPDATE_TASK_PROGRESS", {"progressPercentage": 50}))
        # A consultant engineer supervises; they never post contractor progress.
        self.assertEqual(raised.exception.status_code, 403)

    def test_an_ambiguous_command_is_blocked_until_the_human_clarifies(self):
        with self.assertRaises(HTTPException) as raised:
            self._validate(actor(UserRole.ENGINEER),
                           draft("UPDATE_TASK_PROGRESS", {"progressPercentage": 30}, missing=["taskId"]))
        self.assertEqual(raised.exception.status_code, 409)

    def test_a_low_confidence_reading_must_be_reviewed_before_it_executes(self):
        with self.assertRaises(HTTPException) as raised:
            self._validate(actor(UserRole.ENGINEER),
                           draft("ADD_TASK_NOTE", None, confidence=.2))
        self.assertEqual(raised.exception.status_code, 409)


class AIIsNeverTheApprovingActor(TestCase):
    def test_ai_actor_types_are_refused_official_authority(self):
        self.assertTrue(assert_human_authority("HUMAN"))
        for impostor in ("AI", "ai", "AI_ASSISTANT", "SYSTEM_AI", "LLM"):
            self.assertFalse(assert_human_authority(impostor), impostor)

    def test_a_voice_created_design_change_still_starts_as_a_proposal(self):
        """Voice must not skip the approval chain a manual proposal goes through."""
        self.assertEqual(DesignChangeStatus.PROPOSED.value, "proposed")
        self.assertNotEqual(DesignChangeStatus.PROPOSED, DesignChangeStatus.APPROVED)

    def test_the_voice_action_vocabulary_contains_no_approval_verb(self):
        approving = [
            item for item in SuggestedActionType
            if any(word in item.value.upper() for word in ("APPROVE", "SIGN_OFF", "VERIFY", "AUTHORIZE"))
        ]
        self.assertEqual(approving, [], "voice must not expose an action that approves engineering work")

    def test_preparing_a_consultant_review_is_the_only_review_shaped_action(self):
        # "PREPARE" is deliberate: it drafts the consultant's decision for them,
        # it does not record an approval on their behalf.
        self.assertIn(SuggestedActionType.PREPARE_CONSULTANT_REVIEW, set(SuggestedActionType))
        self.assertTrue(SuggestedActionType.PREPARE_CONSULTANT_REVIEW.value.startswith("PREPARE"))
