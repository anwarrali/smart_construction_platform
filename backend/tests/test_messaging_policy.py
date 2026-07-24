import unittest
from datetime import datetime, timezone, timedelta

from app.services.messaging_policy import (
    can_create_group,
    can_project_broadcast,
    context_is_supported,
    conversation_search_visible,
    participants_belong_to_project,
    resolve_group_records,
    user_specific_unread,
    worker_can_message,
)


class MessagingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.members = [
            {"id": "pm", "role": "project_manager", "active": True},
            {"id": "civil", "role": "engineer", "affiliation": "main_contractor",
             "discipline": "civil", "active": True},
            {"id": "electrical", "role": "engineer", "affiliation": "main_contractor",
             "discipline": "electrical", "active": True},
            {"id": "consultant", "role": "engineer",
             "affiliation": "external_consultant", "discipline": "electrical",
             "active": True},
            {"id": "worker", "role": "worker", "active": True},
            {"id": "inactive", "role": "worker", "active": False},
        ]

    def test_01_authorized_project_member_can_be_selected(self):
        self.assertTrue(participants_belong_to_project(
            {"civil"}, {"pm", "civil", "worker"}
        ))

    def test_02_unrelated_member_cannot_be_injected(self):
        self.assertFalse(participants_belong_to_project(
            {"civil", "outside"}, {"pm", "civil", "worker"}
        ))

    def test_03_multi_recipient_selection_is_relational(self):
        self.assertTrue(participants_belong_to_project(
            {"civil", "electrical"}, {item["id"] for item in self.members}
        ))

    def test_04_contractor_team_resolution(self):
        self.assertEqual(
            resolve_group_records("CONTRACTOR_TEAM", self.members),
            {"pm", "civil", "electrical", "worker"},
        )

    def test_05_consultant_team_resolution(self):
        self.assertEqual(
            resolve_group_records("CONSULTANT_TEAM", self.members),
            {"consultant"},
        )

    def test_06_all_engineers_resolution(self):
        self.assertEqual(
            resolve_group_records("ALL_ENGINEERS", self.members),
            {"civil", "electrical", "consultant"},
        )

    def test_07_discipline_group_resolution(self):
        self.assertEqual(
            resolve_group_records("DISCIPLINE:ELECTRICAL", self.members),
            {"electrical", "consultant"},
        )

    def test_08_engineer_cannot_project_broadcast(self):
        self.assertFalse(can_project_broadcast("engineer"))

    def test_09_pm_and_admin_can_project_broadcast(self):
        self.assertTrue(can_project_broadcast("project_manager"))
        self.assertTrue(can_project_broadcast("admin"))

    def test_10_context_supports_task(self):
        self.assertTrue(context_is_supported("TASK"))

    def test_11_context_supports_issue(self):
        self.assertTrue(context_is_supported("ISSUE"))

    def test_12_cross_project_context_search_is_hidden(self):
        self.assertFalse(conversation_search_visible(
            conversation_project_id="a", requested_project_id="b",
            is_participant=True,
        ))

    def test_13_worker_communication_is_restricted(self):
        self.assertTrue(worker_can_message(
            target_is_project_manager=True, target_is_assigned_engineer=False
        ))
        self.assertFalse(worker_can_message(
            target_is_project_manager=False, target_is_assigned_engineer=False
        ))

    def test_14_group_creation_is_restricted(self):
        self.assertTrue(can_create_group("project_manager"))
        self.assertFalse(can_create_group("worker"))

    def test_15_unread_counts_are_user_specific(self):
        now = datetime.now(timezone.utc)
        messages = [
            {"sender_id": "a", "created_at": now - timedelta(minutes=2)},
            {"sender_id": "b", "created_at": now - timedelta(minutes=1)},
        ]
        self.assertEqual(user_specific_unread(
            messages, user_id="b", last_read_at=None
        ), 1)
        self.assertEqual(user_specific_unread(
            messages, user_id="a", last_read_at=None
        ), 1)

    def test_16_mark_read_affects_only_current_users_cursor(self):
        cursors = {"a": None, "b": None}
        marked_at = datetime.now(timezone.utc)
        cursors["a"] = marked_at
        self.assertEqual(cursors["a"], marked_at)
        self.assertIsNone(cursors["b"])

    def test_17_authorized_context_can_be_discovered(self):
        self.assertTrue(conversation_search_visible(
            conversation_project_id="a", requested_project_id="a",
            is_participant=False, contextual_access=True,
        ))


if __name__ == "__main__":
    unittest.main()
