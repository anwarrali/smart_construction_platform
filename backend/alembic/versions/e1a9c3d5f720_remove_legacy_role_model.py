"""Remove the retired role model: the configurable roles are the only source

The contract step of the RBAC redesign. Authorization has resolved from
`users.org_role_id → roles → role_permissions` for some time; what remained of
the six-value role enum was written for compatibility and read nowhere that
decides anything. This removes it:

  * `role_permission_overrides` — the role-keyed override table, superseded by
    editing a role's own permissions;
  * `users.role` and `users.engineer_affiliation`;
  * `project_members.role_on_project`;
  * `roles.legacy_role` and `roles.legacy_affiliation`;
  * the `user_role` PostgreSQL type, which only those three columns used. A
    value cannot be dropped from a PostgreSQL enum, so the type goes whole,
    after every column that uses it.

and makes `users.org_role_id` NOT NULL, so no account can exist without an
office role.

## The guard

It refuses to run while any account has no office role. On such a database
the retired columns are the only record of what those people may do, and
dropping them would lose it. Run the legacy backfill first, at the previous
revision:

    alembic upgrade c84d6e2f1a37
    python -m app.db.rbac_backfill
    alembic upgrade head

A database created after the redesign never reaches that state: every
creation path assigns the role before it writes the account.

## Downgrade

Restores the *schema* — nullable columns, the table and the type — and fills
`users.role` from each account's office role so the retired column is not
left empty. `engineer_affiliation`, `role_on_project` and any override rows
are not reconstructed; restore them from a backup taken before upgrading if
they are needed.

Revision ID: e1a9c3d5f720
Revises: c84d6e2f1a37
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e1a9c3d5f720"
down_revision = "c84d6e2f1a37"
branch_labels = None
depends_on = None

LEGACY_VALUES = ("ADMIN", "OWNER", "PROJECT_MANAGER", "ENGINEER", "CONSULTANT", "WORKER")

#: Used only by the downgrade, to give `users.role` a value. Written out, not
#: imported: a migration records what it does regardless of application code.
OFFICE_ROLE_TO_LEGACY = {
    "org_admin": "ADMIN",
    "office_director": "ADMIN",
    "technical_director": "PROJECT_MANAGER",
    "project_manager": "PROJECT_MANAGER",
    "client_representative": "OWNER",
    "archived_field_staff": "WORKER",
    "legacy_consultant": "CONSULTANT",
}


def upgrade() -> None:
    connection = op.get_bind()
    unmigrated = connection.execute(
        sa.text("SELECT count(*) FROM users WHERE org_role_id IS NULL")
    ).scalar()
    if unmigrated:
        raise RuntimeError(
            f"{unmigrated} account(s) have no office role. Their access is recorded only "
            "in the legacy columns this migration removes. Run the legacy backfill at "
            "revision c84d6e2f1a37 first: `python -m app.db.rbac_backfill`."
        )

    op.drop_table("role_permission_overrides")
    op.drop_column("users", "role")
    op.drop_column("users", "engineer_affiliation")
    op.drop_column("project_members", "role_on_project")
    op.drop_column("roles", "legacy_role")
    op.drop_column("roles", "legacy_affiliation")
    op.alter_column("users", "org_role_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.execute("DROP TYPE user_role")


def downgrade() -> None:
    user_role = postgresql.ENUM(*LEGACY_VALUES, name="user_role")
    user_role.create(op.get_bind(), checkfirst=True)
    role_type = postgresql.ENUM(*LEGACY_VALUES, name="user_role", create_type=False)

    op.alter_column("users", "org_role_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column("roles", sa.Column("legacy_affiliation", sa.String(length=40), nullable=True))
    op.add_column("roles", sa.Column("legacy_role", sa.String(length=30), nullable=True))
    op.add_column("project_members", sa.Column("role_on_project", role_type, nullable=True))
    op.add_column("users", sa.Column("engineer_affiliation", sa.String(length=40), nullable=True))
    op.create_index("ix_users_engineer_affiliation", "users", ["engineer_affiliation"])
    op.add_column("users", sa.Column("role", role_type, nullable=True))
    op.create_index("ix_users_role", "users", ["role"])

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE users SET role = 'ENGINEER'"))
    for code, legacy in OFFICE_ROLE_TO_LEGACY.items():
        connection.execute(
            sa.text(
                "UPDATE users u SET role = CAST(:legacy AS user_role) "
                "FROM roles r WHERE r.id = u.org_role_id AND r.code = :code"
            ),
            {"legacy": legacy, "code": code},
        )

    op.create_table(
        "role_permission_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role", role_type, nullable=False),
        sa.Column("permission_code", sa.String(length=80), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("role", "permission_code", name="uq_role_permission_override"),
    )
    op.create_index("ix_role_permission_overrides_role", "role_permission_overrides", ["role"])
    op.create_index(
        "ix_role_permission_overrides_permission_code", "role_permission_overrides", ["permission_code"]
    )
