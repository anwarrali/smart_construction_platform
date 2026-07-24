"""preserve legacy revision without duplicating enterprise tables

Revision ID: 21c42705f208
Revises: f4a8c2d91e03
"""
from typing import Sequence, Union

revision: str = "21c42705f208"
down_revision: Union[str, None] = "f4a8c2d91e03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # The original generated migration duplicated f4a8c2d91e03. It is a no-op
    # so both existing revision histories and clean installations remain valid.
    pass

def downgrade() -> None:
    pass
