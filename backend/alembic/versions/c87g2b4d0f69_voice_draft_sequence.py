"""Give voice action drafts a deterministic order.

`VoiceAnalysis.action_drafts` was ordered by `created_at`, and every draft of
one analysis is inserted in a single flush — so they all share a timestamp to
the microsecond and the order was a tie. Postgres is free to return tied rows
in any order, and a row rewritten by an UPDATE can move, so the list could
reorder itself *between two requests in the same confirmation flow*.

That is not theoretical: it is the cause of a real failure in which a
`SUBMIT_TASK_FOR_REVIEW` payload was written onto the `UPDATE_TASK_PROGRESS`
draft, the progress action was rejected for carrying fields belonging to the
other action, the review action was never selected, and the consultant was
never notified. Every multi-action analysis in the database had tied
timestamps.

`sequence` is the action's position in the model's own `suggestedActions`
list, so the drafts, the suggestions and the execution results all share one
ordering.

Revision ID: c87g2b4d0f69
Revises: b76f1a3c9e58
"""

import sqlalchemy as sa
from alembic import op

revision = "c87g2b4d0f69"
down_revision = "b76f1a3c9e58"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "voice_action_drafts",
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill from `client_action_id`, which has always encoded the position
    # as `a{n}-{hex}`. Existing rows therefore get their true original order
    # rather than an arbitrary one. Anything unparseable falls back to 0.
    op.execute(
        """
        UPDATE voice_action_drafts
        SET sequence = COALESCE(
            NULLIF(substring(client_action_id from '^a([0-9]+)-'), '')::int - 1,
            0
        )
        """
    )
    op.create_index(
        "ix_voice_action_drafts_analysis_sequence",
        "voice_action_drafts",
        ["voice_analysis_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_voice_action_drafts_analysis_sequence",
        table_name="voice_action_drafts",
    )
    op.drop_column("voice_action_drafts", "sequence")
