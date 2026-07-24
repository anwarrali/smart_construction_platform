import unittest

from app.services.consultant_approval_policy import (
    CENTRALIZED_REVIEW,
    DISCIPLINE_BASED_REVIEW,
    ReviewerAssignment,
    assignment_allows_review,
    dependency_approval_is_satisfied,
    rejected_work_can_be_resubmitted,
)


class ConsultantApprovalPolicyTests(unittest.TestCase):
    project = "project-a"
    other_project = "project-b"
    architect = "architect-consultant"
    electrician = "electrical-consultant"

    def allowed(self, mode, assignments, user, discipline):
        return assignment_allows_review(
            mode,
            assignments,
            project_id=self.project,
            user_id=user,
            task_discipline=discipline,
        )

    def test_centralized_consultant_can_approve_architectural_task(self):
        rows = [ReviewerAssignment(self.project, self.architect, None)]
        self.assertTrue(self.allowed(CENTRALIZED_REVIEW, rows, self.architect, "architectural"))

    def test_centralized_consultant_can_approve_electrical_despite_specialty(self):
        rows = [ReviewerAssignment(self.project, self.architect, None)]
        self.assertTrue(self.allowed(CENTRALIZED_REVIEW, rows, self.architect, "electrical"))

    def test_non_authorized_consultant_cannot_approve(self):
        rows = [ReviewerAssignment(self.project, self.architect, None)]
        self.assertFalse(self.allowed(CENTRALIZED_REVIEW, rows, "not-configured", "civil"))

    def test_consultant_from_another_project_cannot_approve(self):
        rows = [ReviewerAssignment(self.other_project, self.architect, None)]
        self.assertFalse(self.allowed(CENTRALIZED_REVIEW, rows, self.architect, "architectural"))

    def test_discipline_architect_can_approve_architectural_task(self):
        rows = [ReviewerAssignment(self.project, self.architect, "architectural")]
        self.assertTrue(self.allowed(DISCIPLINE_BASED_REVIEW, rows, self.architect, "architectural"))

    def test_discipline_architect_cannot_approve_electrical_task(self):
        rows = [ReviewerAssignment(self.project, self.architect, "architectural")]
        self.assertFalse(self.allowed(DISCIPLINE_BASED_REVIEW, rows, self.architect, "electrical"))

    def test_discipline_electrical_consultant_can_approve_electrical_task(self):
        rows = [ReviewerAssignment(self.project, self.electrician, "electrical")]
        self.assertTrue(self.allowed(DISCIPLINE_BASED_REVIEW, rows, self.electrician, "electrical"))

    def test_rejected_task_can_be_reworked_and_resubmitted(self):
        self.assertTrue(rejected_work_can_be_resubmitted("rework_required", "rejected"))
        self.assertFalse(rejected_work_can_be_resubmitted("under_review", "pending"))

    def test_approval_unblocks_dependency_only_after_required_approval(self):
        self.assertFalse(dependency_approval_is_satisfied("under_review", True, "pending"))
        self.assertTrue(dependency_approval_is_satisfied("done", True, "approved"))

    def test_configuration_change_immediately_changes_authority(self):
        centralized = [ReviewerAssignment(self.project, self.architect, None)]
        discipline = [ReviewerAssignment(self.project, self.electrician, "electrical")]
        self.assertTrue(self.allowed(CENTRALIZED_REVIEW, centralized, self.architect, "electrical"))
        self.assertFalse(self.allowed(DISCIPLINE_BASED_REVIEW, discipline, self.architect, "electrical"))
        self.assertTrue(self.allowed(DISCIPLINE_BASED_REVIEW, discipline, self.electrician, "electrical"))


if __name__ == "__main__":
    unittest.main()
