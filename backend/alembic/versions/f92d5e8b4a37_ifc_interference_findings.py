"""Coordination findings carry confidence and location

Adds `confidence`, `storey` and `space` to `ifc_coordination_findings`.

Until now every coordination finding was a deterministic metadata-quality
check — a missing material either is or is not missing — so a confidence
column would have held nothing but 1.0. Geometric interference detection
changes that: it infers a candidate from overlapping bounding boxes, which is
evidence rather than proof, and the number expressing how far that evidence
goes has to be stored next to the finding rather than buried in its JSON, so
review queues and notification policy can filter on it.

Existing rows are backfilled to 1.0, which is their real confidence, not a
placeholder.

`storey`/`space` mirror the columns `ifc_change_records` already uses for the
same purpose: telling a person where in the building to go and look.

Revision ID: f92d5e8b4a37
Revises: e91c4d7a3f26
"""
from alembic import op
import sqlalchemy as sa

revision = "f92d5e8b4a37"
down_revision = "e91c4d7a3f26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ifc_coordination_findings",
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
    )
    op.add_column("ifc_coordination_findings", sa.Column("storey", sa.String(length=250), nullable=True))
    op.add_column("ifc_coordination_findings", sa.Column("space", sa.String(length=250), nullable=True))
    # Reviewers work worst-and-most-certain first, per model revision.
    op.create_index(
        "ix_ifc_finding_version_severity_confidence",
        "ifc_coordination_findings",
        ["version_id", "severity", "confidence"],
    )


def downgrade() -> None:
    op.drop_index("ix_ifc_finding_version_severity_confidence", table_name="ifc_coordination_findings")
    op.drop_column("ifc_coordination_findings", "space")
    op.drop_column("ifc_coordination_findings", "storey")
    op.drop_column("ifc_coordination_findings", "confidence")
