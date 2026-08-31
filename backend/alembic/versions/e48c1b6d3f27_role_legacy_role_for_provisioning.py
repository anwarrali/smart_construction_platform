"""Record which legacy enum value a configurable role provisions accounts with

Expand step. One nullable column, `roles.legacy_role`, backfilled from the
seeded templates. Nothing is dropped and no behaviour changes on its own.

## Why this column exists at all

Account creation is moving off the `UserRole` enum and onto the office's own
configured roles: an administrator picks "Senior Structural Engineer", not
"engineer". But `users.role` is still `NOT NULL` and stays that way until the
contract migration, so *something* has to decide which legacy value a new
account is written with.

The alternatives were worse. Deriving it from the role's permissions would make
provisioning depend on whatever an office had configured that morning, and a
role that had been re-permissioned would start creating accounts of a different
legacy kind — a silent, invisible coupling. Defaulting everything to ENGINEER
would break the equivalence gate for any office that had customised its
permissions, because the fallback path resolves an unmigrated account through
the catalogue defaults for exactly this column.

So it is recorded explicitly, once, next to the role it belongs to. A custom
role an office creates inherits the value from the template it was copied from,
or falls back to `engineer` — the least-privileged legacy value that still
carries a working permission set.

**This column is Category B: it exists only for the migration window.** Its one
consumer is `app.services.user_service.create_provisioned_user`, and it is
dropped in the same migration that drops `users.role`.

Revision ID: e48c1b6d3f27
Revises: d26b9f4a1e08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e48c1b6d3f27"
down_revision: Union[str, None] = "d26b9f4a1e08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Role template code -> the legacy `user_role` value an account created under
#: it is written with. A verbatim copy of `PROVISIONING_LEGACY_ROLE` in
#: `app.core.role_templates` — copied rather than imported, because a migration
#: must keep describing the schema of its own moment even after the module it
#: was copied from has moved on. `test_provisioning_legacy_roles_match_the_migration`
#: parses this dict and asserts the two agree, so the copy cannot drift while
#: both still exist.
#:
#: Note these are NOT the roles the templates inherit permissions from.
#: `technical_director` inherits ADMIN but provisions PROJECT_MANAGER, because
#: writing `role=ADMIN` would make the surviving hardcoded admin checks treat
#: it as a full administrator — the one authority that template withholds.
#:
#: `archived_field_staff` deliberately has no entry. No account is ever created
#: under it — it is where retired worker accounts were parked — and leaving it
#: NULL means an attempt to provision one fails loudly rather than quietly
#: minting the role this redesign removed.
TEMPLATE_LEGACY_ROLE = {
    "org_admin": "ADMIN",
    "office_director": "ADMIN",
    "technical_director": "PROJECT_MANAGER",
    "project_manager": "PROJECT_MANAGER",
    "senior_engineer": "ENGINEER",
    "engineer": "ENGINEER",
    "site_engineer": "ENGINEER",
    "bim_engineer": "ENGINEER",
    "cad_technician": "ENGINEER",
    "surveyor": "ENGINEER",
    "document_controller": "ENGINEER",
    "office_staff": "ENGINEER",
    "client_representative": "OWNER",
    "contractor_representative": "ENGINEER",
    "subcontractor_representative": "ENGINEER",
    "external_reviewer": "ENGINEER",
    "legacy_consultant": "CONSULTANT",
}

#: The office side an account gets on `users.engineer_affiliation` when its
#: legacy role is ENGINEER. Every internal template is `internal_engineer`:
#: a consultant-side reviewer is office staff under the confirmed product
#: direction, not an outside party, so no template maps to
#: `external_consultant` any more. The two contractor templates are the only
#: ones that carry an external affiliation, and they are also the ones whose
#: members hold a `ProjectParty` — the affiliation is the pre-backfill echo of
#: that, nothing more.
TEMPLATE_AFFILIATION = {
    "contractor_representative": "main_contractor",
    "subcontractor_representative": "main_contractor",
}


def upgrade() -> None:
    op.add_column("roles", sa.Column("legacy_role", sa.String(length=30), nullable=True))
    op.add_column("roles", sa.Column("legacy_affiliation", sa.String(length=40), nullable=True))

    connection = op.get_bind()
    for code, legacy_role in TEMPLATE_LEGACY_ROLE.items():
        connection.execute(
            sa.text("UPDATE roles SET legacy_role = :legacy WHERE code = :code"),
            {"legacy": legacy_role, "code": code},
        )
    for code, affiliation in TEMPLATE_AFFILIATION.items():
        connection.execute(
            sa.text("UPDATE roles SET legacy_affiliation = :aff WHERE code = :code"),
            {"aff": affiliation, "code": code},
        )
    # An office's own roles, and anything seeded before this migration, land on
    # the engineer default rather than being left undecided — except the
    # archived template, which must stay NULL.
    connection.execute(
        sa.text("""
            UPDATE roles
            SET legacy_role = 'ENGINEER'
            WHERE legacy_role IS NULL AND code <> 'archived_field_staff'
        """)
    )


def downgrade() -> None:
    op.drop_column("roles", "legacy_affiliation")
    op.drop_column("roles", "legacy_role")
