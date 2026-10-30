"""Split working inside every project from seeing every project (QA-06B)

`platform.view_all_projects` used to open every project completely: list it,
staff it, and read and act on its tasks, documents, models and reports. That
made system administration project participation. It now means the registry
only — list every project, manage its details, team and parties — and a new
code, `platform.work_in_all_projects`, carries the work-side bypass.

Nobody's access may shift except the administrator's, so this grants the new
code wherever the old one is held today:

  * every role that holds `platform.view_all_projects` — the seeded General
    Manager and Technical Director, and any role an office created — **except
    the seeded Office Administrator** (`org_admin`, `organization_id IS NULL`),
    which is the change;
  * every per-person override of `platform.view_all_projects`, with the same
    allowed/revoked value and project, except for people whose office role is
    the seeded Office Administrator.

Only rows that do not exist yet are inserted, so re-running is a no-op. No
existing row is changed or deleted. The administrator keeps every permission
it had; the project-scoped ones now apply on the projects they are on.

Revision ID: i6f3a9c4d170
Revises: h5e2f8b3c069
"""

from alembic import op
import sqlalchemy as sa

revision = "i6f3a9c4d170"
down_revision = "h5e2f8b3c069"
branch_labels = None
depends_on = None

OLD = "platform.view_all_projects"
NEW = "platform.work_in_all_projects"


def upgrade() -> None:
    bind = op.get_bind()
    roles = bind.execute(
        sa.text(
            """
            INSERT INTO role_permissions (id, role_id, permission_code, allowed,
                                          created_at, updated_at)
            SELECT gen_random_uuid(), rp.role_id, :new, rp.allowed, now(), now()
              FROM role_permissions rp
              JOIN roles r ON r.id = rp.role_id
             WHERE rp.permission_code = :old
               AND NOT (r.code = 'org_admin' AND r.organization_id IS NULL)
               AND NOT EXISTS (
                   SELECT 1 FROM role_permissions x
                    WHERE x.role_id = rp.role_id AND x.permission_code = :new
               )
            """
        ),
        {"old": OLD, "new": NEW},
    )
    overrides = bind.execute(
        sa.text(
            """
            INSERT INTO user_permission_overrides (id, user_id, permission_code,
                                                   allowed, project_id, reason,
                                                   created_at, updated_at)
            SELECT gen_random_uuid(), o.user_id, :new, o.allowed, o.project_id,
                   'Carried over from "See every project" when it was split (QA-06B)',
                   now(), now()
              FROM user_permission_overrides o
              JOIN users u ON u.id = o.user_id
              LEFT JOIN roles r ON r.id = u.org_role_id
             WHERE o.permission_code = :old
               AND NOT (COALESCE(r.code, '') = 'org_admin' AND r.organization_id IS NULL)
               AND NOT EXISTS (
                   SELECT 1 FROM user_permission_overrides x
                    WHERE x.user_id = o.user_id AND x.permission_code = :new
                      AND x.project_id IS NOT DISTINCT FROM o.project_id
               )
            """
        ),
        {"old": OLD, "new": NEW},
    )
    print(f"[{revision}] granted {NEW} to {roles.rowcount} role(s), "
          f"carried {overrides.rowcount} override(s)")


def downgrade() -> None:
    # The code leaves the catalogue with this revision, so its rows would name
    # a permission that no longer exists.
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = :new"), {"new": NEW})
    bind.execute(sa.text("DELETE FROM user_permission_overrides WHERE permission_code = :new"), {"new": NEW})
