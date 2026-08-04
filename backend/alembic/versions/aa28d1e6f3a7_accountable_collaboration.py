"""accountable collaboration owner requests and site visits

Revision ID: aa28d1e6f3a7
Revises: z27c0a5e2d46
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "aa28d1e6f3a7"
down_revision = "z27c0a5e2d46"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("owner_requests",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_to_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(250), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False), sa.Column("discipline", sa.String(50), nullable=True),
        sa.Column("floor", sa.String(120), nullable=True), sa.Column("room", sa.String(120), nullable=True),
        sa.Column("related_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.String(20), server_default="NORMAL", nullable=False),
        sa.Column("status", sa.String(40), server_default="SUBMITTED", nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True), sa.Column("clarification_text", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_design_change_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["converted_design_change_id"], ["design_changes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("converted_design_change_id"),
    )
    op.create_index("ix_owner_requests_project_status_priority", "owner_requests", ["project_id", "status", "priority"])
    op.create_index("ix_owner_requests_assignee_status", "owner_requests", ["assigned_to_id", "status"])
    op.create_index("ix_owner_requests_category", "owner_requests", ["category"])
    op.create_index("ix_owner_requests_discipline", "owner_requests", ["discipline"])
    op.create_index("ix_owner_requests_due_at", "owner_requests", ["due_at"])
    op.add_column("design_changes", sa.Column("owner_request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_design_changes_owner_request", "design_changes", "owner_requests", ["owner_request_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint("uq_design_changes_owner_request", "design_changes", ["owner_request_id"])

    op.add_column("messages", sa.Column("priority", sa.String(20), server_default="NORMAL", nullable=False))
    op.add_column("messages", sa.Column("requires_acknowledgement", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("messages", sa.Column("requires_response", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("messages", sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("messages", sa.Column("responded_to_message_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_messages_responded_to", "messages", "messages", ["responded_to_message_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_messages_priority", "messages", ["priority"])
    op.create_index("ix_messages_response_due_at", "messages", ["response_due_at"])
    op.create_table("message_recipient_states",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_status", sa.String(30), server_default="UNREAD", nullable=False),
        sa.Column("reminder_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("message_id", "user_id", name="uq_message_recipient_state"),
    )
    op.create_index("ix_message_recipient_action", "message_recipient_states", ["user_id", "response_status"])

    op.create_table("reminder_rules",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("target_type", sa.String(40), server_default="IMPORTANT_COMMUNICATION", nullable=False),
        sa.Column("priority", sa.String(20), nullable=False), sa.Column("first_reminder_minutes", sa.Integer(), nullable=False),
        sa.Column("repeat_interval_minutes", sa.Integer(), nullable=False), sa.Column("maximum_reminders", sa.Integer(), server_default="3", nullable=False),
        sa.Column("escalation_recipient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True), sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["escalation_recipient_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("project_id", "target_type", "priority", name="uq_reminder_rule_scope"),
    )
    op.create_table("reminder_events",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(40), nullable=False), sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False), sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["reminder_rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reminder_events_target_created", "reminder_events", ["target_type", "target_id", "created_at"])

    op.create_table("site_visits",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("engineer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("title", sa.String(250), nullable=False),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False), sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visit_type", sa.String(50), nullable=False), sa.Column("location", sa.String(250), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True), sa.Column("status", sa.String(30), server_default="SCHEDULED", nullable=False),
        sa.Column("reschedule_reason", sa.Text(), nullable=True), sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True), sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("scheduled_end > scheduled_start", name="ck_site_visit_time_order"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["engineer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_visits_engineer_start", "site_visits", ["engineer_id", "scheduled_start"])
    op.create_index("ix_site_visits_project_start", "site_visits", ["project_id", "scheduled_start"])
    op.create_table("site_visit_participants",
        sa.Column("site_visit_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_status", sa.String(20), server_default="INVITED", nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True), sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["site_visit_id"], ["site_visits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_visit_id", "user_id", name="uq_site_visit_participant"),
    )
    op.add_column("site_reports", sa.Column("site_visit_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_site_reports_site_visit", "site_reports", "site_visits", ["site_visit_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint("uq_site_reports_site_visit", "site_reports", ["site_visit_id"])
    op.create_index("ix_site_reports_site_visit_id", "site_reports", ["site_visit_id"])

    op.create_table("ai_insight_sources",
        sa.Column("insight_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False), sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_label", sa.String(250), nullable=True), sa.Column("source_state", sa.String(30), server_default="RAW", nullable=False),
        sa.Column("source_version", sa.String(120), nullable=True), sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("is_valid", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True), sa.Column("invalidation_reason", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["insight_id"], ["ai_insights.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("insight_id", "source_type", "source_id", name="uq_ai_insight_source"),
    )
    op.create_index("ix_ai_insight_source_entity", "ai_insight_sources", ["source_type", "source_id"])

    op.add_column("notifications", sa.Column("category", sa.String(40), server_default="SYSTEM", nullable=False))
    op.add_column("notifications", sa.Column("requires_action", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("notifications", sa.Column("action_url", sa.String(500), nullable=True))
    op.create_index("ix_notifications_category", "notifications", ["category"])
    op.create_index("ix_notifications_requires_action", "notifications", ["requires_action"])


def downgrade() -> None:
    op.drop_index("ix_notifications_requires_action", table_name="notifications"); op.drop_index("ix_notifications_category", table_name="notifications")
    op.drop_column("notifications", "action_url"); op.drop_column("notifications", "requires_action"); op.drop_column("notifications", "category")
    op.drop_table("ai_insight_sources")
    op.drop_index("ix_site_reports_site_visit_id", table_name="site_reports"); op.drop_constraint("uq_site_reports_site_visit", "site_reports", type_="unique")
    op.drop_constraint("fk_site_reports_site_visit", "site_reports", type_="foreignkey"); op.drop_column("site_reports", "site_visit_id")
    op.drop_table("site_visit_participants"); op.drop_table("site_visits")
    op.drop_table("reminder_events"); op.drop_table("reminder_rules"); op.drop_table("message_recipient_states")
    op.drop_index("ix_messages_response_due_at", table_name="messages"); op.drop_index("ix_messages_priority", table_name="messages")
    op.drop_constraint("fk_messages_responded_to", "messages", type_="foreignkey")
    for column in ("responded_to_message_id", "response_due_at", "requires_response", "requires_acknowledgement", "priority"):
        op.drop_column("messages", column)
    op.drop_constraint("uq_design_changes_owner_request", "design_changes", type_="unique")
    op.drop_constraint("fk_design_changes_owner_request", "design_changes", type_="foreignkey"); op.drop_column("design_changes", "owner_request_id")
    op.drop_table("owner_requests")
