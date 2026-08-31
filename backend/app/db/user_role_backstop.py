"""Every account reaches the database with an office role.

`RBAC_REQUIRE_DB_ROLES` turns "this account has no `org_role_id`" from a silent
fallback into a hard failure. That is only a safety feature if nothing can
*create* such an account — otherwise the flag converts a tolerated state into an
outage, which is worse than the state it was meant to catch.

`create_provisioned_user` assigns a role on both its paths, but it is not the
only way a `User` row is written. Seed scripts write them, migrations write
them, tests write them by the hundred, and any code added later will write them
too. Fixing each caller leaves the *next* caller broken, and the next caller is
the one nobody reviews.

So the invariant is enforced where it cannot be forgotten: a `before_flush`
listener fills `org_role_id` for any new account that arrives without one,
from the seeded role its retired enum maps to — the same mapping
`rbac_backfill` used for the accounts that already existed.

## It runs always, since the contract step

It used to be gated on `RBAC_REQUIRE_DB_ROLES`, because while the pre-backfill
fallback existed an account without a role was a *supported* state and three
bridges depended on being able to construct one. The contract step removed the
fallback and the bridges with it: `resolved_permissions` now refuses an account
that has no role, so filling the column is no longer a policy choice but the
only way such a row can be written at all. The flag is gone.

## `is_internal` moves with it, and must

The first version of this filled `org_role_id` alone and was wrong in a way
worth recording. `is_external_participant` reads the affiliation bridge while
`org_role_id IS NULL`, and `is_internal` once it is set. Setting the role
without the flag flipped a contractor from external to internal — the column
defaults to true — which dropped the non-project-scoped ceiling and handed them
`platform.view_all_projects` on every project in the office. A backstop that
does half a provisioning job is worse than none;
`test_an_external_account_cannot_be_granted_it` caught it.

## What this is not

It is not a substitute for provisioning correctly. `create_provisioned_user`
still resolves the role explicitly and records the organization membership,
which this deliberately does not — an office membership is a statement about a
person that only provisioning is in a position to make.

It is also not a security control. The role it assigns is the one the account's
own legacy enum already implied, so it grants nothing the fallback would not
have granted anyway.

## Why `before_flush` and not `before_insert`

Mapper-level insert events run inside the flush and must not emit queries
against the session being flushed. Finding a role is a query. `before_flush`
is the sanctioned place for exactly this, and it sees `session.new` before any
SQL has been written.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session

_INSTALLED = False


def _fill_missing_org_roles(session: Session, _flush_context, _instances) -> None:
    # Imported here rather than at module scope: `app.services.rbac` imports the
    # models, and the models import this. A local import keeps the cycle from
    # existing at all rather than relying on import order to hide it.
    from app.models.user import User
    from app.services import rbac

    pending = [
        row for row in session.new
        if isinstance(row, User) and row.org_role_id is None
    ]
    if not pending:
        return

    for row in pending:
        if row.role is None:
            # Nothing to map from. `users.role` is NOT NULL, so this is a row
            # that was going to fail anyway; letting it fail on its own
            # constraint gives a better error than one invented here.
            continue
        role = rbac.template_role_for_legacy_user(session, row)
        if role is None:
            continue
        row.org_role_id = role.id
        # Both, always. `is_external_participant` switches from the affiliation
        # bridge to this column the moment a role is set, so filling one
        # without the other silently reclassifies a contractor as office staff.
        row.is_internal = bool(role.is_internal_only)


def install() -> None:
    """Register the listener once, for every session in the process."""
    global _INSTALLED
    if _INSTALLED:
        return
    event.listen(Session, "before_flush", _fill_missing_org_roles)
    _INSTALLED = True
