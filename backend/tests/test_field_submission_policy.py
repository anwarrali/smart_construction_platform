import unittest

from app.services.consultant_approval_policy import (
    CENTRALIZED_REVIEW,
    ReviewerAssignment,
    assignment_allows_review,
    dependency_approval_is_satisfied,
)
from app.services.field_submission_policy import (
    AUDIT_ACTIONS,
    REJECTED,
    SUBMITTED,
    VERIFIED,
    can_review_submission,
    engineer_assignment_allows_review,
    notification_recipients,
    valid_rejection_reason,
    validate_photo_directions,
    verification_preserves_official_task,
    worker_assignment_allows_submission,
)


class FieldSubmissionPolicyTests(unittest.TestCase):
    def worker_allowed(self, **changes):
        values = dict(
            role="worker", active=True, member_role="worker", member_active=True,
            member_project_id="project-a", task_project_id="project-a",
            assigned_to_task=True,
        )
        values.update(changes)
        return worker_assignment_allows_submission(**values)

    def engineer_allowed(self, **changes):
        values = dict(
            role="engineer", affiliation="main_contractor", active=True,
            member_role="engineer", member_active=True,
            member_project_id="project-a", submission_project_id="project-a",
            assigned_to_task=True, reviewer_id="engineer-a", worker_id="worker-a",
        )
        values.update(changes)
        return engineer_assignment_allows_review(**values)

    def test_01_worker_can_submit_for_accessible_assigned_task(self):
        self.assertTrue(self.worker_allowed())

    def test_02_worker_cannot_submit_to_another_project(self):
        self.assertFalse(self.worker_allowed(task_project_id="project-b"))

    def test_03_worker_evidence_cannot_modify_official_progress(self):
        self.assertEqual(
            verification_preserves_official_task("in_progress", 45, None),
            ("in_progress", 45, None),
        )

    def test_04_submission_supports_multiple_photos(self):
        self.assertEqual(
            validate_photo_directions([None, "FRONT", "DETAIL"], 3),
            [None, "FRONT", "DETAIL"],
        )

    def test_05_optional_photo_direction_is_preserved(self):
        self.assertEqual(validate_photo_directions(["LEFT"], 1)[0], "LEFT")
        self.assertEqual(validate_photo_directions([None], 1)[0], None)

    def test_06_authorized_engineer_can_verify(self):
        self.assertTrue(self.engineer_allowed())
        self.assertTrue(can_review_submission(SUBMITTED))

    def test_07_engineer_rejection_requires_reason(self):
        self.assertTrue(valid_rejection_reason("Incorrect angle"))
        self.assertFalse(valid_rejection_reason(" "))

    def test_08_rejection_reason_remains_worker_visible_domain_data(self):
        reason = "Show the rear connection"
        self.assertEqual(reason, reason.strip())
        self.assertTrue(valid_rejection_reason(reason))

    def test_09_unauthorized_engineer_cannot_verify(self):
        self.assertFalse(self.engineer_allowed(assigned_to_task=False))

    def test_10_worker_cannot_verify_own_submission(self):
        self.assertFalse(self.engineer_allowed(reviewer_id="worker-a"))

    def test_11_consultant_cannot_modify_worker_evidence(self):
        self.assertFalse(self.engineer_allowed(
            affiliation="external_consultant", member_role="consultant"
        ))

    def test_12_verification_does_not_approve_official_task(self):
        self.assertEqual(
            verification_preserves_official_task("under_review", 100, "pending"),
            ("under_review", 100, "pending"),
        )

    def test_13_existing_consultant_approval_policy_is_unchanged(self):
        self.assertTrue(assignment_allows_review(
            CENTRALIZED_REVIEW,
            [ReviewerAssignment("project-a", "consultant-a", None)],
            project_id="project-a", user_id="consultant-a",
            task_discipline="electrical",
        ))

    def test_14_existing_dependency_blocking_rule_is_unchanged(self):
        self.assertFalse(dependency_approval_is_satisfied("under_review", True, "pending"))
        self.assertTrue(dependency_approval_is_satisfied("done", True, "approved"))

    def test_15_notifications_target_engineers_then_worker(self):
        self.assertEqual(
            notification_recipients(SUBMITTED, {"engineer-a"}, "worker-a"),
            {"engineer-a"},
        )
        self.assertEqual(
            notification_recipients(REJECTED, {"engineer-a"}, "worker-a"),
            {"worker-a"},
        )

    def test_16_audit_events_cover_submission_verification_and_rejection(self):
        self.assertEqual(set(AUDIT_ACTIONS), {SUBMITTED, VERIFIED, REJECTED})
        self.assertEqual(AUDIT_ACTIONS[VERIFIED], "worker_evidence_verified")


if __name__ == "__main__":
    unittest.main()
