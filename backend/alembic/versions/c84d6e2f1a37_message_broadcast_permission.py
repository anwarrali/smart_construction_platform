"""Grant `message.broadcast` to the roles that could already broadcast

Starting a project group conversation and sending a project announcement were
gated on `users.role in {"admin", "project_manager"}` — the retired enum — in
`app.services.messaging_policy`. They now require `message.broadcast`, a code
added to the catalogue for them.

## Who receives it, and why it is read from `roles.legacy_role`

Exactly the people who could do it yesterday. The old check read the account's
legacy enum, and an account's legacy enum is what its office role provisions it
with: `roles.legacy_role`. So every role — a seeded template *or* an office's
own copy — whose `legacy_role` is ADMIN or PROJECT_MANAGER is granted the code,
and nobody else is. Reading the column rather than naming template codes is
what carries an office's copied and renamed roles across too.

This must run while `roles.legacy_role` still exists, which is why it precedes
the migration that removes the legacy columns.

No application constant is imported: the code and the legacy values are
written out, so the migration records what was done regardless of which
version of the application happens to run it. Rows are inserted only where
absent; re-running is a no-op. On a fresh database there are no roles yet, so
this does nothing — the templates seeded by `bootstrap_admin` already carry the
code.

Revision ID: c84d6e2f1a37
Revises: b73f5c8a2e91
"""

from alembic import op
import sqlalchemy as sa

revision = "c84d6e2f1a37"
down_revision = "b73f5c8a2e91"
branch_labels = None
depends_on = None

CODE = "message.broadcast"
LEGACY_VALUES = ("ADMIN", "PROJECT_MANAGER")


def upgrade() -> None:
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            """
            INSERT INTO role_permissions (id, role_id, permission_code, allowed,
                                          created_at, updated_at)
            SELECT gen_random_uuid(), r.id, :code, true, now(), now()
              FROM roles r
             WHERE r.legacy_role = ANY(:legacy_values)
               AND NOT EXISTS (
                   SELECT 1 FROM role_permissions rp
                    WHERE rp.role_id = r.id
                      AND rp.permission_code = :code
               )
            """
        ),
        {"code": CODE, "legacy_values": list(LEGACY_VALUES)},
    )
    print(f"[{revision}] granted {CODE} to {result.rowcount} role(s)")


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM role_permissions WHERE permission_code = :code"),
        {"code": CODE},
    )
