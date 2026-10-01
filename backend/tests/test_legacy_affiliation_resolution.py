"""An unrecognised `engineer_affiliation` must not resolve to a role.

This is the legacy backfill's translation (`app.db.legacy_rbac`), the only
place the retired `users.role` / `engineer_affiliation` pair is still read.

`template_for_legacy` used to try `(role, affiliation)` and then fall back to
`(role, None)`. For every role but one that fallback is correct and deliberate:
ADMIN, PROJECT_MANAGER and OWNER never carried an affiliation, so ignoring the
column is the right answer for them.

For ENGINEER it was a fail-open authorization classification. The affiliation is
the *only* thing separating an office engineer from an outside contractor, so a
value the platform did not recognise — a typo, a hand-edited row, a value from
a system that spells it differently — fell through to `(ENGINEER, None)` and
produced the internal `engineer` template:

    engineer_affiliation="main_contracter"  ->  engineer  ->  is_internal=True

The fix is to refuse. There is no safe role to guess here: guessing high hands
an outsider internal access, and guessing low would silently strip a legitimate
account nobody had a reason to distrust. That the refusal rolls the whole
backfill back is pinned end to end in `test_fresh_deployment_rbac.py`.
"""

from __future__ import annotations

import pytest

from app.core.role_templates import BY_CODE_TEMPLATE, LEGACY_CONSULTANT_TEMPLATE
from app.db.legacy_rbac import (
    LEGACY_ROLE_MAP,
    SUPPORTED_AFFILIATIONS,
    UnknownAffiliation,
    UnknownLegacyRole,
    template_for_legacy,
)

#: The values PostgreSQL stored for the retired `user_role` type.
LEGACY_ROLES = ("ADMIN", "OWNER", "PROJECT_MANAGER", "ENGINEER", "CONSULTANT", "WORKER")

#: Values that must keep working, written out rather than imported from the
#: module under test so that a change there cannot quietly change what this
#: asserts.
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


def _template(code):
    return LEGACY_CONSULTANT_TEMPLATE if code == LEGACY_CONSULTANT_TEMPLATE.code else BY_CODE_TEMPLATE[code]


# --- the vocabulary ----------------------------------------------------------

def test_the_supported_set_is_exactly_the_three_the_retired_model_used():
    assert SUPPORTED_AFFILIATIONS == frozenset(RECOGNISED)


def test_every_mapped_code_is_a_seeded_template():
    """A legacy account can only land on a role `seed_roles` actually creates."""
    for code in LEGACY_ROLE_MAP.values():
        assert _template(code).code == code


# --- behaviour that must not change ------------------------------------------

def test_main_contractor_is_the_external_contractor_template():
    code = template_for_legacy("ENGINEER", "main_contractor")
    assert code == "contractor_representative"
    assert _template(code).is_internal_only is False


def test_internal_engineer_is_the_internal_engineer_template():
    code = template_for_legacy("ENGINEER", "internal_engineer")
    assert code == "engineer"
    assert _template(code).is_internal_only is True


def test_external_consultant_is_office_review_staff():
    """The deliberate non-literal mapping. See `LEGACY_ROLE_MAP`."""
    code = template_for_legacy("ENGINEER", "external_consultant")
    assert code == "senior_engineer"
    assert _template(code).is_internal_only is True


@pytest.mark.parametrize(
    "role, expected",
    [
        ("ADMIN", "org_admin"),
        ("PROJECT_MANAGER", "project_manager"),
        ("ENGINEER", "engineer"),
        ("OWNER", "client_representative"),
        ("WORKER", "archived_field_staff"),
        ("CONSULTANT", "legacy_consultant"),
    ],
)
def test_affiliation_none_uses_the_role_only_mapping(role, expected):
    """`None` is not a typo and must not be treated as one: most roles never
    carried an affiliation, so rejecting it would refuse every administrator."""
    assert template_for_legacy(role, None) == expected


@pytest.mark.parametrize("affiliation", RECOGNISED)
def test_a_role_that_never_carried_an_affiliation_ignores_a_recognised_one(affiliation):
    assert template_for_legacy("OWNER", affiliation) == "client_representative"


# --- the vulnerability -------------------------------------------------------

@pytest.mark.parametrize("affiliation", UNRECOGNISED)
def test_an_unrecognised_affiliation_is_refused(affiliation):
    with pytest.raises(UnknownAffiliation):
        template_for_legacy("ENGINEER", affiliation)


def test_the_original_typo_no_longer_becomes_an_internal_engineer():
    """The exact case the audit measured, named so a regression is legible."""
    with pytest.raises(UnknownAffiliation) as excinfo:
        template_for_legacy("ENGINEER", "main_contracter")
    message = str(excinfo.value)
    assert "main_contracter" in message
    assert "main_contractor" in message, "the message should show the valid values"


@pytest.mark.parametrize("role", LEGACY_ROLES)
@pytest.mark.parametrize("affiliation", UNRECOGNISED)
def test_no_unrecognised_affiliation_produces_any_template_for_any_role(role, affiliation):
    """Not "it does not return `engineer`" but "it does not return" — including
    `archived_field_staff`, the tempting wrong answer: parking the account
    somewhere harmless would keep a corrupt affiliation from ever being noticed."""
    with pytest.raises(UnknownAffiliation):
        result = template_for_legacy(role, affiliation)
        pytest.fail(f"resolved to {result!r} instead of refusing")


@pytest.mark.parametrize("role", ["", "SUPERUSER", "contractor", None])
def test_an_unrecognised_role_is_refused(role):
    with pytest.raises(UnknownLegacyRole):
        template_for_legacy(role, None)
