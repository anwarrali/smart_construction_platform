"""The retired role model, kept only to migrate a database that still holds it.

Nothing in the running application imports this module. Authorization is
`users.org_role_id → roles → role_permissions`, resolved by
`app.services.authorization.effective_permissions`. What lives here is the
vocabulary of the model that preceded it — the six-value `user_role` enum, the
`engineer_affiliation` strings and the role-keyed overrides — and the one
translation `app.db.rbac_backfill` needs to move such a database across.

Values are the strings PostgreSQL stores for the retired `user_role` type
(`ADMIN`, `ENGINEER`, …), read with raw SQL: the ORM no longer maps the legacy
columns, and after the contract migration they do not exist at all.
"""

from __future__ import annotations

#: Where an existing account's authority moves to, keyed by
#: `(users.role, users.engineer_affiliation)`. The affiliation is ignored for
#: roles that never carried one.
LEGACY_ROLE_MAP: dict[tuple[str, str | None], str] = {
    ("ADMIN", None): "org_admin",
    ("PROJECT_MANAGER", None): "project_manager",
    ("ENGINEER", "internal_engineer"): "engineer",
    ("ENGINEER", "main_contractor"): "contractor_representative",
    # The reviewing side of the old owner/contractor/consultant triangle. The
    # consulting office *is* the reviewer, so these accounts become office
    # staff with review authority rather than an outside party.
    ("ENGINEER", "external_consultant"): "senior_engineer",
    ("ENGINEER", None): "engineer",
    ("OWNER", None): "client_representative",
    ("WORKER", None): "archived_field_staff",
    ("CONSULTANT", None): "legacy_consultant",
}

#: The affiliation strings the map is written in terms of. Derived from the map
#: so the two cannot disagree.
SUPPORTED_AFFILIATIONS: frozenset[str] = frozenset(
    affiliation for _role, affiliation in LEGACY_ROLE_MAP if affiliation is not None
)

#: Which retired role each seeded template took its permissions from. Used for
#: one thing: folding the administrator's retired `role_permission_overrides`
#: (keyed by that role) into the roles that replaced it, so a permission an
#: office had switched on or off before the redesign stays on or off after it.
LEGACY_INHERITS: dict[str, str | None] = {
    "org_admin": "ADMIN",
    "office_director": "ADMIN",
    "technical_director": "ADMIN",
    "project_manager": "PROJECT_MANAGER",
    "senior_engineer": "ENGINEER",
    "engineer": "ENGINEER",
    "site_engineer": "ENGINEER",
    "bim_engineer": "ENGINEER",
    "cad_technician": "ENGINEER",
    "surveyor": "ENGINEER",
    "document_controller": "ENGINEER",
    "office_staff": None,
    "client_representative": "OWNER",
    "contractor_representative": "ENGINEER",
    "subcontractor_representative": "ENGINEER",
    "external_reviewer": "ENGINEER",
    "archived_field_staff": None,
    "legacy_consultant": "CONSULTANT",
}

#: Affiliations that describe somebody working for the main contractor — the
#: accounts that become external project participants.
CONTRACTOR_AFFILIATIONS = frozenset({"main_contractor"})


class UnknownAffiliation(ValueError):
    """An `engineer_affiliation` the platform does not recognise.

    There is no safe role to guess: guessing high hands an outsider internal
    access, guessing low silently strips a legitimate account. The backfill
    therefore stops, and its transaction rolls back, until the row is fixed.
    """


class UnknownLegacyRole(ValueError):
    """A `users.role` value outside the retired enum."""


def template_for_legacy(role: str, affiliation: str | None) -> str:
    """The template code an account with this retired role and affiliation moves onto.

    Fails closed: an affiliation outside `SUPPORTED_AFFILIATIONS`, on any
    role, raises `UnknownAffiliation`. Before this rule an unrecognised value
    fell through to `(ENGINEER, None)` — the internal `engineer` template — so
    a typo such as `main_contracter` silently turned an outside contractor into
    office staff. `None` is not a typo: roles that never carried an affiliation
    resolve through their `(role, None)` entry.
    """
    if affiliation is not None and affiliation not in SUPPORTED_AFFILIATIONS:
        raise UnknownAffiliation(
            f"Unrecognised engineer_affiliation {affiliation!r} for role {role}. "
            f"Supported values are {sorted(SUPPORTED_AFFILIATIONS)}."
        )
    key = (role or "").upper()
    code = LEGACY_ROLE_MAP.get((key, affiliation)) or LEGACY_ROLE_MAP.get((key, None))
    if code is None:
        raise UnknownLegacyRole(f"Unrecognised legacy role {role!r}")
    return code
