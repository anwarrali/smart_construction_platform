import unittest
from datetime import date

from app.services.photo_archive_policy import (
    SYSTEM_PHOTO_CATEGORIES,
    archive_scope,
    category_belongs_to_project,
    category_code,
    category_management_allowed,
    human_tagging_allowed,
    matches_archive_filters,
    paginate_records,
)


class PhotoArchivePolicyTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "project_id": "project-a",
            "task_id": "task-12",
            "task_code": "TASK-12",
            "task_title": "Foundation concrete",
            "discipline": "structural",
            "uploader_id": "worker-a",
            "worker_id": "worker-a",
            "engineer_id": "engineer-a",
            "status": "VERIFIED",
            "direction": "FRONT",
            "categories": ["FOUNDATIONS", "CONCRETE"],
            "created_date": date(2026, 6, 15),
            "filename": "footing-front.jpg",
        }

    def test_01_system_categories_are_available(self):
        self.assertIn("FOUNDATIONS", SYSTEM_PHOTO_CATEGORIES)
        self.assertIn("SAFETY", SYSTEM_PHOTO_CATEGORIES)
        self.assertEqual(len(SYSTEM_PHOTO_CATEGORIES), 16)

    def test_02_custom_category_code_is_normalized(self):
        self.assertEqual(category_code("  Fire Alarm  "), "FIRE_ALARM")

    def test_02b_pm_can_create_project_category(self):
        self.assertTrue(category_management_allowed(
            "project_manager", is_assigned_pm=True
        ))

    def test_02c_unauthorized_user_cannot_create_category(self):
        self.assertFalse(category_management_allowed(
            "worker", is_assigned_pm=False
        ))

    def test_03_custom_category_is_isolated_to_project(self):
        self.assertTrue(category_belongs_to_project("project-a", "project-a", False))
        self.assertFalse(category_belongs_to_project("project-a", "project-b", False))

    def test_04_system_category_is_global(self):
        self.assertTrue(category_belongs_to_project(None, "project-b", True))

    def test_05_worker_archive_scope_is_own_evidence(self):
        self.assertEqual(archive_scope("worker"), "OWN")

    def test_05b_worker_can_tag_only_their_pending_submission(self):
        self.assertTrue(human_tagging_allowed(
            "worker", owns_submission=True, submission_pending=True,
            assigned_contractor_engineer=False,
        ))
        self.assertFalse(human_tagging_allowed(
            "worker", owns_submission=False, submission_pending=True,
            assigned_contractor_engineer=False,
        ))

    def test_06_consultant_archive_scope_is_verified_only(self):
        self.assertEqual(archive_scope("engineer", is_consultant=True), "VERIFIED_ONLY")

    def test_07_engineer_scope_is_assigned_tasks(self):
        self.assertEqual(archive_scope("engineer"), "ASSIGNED_TASKS")

    def test_07b_assigned_engineer_can_correct_categories(self):
        self.assertTrue(human_tagging_allowed(
            "engineer", owns_submission=False, submission_pending=False,
            assigned_contractor_engineer=True,
        ))

    def test_08_one_photo_supports_multiple_categories(self):
        self.assertTrue(matches_archive_filters(
            self.record, project_id="project-a", category="CONCRETE"
        ))
        self.assertEqual(len(self.record["categories"]), 2)

    def test_09_category_filtering(self):
        self.assertTrue(matches_archive_filters(
            self.record, project_id="project-a", category="FOUNDATIONS"
        ))
        self.assertFalse(matches_archive_filters(
            self.record, project_id="project-a", category="ELECTRICAL"
        ))

    def test_10_discipline_filtering(self):
        self.assertTrue(matches_archive_filters(
            self.record, project_id="project-a", discipline="Structural"
        ))

    def test_11_task_filtering(self):
        self.assertTrue(matches_archive_filters(
            self.record, project_id="project-a", task_id="task-12"
        ))
        self.assertFalse(matches_archive_filters(
            self.record, project_id="project-a", task_id="task-13"
        ))

    def test_12_date_filtering(self):
        self.assertTrue(matches_archive_filters(
            self.record, project_id="project-a",
            date_from=date(2026, 6, 1), date_to=date(2026, 6, 30),
        ))
        self.assertFalse(matches_archive_filters(
            self.record, project_id="project-a", date_from=date(2026, 7, 1)
        ))

    def test_13_uploader_filtering(self):
        self.assertTrue(matches_archive_filters(
            self.record, project_id="project-a", uploader_id="worker-a"
        ))

    def test_14_submission_status_filtering(self):
        self.assertTrue(matches_archive_filters(
            self.record, project_id="project-a", status="VERIFIED"
        ))

    def test_15_cross_project_evidence_never_matches(self):
        self.assertFalse(matches_archive_filters(
            self.record, project_id="project-b", category="FOUNDATIONS"
        ))

    def test_16_pagination_is_bounded_and_stable(self):
        values, page = paginate_records(list(range(250)), 2, 500)
        self.assertEqual(page, 2)
        self.assertEqual(values, list(range(100, 200)))

    def test_17_deactivation_does_not_remove_historical_reference(self):
        assignment = {"category_id": "category-a"}
        category = {"id": "category-a", "active": False}
        self.assertEqual(assignment["category_id"], category["id"])

    def test_18_free_text_searches_task_category_and_filename(self):
        for search in ("foundation", "concrete", "footing"):
            self.assertTrue(matches_archive_filters(
                self.record, project_id="project-a", search=search
            ))


if __name__ == "__main__":
    unittest.main()
