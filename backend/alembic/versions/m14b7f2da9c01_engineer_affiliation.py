"""classify contractor and external consultant engineers

Revision ID: m14b7f2da9c01
Revises: l13a6e1ca8baa
"""
from alembic import op
import sqlalchemy as sa

revision = "m14b7f2da9c01"
down_revision = "l13a6e1ca8baa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("engineer_affiliation", sa.String(40), nullable=True))
    op.execute("UPDATE users SET engineer_affiliation = 'external_consultant' WHERE role = 'CONSULTANT'")
    op.execute("UPDATE users SET engineer_affiliation = 'contractor_staff' WHERE role = 'ENGINEER'")
    op.create_index("ix_users_engineer_affiliation", "users", ["engineer_affiliation"])


def downgrade() -> None:
    op.drop_index("ix_users_engineer_affiliation", table_name="users")
    op.drop_column("users", "engineer_affiliation")
