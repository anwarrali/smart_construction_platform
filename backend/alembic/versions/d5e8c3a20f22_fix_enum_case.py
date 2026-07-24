"""fix enum labels added with incompatible case

Revision ID: d5e8c3a20f22
Revises: c4d7a2b19f11
"""
from alembic import op

revision = "d5e8c3a20f22"
down_revision = "c4d7a2b19f11"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid WHERE t.typname='user_role' AND e.enumlabel='consultant') THEN
            ALTER TYPE user_role RENAME VALUE 'consultant' TO 'CONSULTANT';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid WHERE t.typname='task_status' AND e.enumlabel='rework_required') THEN
            ALTER TYPE task_status RENAME VALUE 'rework_required' TO 'REWORK_REQUIRED';
        END IF;
    END $$;""")

def downgrade() -> None:
    pass
