"""The roles and disciplines a consulting office starts with.

Nothing here is a hardcoded role model. These are *templates*: rows the office
gets on day one so the platform is usable before anybody configures anything,
and which an administrator can then rename, re-permission or delete. The
authority is always the `roles` / `role_permissions` tables — this module only
says what to put in them the first time.

## Why the permission sets are expressed as "inherits from a legacy role"

The redesign must not change who can do what as a side effect of becoming
configurable. Every template that existing accounts are migrated onto therefore
derives its permission set from `permission_catalogue.role_defaults(...)` for
the role those accounts hold today, rather than from a fresh opinion about what
a Site Engineer ought to be allowed to do. Seeding from the catalogue is what
makes the old-vs-new equivalence gate in `app.db.rbac_equivalence` come out
empty; a hand-written set would have made it a negotiation.

Templates nobody is migrated onto (Site Engineer, BIM Engineer, Surveyor,
Document Controller…) are seeded as *available* and start out unassigned. They
exist so an office can express its own structure without inventing permission
sets from scratch.

## Internal and external

`is_internal_only` is the structural half of the internal/external split. A
role marked internal can never be given to a project member who belongs to an
external party, and an external member never holds a permission that is not
project-scoped. Both rules are enforced in `app.services.rbac`, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.permission_catalogue import BY_CODE, role_defaults
from app.models.enums import UserRole

# Role scope. A role may be held at the office level, on a project, or both.
SCOPE_ORG = "ORG"
SCOPE_PROJECT = "PROJECT"
SCOPE_BOTH = "BOTH"

# Party kinds a project may record. Deliberately a small closed list: these are
# the relationships the platform reasons about, not a free directory of
# company types.
PARTY_CLIENT = "CLIENT"
PARTY_MAIN_CONTRACTOR = "MAIN_CONTRACTOR"
PARTY_SUBCONTRACTOR = "SUBCONTRACTOR"
PARTY_CONSULTANT = "CONSULTANT"
PARTY_SUPPLIER = "SUPPLIER"
PARTY_AUTHORITY = "AUTHORITY"
PARTY_OTHER = "OTHER"

PARTY_KINDS: tuple[str, ...] = (
    PARTY_CLIENT, PARTY_MAIN_CONTRACTOR, PARTY_SUBCONTRACTOR,
    PARTY_CONSULTANT, PARTY_SUPPLIER, PARTY_AUTHORITY, PARTY_OTHER,
)

# Organization kinds. The office is the tenant; the others exist only so
# historical `Company` rows keep their meaning after the redesign. They are
# NOT a hierarchy — a contractor is recorded on a *project*, through
# `ProjectParty`, never as a subordinate of the office.
ORG_CONSULTING_OFFICE = "CONSULTING_OFFICE"
ORG_CONTRACTOR = "CONTRACTOR"
ORG_CLIENT = "CLIENT"
ORG_OTHER = "OTHER"


@dataclass(frozen=True)
class RoleTemplate:
    """One seeded role."""

    code: str
    name_en: str
    name_ar: str
    scope: str
    is_internal_only: bool
    #: Legacy role whose catalogue defaults this template starts from.
    #: `None` means "no permissions at all" — used by the archived field-staff
    #: template that removed worker accounts are parked on.
    inherits: UserRole | None
    #: Added on top of the inherited set.
    extra: frozenset[str] = field(default_factory=frozenset)
    #: Removed from the inherited set.
    without: frozenset[str] = field(default_factory=frozenset)
    #: Display order only. Carries no authorization meaning — the old
    #: `ROLE_HIERARCHY` numbers did, and that is exactly what this is not.
    rank: int = 100
    #: Refused by the delete endpoint. Only the office administrator role,
    #: because deleting it would leave nobody able to administer.
    undeletable: bool = False
    description: str = ""

    @property
    def legacy_role(self) -> str | None:
        """Which retired enum value an account created under this role gets.

        Migration-window only; it lands in `Role.legacy_role` and is dropped
        with `users.role`. It is deliberately **not** `inherits.name`, because
        the two answer different questions:

          * `inherits` is where the role's *permissions* start from;
          * this is what the retired `users.role` column is *written with*,
            and that column is still read by a handful of hardcoded checks
            during the migration window.

        Technical Director is the case that makes the difference concrete. Its
        permissions inherit from ADMIN (minus account administration), but
        writing `role=ADMIN` would make every surviving `role == UserRole.ADMIN`
        check treat it as a full administrator — the exact authority the
        template exists to withhold. PROJECT_MANAGER is the closest legacy
        shadow that does not lie.

        `None` means no account may be created under the role. That is exactly
        one template — the archived field-staff role retired worker accounts
        sit on — and refusing there is what keeps Worker unreachable through
        the new provisioning path.
        """
        return PROVISIONING_LEGACY_ROLE.get(self.code)

    @property
    def legacy_affiliation(self) -> str | None:
        """The office side an ENGINEER-backed account is written with.

        Records only the *deviation*. `None` means the account falls through to
        `internal_engineer`, which `create_provisioned_user` applies — so the
        one thing this table says is "these two are the contractor side".

        No template produces `external_consultant`. Under the confirmed product
        direction a consultant-side reviewer is office staff, not an outside
        party; the value survives only on accounts created before the redesign,
        where the pre-backfill bridges still read it.
        """
        return PROVISIONING_LEGACY_AFFILIATION.get(self.code)

    def permissions(self) -> set[str]:
        """The codes this template grants when it is first created."""
        base = set(role_defaults(self.inherits)) if self.inherits is not None else set()
        base |= {code for code in self.extra if code in BY_CODE}
        base -= self.without
        return base


def _t(code, name_en, name_ar, scope, internal, inherits, *, extra=(), without=(),
       rank=100, undeletable=False, description=""):
    return RoleTemplate(
        code, name_en, name_ar, scope, internal, inherits,
        frozenset(extra), frozenset(without), rank, undeletable, description,
    )


#: Codes a purely drafting/support role should not carry. Reviewing and
#: approving design work is an engineering authority, and a CAD technician or
#: surveyor holding it by default would be the kind of unexamined assumption
#: this redesign exists to remove.
_NO_REVIEW_AUTHORITY = ("task.review", "design_change.approve")


TEMPLATES: tuple[RoleTemplate, ...] = (
    # --- office administration ---------------------------------------------
    _t("org_admin", "Office Administrator", "مدير النظام", SCOPE_ORG, True,
       UserRole.ADMIN, rank=10, undeletable=True,
       description="Runs the platform for the office: accounts, roles and permissions."),
    _t("office_director", "General Manager", "المدير العام", SCOPE_BOTH, True,
       UserRole.ADMIN, rank=20,
       description="Office-level authority across every project."),
    _t("technical_director", "Technical Director", "المدير الفني", SCOPE_BOTH, True,
       UserRole.ADMIN, without=("platform.manage_users", "platform.manage_permissions"),
       rank=30,
       description="Technical authority across projects, without account administration."),

    # --- project leadership -------------------------------------------------
    _t("project_manager", "Project Manager", "مدير المشروع", SCOPE_BOTH, True,
       UserRole.PROJECT_MANAGER, rank=40,
       description="Runs a project: team, schedule, tasks and reviews."),

    # --- engineering --------------------------------------------------------
    # Withholds `project.view_all_disciplines` deliberately. This is where retired
    # `external_consultant` accounts land, and the platform narrowed those
    # people's document access to their own discipline. Keeping that narrowing
    # is why the permission is removed here rather than added to the others:
    # their actual access is unchanged, the rule that produces it is simply
    # written down now instead of being inferred from an affiliation string.
    _t("senior_engineer", "Senior Engineer", "مهندس أول", SCOPE_BOTH, True,
       UserRole.ENGINEER, without=("project.view_all_disciplines",), rank=50,
       description="Design and review authority within their disciplines."),
    _t("engineer", "Engineer", "مهندس", SCOPE_BOTH, True,
       UserRole.ENGINEER, rank=60,
       description="Design, coordination and technical work."),
    _t("site_engineer", "Site Engineer", "مهندس موقع", SCOPE_PROJECT, True,
       UserRole.ENGINEER, extra=("field_evidence.submit", "site_report.submit"), rank=70,
       description="Supervises work on site: reports, evidence and observations."),
    _t("bim_engineer", "BIM Engineer", "مهندس نمذجة", SCOPE_BOTH, True,
       UserRole.ENGINEER, extra=("ifc.upload", "ifc.manage_version"), rank=80,
       description="Owns the model: revisions, coordination and clash review."),
    _t("cad_technician", "CAD Technician", "فني رسم", SCOPE_BOTH, True,
       UserRole.ENGINEER, without=_NO_REVIEW_AUTHORITY, rank=90,
       description="Drawing production and technical drafting."),
    _t("surveyor", "Surveyor", "مساح", SCOPE_BOTH, True,
       UserRole.ENGINEER, extra=("field_evidence.submit",), without=_NO_REVIEW_AUTHORITY,
       rank=95,
       description="Setting out, measurement and survey records."),
    _t("document_controller", "Document Controller", "مسؤول الوثائق", SCOPE_BOTH, True,
       UserRole.ENGINEER,
       extra=("project.view_all_disciplines", "document.share_external", "document.upload"),
       without=_NO_REVIEW_AUTHORITY, rank=100,
       description="Custody of project documents, revisions and distribution."),
    _t("office_staff", "Administrative Staff", "موظف إداري", SCOPE_ORG, True,
       None, extra=("task.view",), rank=110,
       description="Office administration. Starts with read access only."),

    # --- external project participants --------------------------------------
    # Every one of these is project-scoped and non-internal. `is_internal_only`
    # is False, which is what lets them be attached to a ProjectParty.
    _t("client_representative", "Client Representative", "ممثل العميل",
       SCOPE_PROJECT, False, UserRole.OWNER, rank=200,
       description="The client's contact on this project."),
    _t("contractor_representative", "Main Contractor", "المقاول الرئيسي",
       SCOPE_PROJECT, False, UserRole.ENGINEER, rank=210,
       description="The main contractor's engineer on this project."),
    _t("subcontractor_representative", "Subcontractor", "مقاول من الباطن",
       SCOPE_PROJECT, False, UserRole.ENGINEER, rank=220,
       description="A subcontractor's engineer on this project."),
    _t("external_reviewer", "External Reviewer", "مراجع خارجي",
       SCOPE_PROJECT, False, UserRole.ENGINEER, rank=230,
       description="An outside consultant reviewing work on this project."),

    # --- migration target ---------------------------------------------------
    # Where removed worker accounts land. Zero permissions on purpose: the
    # account survives so its field evidence stays attributable, and it can
    # do nothing. See docs/CONSULTING_OFFICE_REDESIGN.md §7.
    _t("archived_field_staff", "Field Staff (archived)", "عامل ميداني (مؤرشف)",
       SCOPE_ORG, True, None, rank=900,
       description="Retained for historical evidence only. Holds no permissions."),
)

#: What `users.role` is written with for an account created under each seeded
#: role. Mirrored verbatim by the `e48c1b6d3f27` migration, which cannot import
#: this module; `test_provisioning_legacy_roles_match_the_migration` asserts the
#: two agree, so they cannot drift.
#:
#: Every entry is the least-privileged legacy value that still resolves
#: correctly — see `RoleTemplate.legacy_role` for why that is not the same as
#: the role the permissions inherit from. `archived_field_staff` is absent on
#: purpose: no account may be created under it.
PROVISIONING_LEGACY_ROLE: dict[str, str] = {
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

#: Mirrored by `TEMPLATE_AFFILIATION` in the `e48c1b6d3f27` migration, and
#: asserted equal by the same test. Only deviations are listed; everything else
#: falls through to `internal_engineer`.
PROVISIONING_LEGACY_AFFILIATION: dict[str, str] = {
    "contractor_representative": "main_contractor",
    "subcontractor_representative": "main_contractor",
}

BY_CODE_TEMPLATE: dict[str, RoleTemplate] = {item.code: item for item in TEMPLATES}

#: Where an existing account's authority moves to. Keyed by
#: `(UserRole, engineer_affiliation)`; the affiliation is ignored for roles
#: that never carried one. Every mapping except WORKER inherits the same
#: catalogue defaults the account holds today, which is what keeps the
#: equivalence gate empty.
LEGACY_ROLE_MAP: dict[tuple[UserRole, str | None], str] = {
    (UserRole.ADMIN, None): "org_admin",
    (UserRole.PROJECT_MANAGER, None): "project_manager",
    (UserRole.ENGINEER, "internal_engineer"): "engineer",
    (UserRole.ENGINEER, "main_contractor"): "contractor_representative",
    # An `external_consultant` account is the *reviewing* side of the old
    # owner/contractor/consultant triangle — and in the new product the
    # consulting office is itself the reviewer. These accounts therefore become
    # office staff with review authority, not an outside party. Mapping them to
    # `external_reviewer` would have been the literal reading of the old
    # affiliation string and the wrong one: it would put the office's own
    # reviewers behind deny-by-default external document scoping and revoke the
    # discipline-scoped access they have today.
    #
    # `external_reviewer` still exists, for an office that genuinely brings in
    # an outside consultant. Nobody is migrated onto it.
    (UserRole.ENGINEER, "external_consultant"): "senior_engineer",
    (UserRole.ENGINEER, None): "engineer",
    (UserRole.OWNER, None): "client_representative",
    (UserRole.WORKER, None): "archived_field_staff",
}

#: `UserRole.CONSULTANT` is unreachable on `User.role` today —
#: `UserCreateByAdmin` rewrites it — but it is a live value on
#: `ProjectMember.role_on_project`, and an old database may still hold one on a
#: user. It gets its own template seeded from the CONSULTANT catalogue defaults
#: so a migration of such a row is still exactly equivalent.
LEGACY_CONSULTANT_TEMPLATE = _t(
    "legacy_consultant", "Consultant (legacy)", "استشاري (سابق)",
    SCOPE_PROJECT, False, UserRole.CONSULTANT, rank=910,
    description="Migrated from the retired Consultant role. Review and rename it.",
)


def template_for_legacy(role: UserRole, affiliation: str | None) -> RoleTemplate:
    """The template an existing account or membership migrates onto."""
    if role == UserRole.CONSULTANT:
        return LEGACY_CONSULTANT_TEMPLATE
    code = LEGACY_ROLE_MAP.get((role, affiliation)) or LEGACY_ROLE_MAP.get((role, None))
    if code is None:
        # An unknown legacy value must not silently become a powerful role.
        return BY_CODE_TEMPLATE["archived_field_staff"]
    return BY_CODE_TEMPLATE[code]


# ---------------------------------------------------------------------------
# Disciplines
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DisciplineTemplate:
    """One seeded discipline.

    `ifc_disciplines` is the bridge between the two vocabularies the platform
    grew separately: the four-value `EngineerDiscipline` the organization model
    used, and the discipline names IFC classification produces
    (`STRUCTURAL`, `PLUMBING`, `FIRE_PROTECTION`, `SITE_CIVIL`…). Without it a
    reviewer scoped to "mechanical" can never be matched against a coordination
    finding tagged `PLUMBING`, which is the state of the system today.

    It is also what lets one office model MEP as a single discipline while
    another splits it into Mechanical and Electrical: both resolve to the same
    IFC set, so routing behaves the same either way.
    """

    code: str
    name_en: str
    name_ar: str
    ifc_disciplines: tuple[str, ...]
    #: Legacy `EngineerDiscipline` value this replaces, where one exists.
    legacy_code: str | None = None
    rank: int = 100


DISCIPLINES: tuple[DisciplineTemplate, ...] = (
    DisciplineTemplate("architectural", "Architectural", "معماري",
                       ("ARCHITECTURAL",), "architectural", 10),
    DisciplineTemplate("structural", "Structural", "إنشائي",
                       ("STRUCTURAL",), None, 20),
    # `civil` keeps STRUCTURAL in its IFC set because the retired
    # `normalize_discipline` alias map folded `structural` into `civil`, and
    # existing consultant assignments were written under that assumption.
    DisciplineTemplate("civil", "Civil", "مدني",
                       ("SITE_CIVIL", "STRUCTURAL"), "civil", 30),
    DisciplineTemplate("geotechnical", "Geotechnical", "جيوتقني",
                       ("SITE_CIVIL",), None, 40),
    DisciplineTemplate("mechanical", "Mechanical", "ميكانيكي",
                       ("MECHANICAL", "PLUMBING", "FIRE_PROTECTION"), "mechanical", 50),
    DisciplineTemplate("electrical", "Electrical", "كهربائي",
                       ("ELECTRICAL",), "electrical", 60),
    DisciplineTemplate("plumbing", "Plumbing", "صحي",
                       ("PLUMBING",), None, 70),
    DisciplineTemplate("fire_protection", "Fire Protection", "مكافحة الحريق",
                       ("FIRE_PROTECTION",), None, 80),
    DisciplineTemplate("mep", "MEP", "كهروميكانيك",
                       ("MECHANICAL", "ELECTRICAL", "PLUMBING", "FIRE_PROTECTION"),
                       None, 90),
    DisciplineTemplate("hvac", "HVAC", "تكييف وتهوية",
                       ("MECHANICAL",), None, 100),
    DisciplineTemplate("bim", "BIM", "نمذجة معلومات البناء", (), None, 110),
    DisciplineTemplate("survey", "Surveying", "مساحة", ("SITE_CIVIL",), None, 120),
    DisciplineTemplate("quantity_surveying", "Quantity Surveying", "حصر كميات",
                       (), None, 130),
    DisciplineTemplate("landscape", "Landscape", "تنسيق مواقع",
                       ("SITE_CIVIL",), None, 140),
    DisciplineTemplate("infrastructure", "Infrastructure", "بنية تحتية",
                       ("SITE_CIVIL",), None, 150),
)

DISCIPLINE_BY_CODE: dict[str, DisciplineTemplate] = {
    item.code: item for item in DISCIPLINES
}

#: The alias map that used to live in `consultant_approval_policy` as code.
#: Kept here so a legacy string still resolves to a seeded discipline during
#: backfill; new data goes through the `disciplines` table instead.
LEGACY_DISCIPLINE_ALIASES: dict[str, str] = {
    "architect": "architectural",
    "architecture": "architectural",
    "structure": "structural",
    "mep_mechanical": "mechanical",
    "mep_electrical": "electrical",
    "firefighting": "fire_protection",
}


def discipline_code_for_legacy(value: str | None) -> str | None:
    """Resolve a legacy discipline string onto a seeded discipline code."""
    if not value:
        return None
    normalized = value.strip().lower().replace(" ", "_")
    normalized = LEGACY_DISCIPLINE_ALIASES.get(normalized, normalized)
    return normalized if normalized in DISCIPLINE_BY_CODE else None
