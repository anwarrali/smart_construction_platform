"""normalize legacy engineer roles

Revision ID: e6f9d4b31a33
Revises: d5e8c3a20f22
"""
from alembic import op

revision = "e6f9d4b31a33"
down_revision = "d5e8c3a20f22"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'ENGINEER'")
    op.execute("""
        INSERT INTO engineer_profiles
            (id, user_id, discipline, can_act_as_project_manager, created_at, updated_at)
        SELECT gen_random_uuid(), u.id,
            CASE u.role::text
                WHEN 'ARCHITECT' THEN 'ARCHITECT'::engineer_discipline
                WHEN 'CIVIL_ENGINEER' THEN 'CIVIL'::engineer_discipline
                WHEN 'ELECTRICAL_ENGINEER' THEN 'ELECTRICAL'::engineer_discipline
                ELSE 'MECHANICAL'::engineer_discipline
            END,
            u.role::text IN ('ARCHITECT', 'CIVIL_ENGINEER'), now(), now()
        FROM users u
        WHERE u.role::text IN ('ARCHITECT','CIVIL_ENGINEER','ELECTRICAL_ENGINEER','MECHANICAL_ENGINEER')
          AND NOT EXISTS (SELECT 1 FROM engineer_profiles ep WHERE ep.user_id = u.id)
    """)
    op.execute("UPDATE users SET role = 'ENGINEER' WHERE role::text IN ('ARCHITECT','CIVIL_ENGINEER','ELECTRICAL_ENGINEER','MECHANICAL_ENGINEER')")
    op.execute("UPDATE project_members SET role_on_project = 'ENGINEER' WHERE role_on_project::text IN ('ARCHITECT','CIVIL_ENGINEER','ELECTRICAL_ENGINEER','MECHANICAL_ENGINEER')")

def downgrade() -> None:
    pass
