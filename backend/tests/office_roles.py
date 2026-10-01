"""Give test accounts their office role explicitly.

Every account the suite creates names the office role it holds — a seeded
template code such as `"org_admin"`, `"project_manager"`, `"engineer"`,
`"senior_engineer"`, `"contractor_representative"` or
`"client_representative"`. `users.org_role_id` is NOT NULL, so an account
cannot be written without one, exactly as in production.

`with_office_role` sets the role and the `is_internal` flag that goes with it,
through `rbac.apply_template_role` — the helper the creation paths use. Call
it before the account is added or flushed, once any `company_id` it will carry
is set: an office's own copy of a role takes precedence over the shared
template, so the company is part of the answer.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.services import rbac


def with_office_role(db: Session, user: User, role: str) -> User:
    """Assign the office role with template code `role` to `user`, and return `user`."""
    assigned = rbac.apply_template_role(db, user, role)
    assert assigned is not None, (
        f"No seeded office role {role!r}. Seed the role templates "
        "(rbac.seed_roles) before creating this account."
    )
    return user
