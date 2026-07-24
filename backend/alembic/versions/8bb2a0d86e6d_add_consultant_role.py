"""add consultant role

Revision ID: 8bb2a0d86e6d
Revises: 21c42705f208
Create Date: 2026-07-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "8bb2a0d86e6d"
down_revision: Union[str, None] = "21c42705f208"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'CONSULTANT'")


def downgrade() -> None:
    pass
