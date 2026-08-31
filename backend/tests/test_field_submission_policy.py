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
    evidence_review_allowed,
    evidence_submission_allowed,
    can_review_submission,
    initial_status,
    notification_recipients,
    valid_rejection_reason,
    validate_photo_directions,
    verification_preserves_official_task,
)


class FieldSubmissionPolicyTests(unittest.TestCase):
    # The submitter is now whoever holds `field_evidence.submit` — normally a
    # Site Engineer — and the reviewer whoever holds `field_evidence.verify`.
    # The rules did not change shape; they stopped naming job titles, so the
    # caller passes the resolved permission in.
    def submitter_allowed(self, **changes):
        values = dict(
            holds_permission=True, active=True, member_active=True,
            member_project_id="project-a", task_project_id="project-a",
            assigned_to_task=True,
        )
        values.update(changes)
        return evidence_submission_allowed(**values)

    def reviewer_allowed(self, **changes):
        values = dict(
            holds_permission=True, active=True, member_active=True,
            member_project_id="project-a", submission_project_id="project-a",
            assigned_to_task=True, reviewer_id="engineer-a",
            submitted_by_id="site-engineer-a",
        )
        values.update(changes)
        return evidence_review_allowed(**values)

    def test_01_worker_can_submit_for_accessible_assigned_task(self):
        self.assertTrue(self.submitter_allowed())

    def test_02_worker_cannot_submit_to_another_project(self):
        self.assertFalse(self.submitter_allowed(task_project_id="project-b"))

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
        self.assertTrue(self.reviewer_allowed())
        self.assertTrue(can_review_submission(SUBMITTED))

    def test_07_engineer_rejection_requires_reason(self):
        self.assertTrue(valid_rejection_reason("Incorrect angle"))
        self.assertFalse(valid_rejection_reason(" "))

    def test_08_rejection_reason_remains_worker_visible_domain_data(self):
        reason = "Show the rear connection"
        self.assertEqual(reason, reason.strip())
        self.assertTrue(valid_rejection_reason(reason))

    def test_09_unauthorized_engineer_cannot_verify(self):
        self.assertFalse(self.reviewer_allowed(assigned_to_task=False))

    def test_10_worker_cannot_verify_own_submission(self):
        self.assertFalse(self.reviewer_allowed(reviewer_id="site-engineer-a"))

    def test_11_someone_without_the_verify_permission_cannot_review(self):
        # Was "a consultant cannot modify worker evidence", asserted by passing
        # an affiliation string. The rule it was reaching for is that reviewing
        # evidence takes `field_evidence.verify`, whoever you are.
        self.assertFalse(self.reviewer_allowed(holds_permission=False))

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
        self.assertEqual(AUDIT_ACTIONS[VERIFIED], "field_evidence_verified")


if __name__ == "__main__":
    unittest.main()
