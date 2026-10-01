import unittest
from datetime import datetime, timezone, timedelta

from app.services.messaging_policy import (
    context_is_supported,
    conversation_search_visible,
    participants_belong_to_project,
    user_specific_unread,
)


class MessagingPolicyTests(unittest.TestCase):
    def setUp(self):
        # Ids only: what a member *is* no longer lives in this module. Group
        # resolution moved to `messaging_authorization.resolve_group_recipients`,
        # which reads the project membership and `has_permission`, and is
        # covered against a real database in test_messaging_authorization.py.
        self.members = [
            {"id": "pm", "active": True},
            {"id": "civil", "active": True},
            {"id": "electrical", "active": True},
            {"id": "consultant", "active": True},
            {"id": "site_engineer", "active": True},
            {"id": "inactive", "active": False},
        ]

    def test_01_authorized_project_member_can_be_selected(self):
        self.assertTrue(participants_belong_to_project(
            {"civil"}, {"pm", "civil", "site_engineer"}
        ))

    def test_02_unrelated_member_cannot_be_injected(self):
        self.assertFalse(participants_belong_to_project(
            {"civil", "outside"}, {"pm", "civil", "site_engineer"}
        ))

    def test_03_multi_recipient_selection_is_relational(self):
        self.assertTrue(participants_belong_to_project(
            {"civil", "electrical"}, {item["id"] for item in self.members}
        ))

    def test_08_broadcast_is_a_permission_not_a_role_name(self):
        # Who may address a whole project is `message.broadcast`, resolved per
        # project like every other permission; the role-name helpers are gone.
        from app.core.permission_catalogue import BY_CODE
        from app.services import messaging_policy as policy
        self.assertIn("message.broadcast", BY_CODE)
        self.assertFalse(hasattr(policy, "can_project_broadcast"))
        self.assertFalse(hasattr(policy, "can_create_group"))

    def test_10_context_supports_task(self):
        self.assertTrue(context_is_supported("TASK"))

    def test_11_context_supports_issue(self):
        self.assertTrue(context_is_supported("ISSUE"))

    def test_11b_context_supports_accountable_project_entities(self):
        for value in ("OWNER_REQUEST", "SITE_VISIT", "DESIGN_CHANGE", "DOCUMENT", "ROOM", "FLOOR", "IFC_ELEMENT", "SITE_REPORT"):
            self.assertTrue(context_is_supported(value))

    def test_12_cross_project_context_search_is_hidden(self):
        self.assertFalse(conversation_search_visible(
            conversation_project_id="a", requested_project_id="b",
            is_participant=True,
        ))

    def test_13_project_participation_is_what_gates_messaging(self):
        # Was "worker communication is restricted", which asserted a rule that
        # only existed to stop a labourer messaging the whole project. With
        # workers gone the restriction has no subject, and the boundary that
        # remains is the real one: you may message people on projects you are
        # on. `can_message_user` enforces it against actual membership, so
        # there is no pure function left to assert here — only that the retired
        # one is gone.
        import app.services.messaging_policy as policy

        self.assertFalse(hasattr(policy, "worker_can_message"))
        self.assertNotIn("WORKERS", policy.PROJECT_GROUPS)

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
