"""An unrecognised `engineer_affiliation` must not resolve to a role.

`template_for_legacy` used to try `(role, affiliation)` and then fall back to
`(role, None)`. For every role but one that fallback is correct and deliberate:
ADMIN, PROJECT_MANAGER and OWNER never carried an affiliation, so ignoring the
column is the right answer for them.

For ENGINEER it was a fail-open authorization classification. The affiliation is
the *only* thing separating an office engineer from an outside contractor, so a
value the platform did not recognise — a typo, a hand-edited row, a value from
a system that spells it differently — fell through to `(ENGINEER, None)` and
produced the `engineer` template, which is `is_internal_only=True`. The account
was then written as internal office staff:

    engineer_affiliation="main_contracter"  ->  engineer  ->  is_internal=True

which drops the project-scoped ceiling `is_external_participant` exists to
impose. The `rbac.apply_org_role` docstring records the same mistake having been
made once already from the other direction — filling `org_role_id` without
`is_internal` — and this is that failure reached by a different route.

The fix is to refuse. There is no safe role to guess here: guessing high hands
an outsider internal access, and guessing low would silently strip a legitimate
account nobody had a reason to distrust. Neither belongs in a resolver.

Scope note: these tests are about *legacy role template resolution*. They are
not evidence about the rest of the `users.role` migration, and the RBAC
equivalence gate is not evidence about them — it compares permission resolution
for accounts that already have a role and never runs a creation path.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.role_templates import (
    BY_CODE_TEMPLATE,
    LEGACY_CONSULTANT_TEMPLATE,
    SUPPORTED_AFFILIATIONS,
    UnknownAffiliation,
    template_for_legacy,
)
from app.db.database import SessionLocal
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.services import rbac
from app.services.user_service import create_provisioned_user
from tests.office_roles import with_office_role

#: Values that must keep working. Exactly the closed set `UserCreateByAdmin`
#: validates against, written out rather than imported from the module under
#: test so that a change there cannot quietly change what this asserts.
RECOGNISED = ("internal_engineer", "main_contractor", "external_consultant")

#: Values that must be refused. The first is the real one — a single
#: transposed pair of letters in `main_contractor`, which is how this arrives
#: in practice; the rest cover casing, whitespace, the empty string and a value
#: from a vocabulary the platform does not share.
UNRECOGNISED = (
    "main_contracter",
    "maincontractor",
    "Main_Contractor",
    " main_contractor",
    "main_contractor ",
    "subcontractor",
    "external-consultant",
    "contractor",
    "",
    "none",
    "null",
    "unknown",
)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:  # pragma: no cover - only without a database
        session.close()
        pytest.skip("database is not reachable")
    try:
        yield session
    finally:
        # Nothing here is ever committed: the point of the flush test below is
        # that the row does not reach the database.
        session.rollback()
        session.close()


# --- the vocabulary ----------------------------------------------------------

def test_the_supported_set_is_exactly_the_three_the_api_accepts():
    """Derived from `LEGACY_ROLE_MAP`, so drift is impossible within the module.

    Pinned against a literal here because the *other* end of the contract —
    `UserCreateByAdmin.validate_admin_create` — lives in `app/schemas/user.py`
    and cannot be derived from. If someone widens one they must see this fail.
    """
    assert SUPPORTED_AFFILIATIONS == frozenset(RECOGNISED)


# --- behaviour that must not change ------------------------------------------

def test_main_contractor_is_still_the_external_contractor_template():
    template = template_for_legacy(UserRole.ENGINEER, "main_contractor")
    assert template.code == "contractor_representative"
    assert template.is_internal_only is False


def test_internal_engineer_is_still_the_internal_engineer_template():
    template = template_for_legacy(UserRole.ENGINEER, "internal_engineer")
    assert template.code == "engineer"
    assert template.is_internal_only is True


def test_external_consultant_is_still_office_review_staff():
    """The deliberate non-literal mapping. See `LEGACY_ROLE_MAP`."""
    template = template_for_legacy(UserRole.ENGINEER, "external_consultant")
    assert template.code == "senior_engineer"
    assert template.is_internal_only is True


@pytest.mark.parametrize(
    "role, expected",
    [
        (UserRole.ADMIN, "org_admin"),
        (UserRole.PROJECT_MANAGER, "project_manager"),
        (UserRole.ENGINEER, "engineer"),
        (UserRole.OWNER, "client_representative"),
        (UserRole.WORKER, "archived_field_staff"),
    ],
)
def test_affiliation_none_still_uses_the_role_only_mapping(role, expected):
    """`None` is not a typo and must not be treated as one.

    Three of these roles never carry an affiliation at all — `user_service`
    writes the column only for ENGINEER — so rejecting `None` would refuse
    every administrator in the database.
    """
    assert template_for_legacy(role, None).code == expected


def test_consultant_still_gets_the_legacy_consultant_template():
    assert template_for_legacy(UserRole.CONSULTANT, None) is LEGACY_CONSULTANT_TEMPLATE


@pytest.mark.parametrize("affiliation", RECOGNISED)
def test_a_role_that_never_carried_an_affiliation_still_ignores_one(affiliation):
    """A recognised value on a non-ENGINEER role keeps falling through.

    This is the fallback the fix deliberately leaves alone: `LEGACY_ROLE_MAP`
    has no `(OWNER, ...)` entry other than `None`, and an owner is a client
    representative regardless of what the column happens to say.
    """
    assert template_for_legacy(UserRole.OWNER, affiliation).code == "client_representative"


# --- the vulnerability -------------------------------------------------------

@pytest.mark.parametrize("affiliation", UNRECOGNISED)
def test_an_unrecognised_affiliation_is_refused(affiliation):
    with pytest.raises(UnknownAffiliation):
        template_for_legacy(UserRole.ENGINEER, affiliation)


def test_the_original_typo_no_longer_becomes_an_internal_engineer():
    """The exact case the audit measured, named so a regression is legible."""
    with pytest.raises(UnknownAffiliation) as excinfo:
        template_for_legacy(UserRole.ENGINEER, "main_contracter")
    message = str(excinfo.value)
    assert "main_contracter" in message
    assert "main_contractor" in message, "the message should show the valid values"


def test_the_refusal_is_a_value_error():
    """`app/api/users.py` turns a `ValueError` from provisioning into a 400.

    Subclassing it is what makes a mistyped affiliation a bad request rather
    than a 500, without a caller having to know this type exists.
    """
    assert issubclass(UnknownAffiliation, ValueError)
    with pytest.raises(ValueError):
        template_for_legacy(UserRole.ENGINEER, "main_contracter")


@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.parametrize("affiliation", UNRECOGNISED)
def test_no_unrecognised_affiliation_produces_any_template_for_any_role(role, affiliation):
    """The negative form of the fix, stated across the whole enum.

    Not "it does not return `engineer`" but "it does not return" — a future
    fallback added for some other reason cannot satisfy this test by picking a
    different role, including `archived_field_staff`, which is the tempting
    wrong answer: parking the account somewhere harmless would keep a corrupt
    affiliation from ever being noticed.
    """
    with pytest.raises(UnknownAffiliation):
        result = template_for_legacy(role, affiliation)
        pytest.fail(f"resolved to {result.code!r} instead of refusing")


def test_every_seeded_template_remains_reachable_by_code():
    """Guards the assertion above from being vacuously true.

    If `template_for_legacy` were broken outright, every test in this file that
    expects a refusal would still pass. This one fails instead.
    """
    for code in ("engineer", "contractor_representative", "archived_field_staff"):
        assert BY_CODE_TEMPLATE[code].code == code


# --- end to end, through the paths that write accounts --------------------

def _engineer(affiliation):
    return User(
        full_name="Affiliation Check",
        email=f"affiliation-{uuid4().hex[:12]}@example.com",
        hashed_password="x",
        role=UserRole.ENGINEER,
        status=UserStatus.ACTIVE,
        engineer_affiliation=affiliation,
    )


def test_a_corrupt_affiliation_is_refused_before_the_account_is_written(db):
    """Where the fail-open used to reach the database, it now stops.

    It reached the database through `user_role_backstop`, which resolved a
    role during the flush for any `User` written without one. That listener is
    gone; every path that writes an account now resolves its role *before*
    writing, through `rbac.apply_legacy_template_role` or its provisioning
    equivalent — and that resolution is what refuses. Before the fix this
    account got the `engineer` template and `is_internal=True`.
    """
    row = _engineer("main_contracter")
    with pytest.raises(UnknownAffiliation):
        rbac.apply_legacy_template_role(db, row)
    assert row.org_role_id is None


def test_provisioning_refuses_a_corrupt_affiliation_and_writes_nothing(db):
    """The service path, below the API schema that already rejects the value.

    `UserCreateByAdmin` guards `POST /users`; `create_provisioned_user` is also
    reachable from code, and must not turn a typo into office staff either.
    """
    admin = with_office_role(db, User(
        full_name="Affiliation Admin", email=f"affiliation-admin-{uuid4().hex[:12]}@example.com",
        hashed_password="x", role=UserRole.ADMIN, status=UserStatus.ACTIVE,
    ))
    db.add(admin)
    db.flush()
    email = f"corrupt-provisioned-{uuid4().hex[:12]}@example.com"

    with pytest.raises(UnknownAffiliation):
        create_provisioned_user(
            db, creator=admin, email=email, full_name="Corrupt Provisioned",
            role=UserRole.ENGINEER, engineer_affiliation="main_contracter",
            password="Str0ngPassw0rd!", send_email=False,
        )
    db.rollback()
    assert db.query(User).filter(User.email == email).first() is None


def test_a_recognised_affiliation_still_resolves_to_an_external_role(db):
    """The control. Without it the tests above could pass for the wrong reason."""
    row = _engineer("main_contractor")
    role = rbac.apply_legacy_template_role(db, row)
    assert role is not None and role.code == "contractor_representative"
    assert row.org_role_id == role.id
    assert row.is_internal is False, "a contractor must not be written as internal"
    db.add(row)
    db.flush()
    db.rollback()
