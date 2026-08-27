"""Agent run records

Phase 6 produced findings but kept the run in memory. Afterwards there was no
way to answer the questions that matter when a finding is disputed: which agent
produced it, what made it run, what it looked at, and whether other agents in
the same pass succeeded.

A run is also the only record of an agent that ran and found nothing — a real
and useful outcome that leaves no `AIInsight` behind, and which is otherwise
indistinguishable from an agent that never ran at all.

`trigger_event_id` points at `domain_events` so that when Phase 8 starts
agents from events, the causal chain from event to finding is already
recorded rather than needing to be reconstructed.

Revision ID: b14f7a2c9e63
Revises: a03e6f9c5b48
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b14f7a2c9e63"
down_revision = "a03e6f9c5b48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.String(length=80), nullable=False),
        sa.Column("trigger_type", sa.String(length=30), nullable=False, server_default="MANUAL"),
        sa.Column("trigger_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="SUCCEEDED"),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("tool_calls_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("finding_codes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("insight_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("finding_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("highest_confidence", sa.Float(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        # SET NULL rather than CASCADE: losing the event must not erase the
        # record that an agent ran because of it.
        sa.ForeignKeyConstraint(["trigger_event_id"], ["domain_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"])
    op.create_index("ix_agent_runs_trigger_type", "agent_runs", ["trigger_type"])
    op.create_index("ix_agent_runs_actor_user_id", "agent_runs", ["actor_user_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_run_project_agent_created", "agent_runs",
                    ["project_id", "agent_name", "created_at"])
    op.create_index("ix_agent_run_status_created", "agent_runs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("agent_runs")
