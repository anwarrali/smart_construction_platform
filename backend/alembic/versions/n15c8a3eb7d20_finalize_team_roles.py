"""finalize supported roles and project team assignments

Revision ID: n15c8a3eb7d20
Revises: m14b7f2da9c01
"""
from alembic import op
import sqlalchemy as sa


revision = "n15c8a3eb7d20"
down_revision = "m14b7f2da9c01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_members", sa.Column("project_discipline", sa.String(30), nullable=True))
    op.add_column("project_members", sa.Column("project_notes", sa.Text(), nullable=True))

    # Replace the discipline enum so ARCHITECTURAL is terminology, not a role.
    op.execute("ALTER TABLE engineer_profiles ALTER COLUMN discipline TYPE VARCHAR(30) USING discipline::text")
    op.execute("UPDATE engineer_profiles SET discipline = 'ARCHITECTURAL' WHERE discipline = 'ARCHITECT'")
    op.execute("DROP TYPE engineer_discipline")
    op.execute("CREATE TYPE engineer_discipline AS ENUM ('ARCHITECTURAL','CIVIL','ELECTRICAL','MECHANICAL')")
    op.execute("ALTER TABLE engineer_profiles ALTER COLUMN discipline TYPE engineer_discipline USING discipline::engineer_discipline")

    # Convert both role columns to text while legacy values are mapped.  No
    # users, memberships, tasks, or legacy company-profile rows are deleted.
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(40) USING role::text")
    op.execute("ALTER TABLE project_members ALTER COLUMN role_on_project TYPE VARCHAR(40) USING role_on_project::text")

    op.execute("""
        INSERT INTO engineer_profiles
            (id, user_id, discipline, can_act_as_project_manager, created_at, updated_at)
        SELECT gen_random_uuid(), u.id,
            (CASE u.role
                WHEN 'ARCHITECT' THEN 'ARCHITECTURAL'
                WHEN 'ELECTRICAL_ENGINEER' THEN 'ELECTRICAL'
                WHEN 'MECHANICAL_ENGINEER' THEN 'MECHANICAL'
                ELSE 'CIVIL'
            END)::engineer_discipline,
            false, now(), now()
        FROM users u
        WHERE u.role IN ('ENGINEER','CONSULTANT','ARCHITECT','CIVIL_ENGINEER',
                         'ELECTRICAL_ENGINEER','MECHANICAL_ENGINEER','CONTRACTOR','SUPERVISOR')
          AND NOT EXISTS (SELECT 1 FROM engineer_profiles ep WHERE ep.user_id = u.id)
    """)
    op.execute("""
        UPDATE users u SET organization = COALESCE(NULLIF(u.organization, ''), cp.company_name)
        FROM contractor_profiles cp
        WHERE cp.user_id = u.id AND u.role = 'CONTRACTOR'
    """)
    op.execute("""
        UPDATE users SET
            engineer_affiliation = CASE WHEN role = 'CONSULTANT' THEN 'external_consultant' ELSE 'main_contractor' END,
            role = CASE WHEN role = 'CONSULTANT' THEN 'CONSULTANT' ELSE 'ENGINEER' END
        WHERE role IN ('ENGINEER','CONSULTANT','ARCHITECT','CIVIL_ENGINEER',
                       'ELECTRICAL_ENGINEER','MECHANICAL_ENGINEER','CONTRACTOR','SUPERVISOR')
    """)
    op.execute("UPDATE users SET engineer_affiliation = NULL WHERE role NOT IN ('ENGINEER','CONSULTANT')")

    op.execute("""
        UPDATE project_members pm SET
            assignment_title = COALESCE(pm.assignment_title,
                CASE WHEN pm.role_on_project = 'SUPERVISOR' THEN 'Field Supervisor' ELSE pm.assignment_title END),
            role_on_project = CASE
                WHEN pm.role_on_project = 'SUPERVISOR' AND u.role = 'OWNER' THEN 'OWNER'
                WHEN pm.role_on_project IN ('ARCHITECT','CIVIL_ENGINEER','ELECTRICAL_ENGINEER',
                                             'MECHANICAL_ENGINEER','CONTRACTOR','SUPERVISOR') THEN 'ENGINEER'
                ELSE pm.role_on_project
            END,
            project_discipline = COALESCE(pm.project_discipline, ep.discipline::text)
        FROM users u LEFT JOIN engineer_profiles ep ON ep.user_id = u.id
        WHERE u.id = pm.user_id
    """)

    op.execute("DROP TYPE user_role")
    op.execute("CREATE TYPE user_role AS ENUM ('ADMIN','OWNER','PROJECT_MANAGER','ENGINEER','CONSULTANT')")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE user_role USING role::user_role")
    op.execute("ALTER TABLE project_members ALTER COLUMN role_on_project TYPE user_role USING role_on_project::user_role")


def downgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(40) USING role::text")
    op.execute("ALTER TABLE project_members ALTER COLUMN role_on_project TYPE VARCHAR(40) USING role_on_project::text")
    op.execute("DROP TYPE user_role")
    op.execute("""CREATE TYPE user_role AS ENUM (
        'ADMIN','OWNER','PROJECT_MANAGER','ARCHITECT','CIVIL_ENGINEER','ELECTRICAL_ENGINEER',
        'MECHANICAL_ENGINEER','CONTRACTOR','SUPERVISOR','CONSULTANT','ENGINEER')""")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE user_role USING role::user_role")
    op.execute("ALTER TABLE project_members ALTER COLUMN role_on_project TYPE user_role USING role_on_project::user_role")

    op.execute("ALTER TABLE engineer_profiles ALTER COLUMN discipline TYPE VARCHAR(30) USING discipline::text")
    op.execute("UPDATE engineer_profiles SET discipline = 'ARCHITECT' WHERE discipline = 'ARCHITECTURAL'")
    op.execute("DROP TYPE engineer_discipline")
    op.execute("CREATE TYPE engineer_discipline AS ENUM ('ARCHITECT','CIVIL','ELECTRICAL','MECHANICAL')")
    op.execute("ALTER TABLE engineer_profiles ALTER COLUMN discipline TYPE engineer_discipline USING discipline::engineer_discipline")
    op.drop_column("project_members", "project_notes")
    op.drop_column("project_members", "project_discipline")
