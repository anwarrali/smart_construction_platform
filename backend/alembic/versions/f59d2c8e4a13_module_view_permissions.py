"""Seed the module-view permissions onto the roles that already reach those pages

Five new codes, granted to existing roles so nobody's access changes when the
frontend starts asking for them:

    document.view  site_report.view  issue.view  design_change.view
    client_portal.view

## Why these exist

Until now, "may this person open the Documents part of a project" was answered
by the frontend's per-role URL table — four prefixes, four different role
lists, for the same four page components. None of the list endpoints behind
them has ever gated on role: `list_documents`, `list_site_reports`,
`list_issues` and `list_design_changes` check project access and then scope
rows by party, discipline or assignment. So the route table was making a
navigation decision that looked like an authorization decision, and getting it
inconsistently wrong — an office's own internal engineer holds
`document.upload` but had no documents page anywhere to upload from.

These codes name that decision and hand it to the office. The data each page
shows is unchanged and still scoped per row.

## Why the grants below keep the equivalence gate green

`legacy_effective_permissions` resolves through `permission_catalogue.role_defaults`,
which is the live catalogue — so a new code appears on the *retired* side of the
comparison for every role in its `default_roles`. For the two sides to agree,
each seeded role must be granted the code exactly when the legacy role its
accounts carry is in that default set.

The four module codes default to every role that can be on a project, so every
template except the archived one gets them. `client_portal.view` defaults to
ADMIN and OWNER only, so it goes to the administrator roles and the client
representative — and to nobody else, because a Project Manager holding it on
the new side while the retired side withholds it is exactly the silent widening
this gate exists to catch.

Revision ID: f59d2c8e4a13
Revises: e48c1b6d3f27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f59d2c8e4a13"
down_revision: Union[str, None] = "e48c1b6d3f27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Every seeded role that can hold work on a project. `archived_field_staff` is
#: absent: it holds nothing, on purpose, and granting it a view permission
#: would be the first crack in that.
_ON_A_PROJECT = (
    "org_admin", "office_director", "technical_director", "project_manager",
    "senior_engineer", "engineer", "site_engineer", "bim_engineer",
    "cad_technician", "surveyor", "document_controller", "office_staff",
    "client_representative", "contractor_representative",
    "subcontractor_representative", "external_reviewer", "legacy_consultant",
)

NEW_CODES = {
    "document.view": _ON_A_PROJECT,
    "site_report.view": _ON_A_PROJECT,
    "issue.view": _ON_A_PROJECT,
    "design_change.view": _ON_A_PROJECT,
    # ADMIN + OWNER, matching `get_owner_dashboard`'s retired role check.
    "client_portal.view": ("org_admin", "office_director", "client_representative"),
}


def upgrade() -> None:
    connection = op.get_bind()
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
