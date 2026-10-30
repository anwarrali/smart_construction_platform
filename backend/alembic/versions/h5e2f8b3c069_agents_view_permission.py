"""Grant the new `agents.view` permission to the Office Administrator role

The project Agents page used to be reachable by anyone who could see tasks,
which put engineers in front of agent controls nobody had decided to give
them. It now requires `agents.view`, a new catalogue code that the
administrator hands out per role or per person.

As with `a92d4e1f70b3` (`project.delete`), adding the code to the catalogue and
to the `org_admin` template is not enough on an existing database: the live
resolver answers from `role_permissions` rows, and the seeder only runs on a
fresh database. Without this migration the administrator — the one person meant
to manage the page — would lose it too.

Only the seeded `org_admin` role receives it (`organization_id IS NULL`), only
where absent, so re-running is a no-op and an office's own roles are untouched.
Every other role starts without it, which is the point of the change.

Revision ID: h5e2f8b3c069
Revises: g4d1e7a2b958
"""

from alembic import op
import sqlalchemy as sa

revision = "h5e2f8b3c069"
down_revision = "g4d1e7a2b958"
branch_labels = None
depends_on = None

CODE = "agents.view"
ROLE_CODES = ("org_admin",)


def upgrade() -> None:
    result = op.get_bind().execute(
        sa.text(
            """
            INSERT INTO role_permissions (id, role_id, permission_code, allowed,
                                          created_at, updated_at)
            SELECT gen_random_uuid(), r.id, :code, true, now(), now()
              FROM roles r
             WHERE r.organization_id IS NULL
               AND r.code = ANY(:role_codes)
               AND NOT EXISTS (
                   SELECT 1 FROM role_permissions rp
                    WHERE rp.role_id = r.id AND rp.permission_code = :code
               )
            """
        ),
        {"code": CODE, "role_codes": list(ROLE_CODES)},
    )
    print(f"[{revision}] granted {CODE} to {result.rowcount} role(s)")


def downgrade() -> None:
    # Removes the code everywhere it was granted, including grants an
    # administrator made later: without the code in the catalogue they would
    # be rows naming a permission that no longer exists.
    op.get_bind().execute(
        sa.text("DELETE FROM role_permissions WHERE permission_code = :code"),
        {"code": CODE},
    )
    op.get_bind().execute(
        sa.text("DELETE FROM user_permission_overrides WHERE permission_code = :code"),
        {"code": CODE},
    )
