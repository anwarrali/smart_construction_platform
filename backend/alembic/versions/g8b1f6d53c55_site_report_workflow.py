"""complete site report workflow

Revision ID: g8b1f6d53c55
Revises: f7a0e5c42b44
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "g8b1f6d53c55"
down_revision = "f7a0e5c42b44"
branch_labels = None
depends_on = None

def upgrade() -> None:
    for name in ("equipment","work_completed","work_in_progress","delays","issues_summary","notes"):
        op.add_column("site_reports", sa.Column(name, sa.Text(), nullable=True))
    op.add_column("site_reports", sa.Column("workers_count", sa.Integer(), nullable=True))
    op.add_column("site_reports", sa.Column("review_status", sa.String(30), nullable=False, server_default="submitted"))
    op.add_column("site_reports", sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("site_reports", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_site_reports_reviewed_by", "site_reports", "users", ["reviewed_by_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_site_reports_review_status", "site_reports", ["review_status"])

def downgrade() -> None:
    op.drop_index("ix_site_reports_review_status", table_name="site_reports")
    op.drop_constraint("fk_site_reports_reviewed_by", "site_reports", type_="foreignkey")
    for name in ("reviewed_at","reviewed_by_id","review_status","workers_count","notes","issues_summary","delays","work_in_progress","work_completed","equipment"):
        op.drop_column("site_reports", name)
