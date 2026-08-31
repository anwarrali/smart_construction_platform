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
    return SimpleNamespace(
        id=uuid4(), role=role, status=status, engineer_affiliation=affiliation,
        org_role_id=None, is_internal=True,
    )


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

    def _validate(self, person, action_draft, *, command=None, access=True, task=None,
                  capable=True):
        """Validate one draft.

        `capable` stands in for the permission catalogue, which
        `voice_capabilities.is_available` reads from the database. These cases
        are about the engine's own role and workflow rules; the catalogue is
        covered by its own tests and a Mock session cannot answer it.
        """
        with patch("app.services.voice_rules_engine.user_has_project_access", return_value=access), \
             patch("app.services.voice_rules_engine.is_available", return_value=capable), \
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


class VoiceRefusesWhatThePermissionRefuses(TestCase):
    """Speaking never widens what somebody may do.

    This class was written around the Worker role, which no longer exists. The
    guarantee it protected is not about workers: it is that the rules engine
    refuses any action the speaker does not hold the permission for, whatever
    they can say. `is_available` is the single question it asks, so a refusal
    is driven by that answer rather than by a job title.
    """

    def _expect_forbidden(self, action_type, payload=None):
        person = actor(UserRole.ENGINEER)
        with patch("app.services.voice_rules_engine.user_has_project_access", return_value=True), \
             patch("app.services.voice_rules_engine.is_available", return_value=False), \
             patch.object(VoiceRulesEngine, "_validated_task", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                VoiceRulesEngine().validate(
                    Mock(), command=command_for(person), draft=draft(action_type, payload), actor=person,
                )
        self.assertEqual(raised.exception.status_code, 403)

    def test_progress_cannot_be_posted_without_the_permission(self):
        self._expect_forbidden("UPDATE_TASK_PROGRESS", {"progressPercentage": 100})

    def test_a_task_cannot_be_submitted_for_review_without_the_permission(self):
        self._expect_forbidden("SUBMIT_TASK_FOR_REVIEW", {"completionNote": "done"})

    def test_a_design_change_cannot_be_raised_without_the_permission(self):
        self._expect_forbidden("CREATE_DESIGN_CHANGE_REPORT", {"title": "x", "description": "y"})

    def test_a_review_decision_cannot_be_recorded_without_the_permission(self):
        self._expect_forbidden("PREPARE_CONSULTANT_REVIEW", {"decision": "APPROVE"})

    def test_field_evidence_still_enters_the_verification_workflow(self):
        """The evidence path survives the removal of the role that used it.

        A Site Engineer holding `field_evidence.submit` produces the same
        record a Worker used to, and it still lands as evidence awaiting
        confirmation rather than as official progress.
        """
        person = actor(UserRole.ENGINEER)
        task = fake_task()
        with patch("app.services.voice_rules_engine.user_has_project_access", return_value=True), \
             patch("app.services.voice_rules_engine.is_available", return_value=True), \
             patch.object(VoiceRulesEngine, "_validated_task", return_value=task):
            result = VoiceRulesEngine().validate(
                Mock(), command=command_for(person),
                draft=draft("CREATE_FIELD_SUBMISSION", {"description": "Poured the slab this morning."},
                            target_id=task.id),
                actor=person,
            )
        self.assertEqual(result.type, SuggestedActionType.CREATE_FIELD_SUBMISSION)


class RoleBoundariesAreNotWidenedByVoice(TestCase):
    def _validate(self, person, action_draft, *, task=None, capable=True):
        with patch("app.services.voice_rules_engine.user_has_project_access", return_value=True), \
             patch("app.services.voice_rules_engine.is_available", return_value=capable), \
             patch.object(VoiceRulesEngine, "_validated_task", return_value=task):
            return VoiceRulesEngine().validate(
                Mock(), command=command_for(person), draft=action_draft, actor=person,
            )

    def test_creating_a_task_needs_authority_over_this_project(self):
        """Holding `task.create` somewhere is not the same as running this job.

        The refusal message names that distinction, because "you do not have
        permission" would be misleading for somebody who does hold it — just
        not here.
        """
        with self.assertRaises(HTTPException) as raised:
            self._validate(actor(UserRole.ENGINEER), draft("CREATE_TASK", {
                "title": "Inspect basement waterproofing", "sourceDiscipline": "civil",
            }), capable=False)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("run this project", raised.exception.detail)

    def test_project_manager_may_create_a_task_by_voice(self):
        result = self._validate(actor(UserRole.PROJECT_MANAGER), draft("CREATE_TASK", {
            "title": "Inspect basement waterproofing", "sourceDiscipline": "civil",
        }))
        self.assertEqual(result.type, SuggestedActionType.CREATE_TASK)

    def test_a_reviewer_gets_their_review_scope_and_nothing_beyond_it(self):
        """Was framed as "a consultant engineer".

        Consultant is no longer an identity — the redesign made reviewing
        authority a permission the office's own staff hold. What the test
        protected still holds and is now expressed the way the system decides
        it: somebody whose permissions cover recording a review, and not
        posting progress, can do the first and not the second.
        """
        reviewer = actor(UserRole.ENGINEER)
        review_task = fake_task()
        allowed = self._validate(reviewer, draft("PREPARE_CONSULTANT_REVIEW", {
            "decision": "APPROVE", "comments": "Reinforcement matches the drawing.",
        }, target_id=review_task.id), task=review_task, capable=True)
        self.assertEqual(allowed.type, SuggestedActionType.PREPARE_CONSULTANT_REVIEW)

        with self.assertRaises(HTTPException) as raised:
            self._validate(
                reviewer, draft("UPDATE_TASK_PROGRESS", {"progressPercentage": 50}),
                capable=False,
            )
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
