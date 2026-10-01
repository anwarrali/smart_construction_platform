"""Give test accounts their office role explicitly.

Fixtures describe people the way the suite always has — by the retired
`UserRole` and, for an engineer, `engineer_affiliation` — because that is the
vocabulary the scenarios are written in. Nothing turns that description into
an office role during the flush any more — the `user_role_backstop` listener
that used to is gone — so an account written without one has no role, and
permission resolution refuses it.

`with_office_role` resolves the role through the platform's own mapping —
`rbac.apply_legacy_template_role`, the one production provisioning uses — so a
fixture keeps exactly the role its description implied: an ADMIN is
`org_admin`, a `main_contractor` engineer the external
`contractor_representative`, an `external_consultant` engineer the office's
`senior_engineer`, a WORKER the archived field-staff role, and so on. It sets
`is_internal` with the role, as provisioning does.

Call it on the account before it is added or flushed, once any `company_id` it
will carry is set: an office's own copy of a role takes precedence over the
shared template, so the company is part of the answer.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.services import rbac


def with_office_role(db: Session, user: User) -> User:
    """Assign the office role `user`'s legacy role maps to, and return `user`."""
    role = rbac.apply_legacy_template_role(db, user)
    assert role is not None, (
        f"No seeded office role for {user.role!r} / {user.engineer_affiliation!r}. "
        "Seed the role templates (rbac.seed_roles) before creating this account."
    )
    return user
