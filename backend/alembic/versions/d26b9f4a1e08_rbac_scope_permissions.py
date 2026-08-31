"""Rename the discipline-scope permission and seed the new work-scope codes

`document.view_all` was introduced by the RBAC expand step to name one rule:
"your view of this project is not narrowed to your own disciplines". It turned
out to govern site reports and issues as well as documents, so the code is
renamed to `project.view_all_disciplines` — the same rule, honestly named.

Permission codes are stored as strings in `role_permissions` and the two
override tables, so the rename has to reach the rows as well as the catalogue.
Nothing is added or removed here: a role that held the old code holds the new
one, and no role's effective permissions change.

`task.view_all` and `cost_validation.review` are new codes whose defaults
reproduce checks the endpoints were making from role names. Existing roles are
given them where the catalogue default says they should have them, so switching
the endpoints over changes nobody's access.

Revision ID: d26b9f4a1e08
Revises: c15a8d2e7f10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d26b9f4a1e08"
down_revision: Union[str, None] = "c15a8d2e7f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RENAMES = (("document.view_all", "project.view_all_disciplines"),)

#: New code -> the role template codes that should hold it, matching the
#: catalogue defaults. Seeded per role rather than per user, because a role is
#: where a permission lives now.
NEW_CODES = {
    "task.view_all": (
        "org_admin", "office_director", "technical_director", "project_manager",
        "client_representative", "legacy_consultant",
    ),
    "cost_validation.review": (
        "org_admin", "office_director", "technical_director", "project_manager",
        "senior_engineer", "engineer", "site_engineer", "bim_engineer",
        "cad_technician", "surveyor", "document_controller",
        "contractor_representative", "subcontractor_representative",
        "external_reviewer",
    ),
}


def upgrade() -> None:
    connection = op.get_bind()

    for old, new in RENAMES:
        for table in ("role_permissions", "user_permission_overrides", "role_permission_overrides"):
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET permission_code = :new WHERE permission_code = :old"
                ),
                {"old": old, "new": new},
            )

    for code, role_codes in NEW_CODES.items():
        connection.execute(
            sa.text("""
                INSERT INTO role_permissions (id, role_id, permission_code, allowed, created_at, updated_at)
                SELECT gen_random_uuid(), r.id, :code, true, now(), now()
                FROM roles r
                WHERE r.code = ANY(:role_codes)
                  AND NOT EXISTS (
                      SELECT 1 FROM role_permissions rp
                      WHERE rp.role_id = r.id AND rp.permission_code = :code
                  )
            """),
            {"code": code, "role_codes": list(role_codes)},
        )


def downgrade() -> None:
    connection = op.get_bind()

    for code in NEW_CODES:
        connection.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_code = :code"),
            {"code": code},
        )

    for old, new in RENAMES:
        for table in ("role_permissions", "user_permission_overrides", "role_permission_overrides"):
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET permission_code = :old WHERE permission_code = :new"
                ),
                {"old": old, "new": new},
            )
