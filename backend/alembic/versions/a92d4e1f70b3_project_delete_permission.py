"""Grant the new `project.delete` permission to the roles that already had it

`DELETE /projects/{id}` was gated on `is_admin(user.role)` — the retired enum.
It now requires `project.delete`, a code added to the catalogue for it. Adding a
code to `app/core/permission_catalogue.py` is not enough on its own: the live
resolver (`rbac.resolved_permissions`) answers from `role_permissions` rows in
the database, not from the catalogue defaults, and the catalogue defaults are
only turned into rows by `rbac.seed_roles`.

## Why this is a migration and not "just re-run the seeder"

`seed_roles` is reached exclusively through `python -m app.db.rbac_backfill`,
which is a manually-run script. It is not in the Compose command, not called at
startup, and not invoked by any earlier migration — so on every existing
deployment the catalogue would have gained a code that no role holds, and the
administrator who could delete a project yesterday could not delete one today.
That is a silent authorization regression introduced by a purely additive
change, which is the worst shape such a bug can take.

## Which roles, and why they are named here rather than derived

The two seeded templates whose `legacy_role` is `ADMIN` — `org_admin` and
`office_director`. Those are exactly the roles whose accounts satisfy
`is_admin(user.role)` today, so this grants nothing that was not already
permitted.

`technical_director` is deliberately absent. It inherits the administrator's
catalogue defaults but provisions accounts whose retired role is
PROJECT_MANAGER, so `is_admin` has always answered False for it; it declines the
code in `role_templates.py` and must not receive a row here either.

The codes are written out rather than read from `TEMPLATES` at run time. A
migration is a record of what was done to a database on a given day; one that
imports application constants produces a different result depending on which
version of the code happens to be deployed when it runs.

Rows are inserted only where absent, and only for system roles the platform
seeded (`organization_id IS NULL`), so an office that has since created its own
roles is untouched and re-running is a no-op.

Revision ID: a92d4e1f70b3
Revises: f81c3a5d9e64
"""

from alembic import op
import sqlalchemy as sa

revision = "a92d4e1f70b3"
down_revision = "f81c3a5d9e64"
branch_labels = None
depends_on = None

CODE = "project.delete"
#: Seeded roles whose accounts could already delete a project.
ROLE_CODES = ("org_admin", "office_director")


def upgrade() -> None:
    connection = op.get_bind()
    result = connection.execute(
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
                    WHERE rp.role_id = r.id
                      AND rp.permission_code = :code
               )
            """
        ),
        {"code": CODE, "role_codes": list(ROLE_CODES)},
    )
    # Surfaced so an operator can see it happen, and so a deployment where the
    # roles were never seeded is visibly a no-op rather than silently one.
    print(f"[{revision}] granted {CODE} to {result.rowcount} role(s)")


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM role_permissions rp
             USING roles r
             WHERE rp.role_id = r.id
               AND rp.permission_code = :code
               AND r.organization_id IS NULL
               AND r.code = ANY(:role_codes)
            """
        ),
        {"code": CODE, "role_codes": list(ROLE_CODES)},
    )
