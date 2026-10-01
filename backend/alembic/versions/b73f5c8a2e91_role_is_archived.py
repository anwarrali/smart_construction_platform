"""Give archived roles a column that says so

`Role.legacy_role` was carrying two unrelated jobs. Its stated one is to record
which retired `users.role` value an account created under this role is written
with — a migration-window bridge that disappears when `users.role` does. Its
unstated one was policy: `legacy_role IS NULL` meant "this role exists to hold
history, so no account may be created under it and nobody on it may be staffed
onto a project", and `services/rbac.py` read exactly that predicate to power
`staffable_filter()` and `is_staffable()`.

Those two facts are true of the same single row today, which is why nobody had
to separate them. But they are not the same fact, and the day `legacy_role` is
dropped the second one would vanish silently — turning a role nobody may be
created under into an ordinary one, and making retired worker accounts staffable
again. `is_archived` states it directly, so it survives the bridge being removed.

## The backfill

    is_archived = (legacy_role IS NULL)

Derived, not hard-coded to `archived_field_staff`. Deriving it reproduces the
predicate the code actually used, which is the only definition of "archived"
this database has ever had; naming the template instead would silently disagree
with any row an office had created that happened to satisfy the old rule.

## Idempotence and safety

`server_default='false'` fills every existing row before the UPDATE runs, so no
row is ever NULL and the column can be NOT NULL immediately. The UPDATE is
naturally idempotent — re-running it computes the same value from the same
source — and touches no other column. `legacy_role` is read and left exactly as
it is: nothing here changes translation, and nothing here changes an existing
authorization answer, because the value written is the one the old predicate
already produced.

## Downgrade

Drops the column. Safe precisely because the old predicate is still present and
still correct: `services/rbac.py` at the previous revision reads
`legacy_role IS NULL`, which is what this column was filled from, so reverting
the schema restores a working system rather than one missing a rule.

Revision ID: b73f5c8a2e91
Revises: a92d4e1f70b3
"""

from alembic import op
import sqlalchemy as sa

revision = "b73f5c8a2e91"
down_revision = "a92d4e1f70b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    result = op.get_bind().execute(
        sa.text("UPDATE roles SET is_archived = true WHERE legacy_role IS NULL")
    )
    # Printed so an operator sees the count rather than trusting that a policy
    # rule moved silently and correctly.
    print(f"[{revision}] marked {result.rowcount} role(s) archived")


def downgrade() -> None:
    op.drop_column("roles", "is_archived")
