"""The roles and disciplines a consulting office starts with.

Nothing here is a hardcoded role model. These are *templates*: rows the office
gets on day one so the platform is usable before anybody configures anything,
and which an administrator can then rename, re-permission or delete. The
authority is always the `roles` / `role_permissions` tables — this module only
says what to put in them the first time.

## Where the permission sets come from

Each template starts from one of a handful of named base sets — office
administration, project leadership, engineering, the client — adjusted by the
codes it adds or withholds. The sets are written out here, code by code; they
are the platform's own statement of what each kind of role does, not a
derivation from the retired role enum. (They were frozen from that enum's
catalogue defaults when the configurable model replaced it, so no account's
access changed in the move.)

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

from app.core.permission_catalogue import BY_CODE

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


# ---------------------------------------------------------------------------
# Base permission sets
# ---------------------------------------------------------------------------
# What each kind of role does before a template adds or withholds anything.

OFFICE_ADMINISTRATION: frozenset[str] = frozenset({
    "platform.manage_users", "platform.manage_permissions",
    "platform.create_project", "platform.view_all_projects",
    "project.manage_members", "project.edit", "project.manage_reminders",
    "project.delete", "task.view", "task.create", "task.edit",
    "task.update_progress", "task.view_all", "task.review", "schedule.view",
    "schedule.edit", "site_visit.schedule", "issue.create", "issue.resolve",
    "owner_request.create", "owner_request.review", "design_change.propose",
    "cost_validation.review", "ifc.view", "ifc.upload", "ifc.manage_version",
    "document.upload", "ai.view_insights", "ai.review_insight",
    "ai.promote_insight", "org.manage_roles", "org.manage_disciplines",
    "org.manage_settings", "project.manage_parties", "project.invite_external",
    "document.share_external", "project.view_all_disciplines", "ifc.compare",
    "ifc.review_finding", "ifc.review_suggestion", "ifc.download",
    "ifc.manage_link", "document.view", "site_report.view", "issue.view",
    "design_change.view", "client_portal.view", "task.add_note", "task.comment",
    "message.send", "message.send_client", "message.broadcast",
})

PROJECT_LEADERSHIP: frozenset[str] = frozenset({
    "project.manage_members", "project.manage_reminders", "task.view",
    "task.create", "task.edit", "task.update_progress", "task.view_all",
    "task.review", "schedule.view", "schedule.edit", "site_visit.schedule",
    "site_report.submit", "site_report.verify", "issue.create", "issue.resolve",
    "owner_request.create", "owner_request.review", "design_change.propose",
    "cost_validation.review", "ifc.view", "ifc.upload", "ifc.manage_version",
    "document.upload", "ai.view_insights", "ai.review_insight",
    "ai.promote_insight", "project.manage_parties", "project.invite_external",
    "document.share_external", "project.view_all_disciplines",
    "field_evidence.submit", "field_evidence.verify", "ifc.compare",
    "ifc.review_finding", "ifc.review_suggestion", "ifc.download",
    "ifc.manage_link", "document.view", "site_report.view", "issue.view",
    "design_change.view", "task.add_note", "task.comment", "message.send",
    "message.send_client", "message.broadcast",
})

ENGINEERING: frozenset[str] = frozenset({
    "task.view", "task.update_progress", "task.review", "site_visit.schedule",
    "site_report.submit", "issue.create", "owner_request.review",
    "design_change.propose", "cost_validation.review", "design_change.approve",
    "ifc.view", "ifc.upload", "document.upload", "ai.view_insights",
    "ai.review_insight", "ai.promote_insight", "project.view_all_disciplines",
    "field_evidence.submit", "field_evidence.verify", "ifc.compare",
    "ifc.review_finding", "ifc.review_suggestion", "ifc.download",
    "ifc.manage_link", "document.view", "site_report.view", "issue.view",
    "design_change.view", "task.add_note", "task.comment", "message.send",
    "message.send_client",
})

CLIENT: frozenset[str] = frozenset({
    "task.view", "task.view_all", "schedule.view", "owner_request.create",
    "ifc.view", "ai.view_insights", "document.view", "site_report.view",
    "issue.view", "design_change.view", "client_portal.view",
})

#: Accounts migrated from the retired Consultant role. Review and rename.
LEGACY_CONSULTANT_GRANTS: frozenset[str] = frozenset({
    "task.view", "task.view_all", "task.review", "schedule.view", "issue.create",
    "ifc.view", "ai.view_insights", "ai.review_insight", "ifc.compare",
    "ifc.review_finding", "ifc.download", "document.view", "site_report.view",
    "issue.view", "design_change.view", "message.send",
})


@dataclass(frozen=True)
class RoleTemplate:
    """One seeded role."""

    code: str
    name_en: str
    name_ar: str
    scope: str
    is_internal_only: bool
    #: The base set this template starts from (one of the sets above). Empty
    #: means "no permissions at all" — the archived field-staff template.
    base: frozenset[str]
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
    #: Exists to preserve historical attribution: no account may be created
    #: under it and nobody on it may be staffed onto a project.
    is_archived: bool = False
    description: str = ""

    def permissions(self) -> set[str]:
        """The codes this template grants when it is first created."""
        granted = {code for code in self.base if code in BY_CODE}
        granted |= {code for code in self.extra if code in BY_CODE}
        granted -= self.without
        return granted


def _t(code, name_en, name_ar, scope, internal, base, *, extra=(), without=(),
       rank=100, undeletable=False, is_archived=False, description=""):
    return RoleTemplate(
        code, name_en, name_ar, scope, internal, frozenset(base or ()),
        frozenset(extra), frozenset(without), rank, undeletable, is_archived,
        description,
    )


#: Codes a purely drafting/support role should not carry. Reviewing and
#: approving design work is an engineering authority, and a CAD technician or
#: surveyor holding it by default would be the kind of unexamined assumption
#: this redesign exists to remove.
_NO_REVIEW_AUTHORITY = ("task.review", "design_change.approve")


TEMPLATES: tuple[RoleTemplate, ...] = (
    # --- office administration ---------------------------------------------
    _t("org_admin", "Office Administrator", "مدير النظام", SCOPE_ORG, True,
       OFFICE_ADMINISTRATION, rank=10, undeletable=True,
       description="Runs the platform for the office: accounts, roles and permissions."),
    _t("office_director", "General Manager", "المدير العام", SCOPE_BOTH, True,
       OFFICE_ADMINISTRATION, rank=20,
       description="Office-level authority across every project."),
    # `project.delete` is declined explicitly. This template inherits the
    # administrator's catalogue defaults but provisions accounts whose retired
    # role is PROJECT_MANAGER, so `is_admin(user.role)` has always answered
    # False for it and a technical director has never been able to delete a
    # project. Adding an {ADMIN}-default code would have handed them that
    # silently — and no account currently holds this template, so the
    # equivalence gate would have reported zero differences and proved nothing.
    # Whether a technical director *should* be able to delete a project is a
    # product question; this preserves the current answer until it is asked.
    _t("technical_director", "Technical Director", "المدير الفني", SCOPE_BOTH, True,
       OFFICE_ADMINISTRATION,
       without=("platform.manage_users", "platform.manage_permissions", "project.delete"),
       rank=30,
       description="Technical authority across projects, without account administration."),

    # --- project leadership -------------------------------------------------
    _t("project_manager", "Project Manager", "مدير المشروع", SCOPE_BOTH, True,
       PROJECT_LEADERSHIP, rank=40,
       description="Runs a project: team, schedule, tasks and reviews."),

    # --- engineering --------------------------------------------------------
    # Withholds `project.view_all_disciplines` deliberately. This is where retired
    # `external_consultant` accounts land, and the platform narrowed those
    # people's document access to their own discipline. Keeping that narrowing
    # is why the permission is removed here rather than added to the others:
    # their actual access is unchanged, the rule that produces it is simply
    # written down now instead of being inferred from an affiliation string.
    _t("senior_engineer", "Senior Engineer", "مهندس أول", SCOPE_BOTH, True,
       ENGINEERING, without=("project.view_all_disciplines",), rank=50,
       description="Design and review authority within their disciplines."),
    _t("engineer", "Engineer", "مهندس", SCOPE_BOTH, True,
       ENGINEERING, rank=60,
       description="Design, coordination and technical work."),
    _t("site_engineer", "Site Engineer", "مهندس موقع", SCOPE_PROJECT, True,
       ENGINEERING, extra=("field_evidence.submit", "site_report.submit"), rank=70,
       description="Supervises work on site: reports, evidence and observations."),
    _t("bim_engineer", "BIM Engineer", "مهندس نمذجة", SCOPE_BOTH, True,
       ENGINEERING, extra=("ifc.upload", "ifc.manage_version"), rank=80,
       description="Owns the model: revisions, coordination and clash review."),
    _t("cad_technician", "CAD Technician", "فني رسم", SCOPE_BOTH, True,
       ENGINEERING, without=_NO_REVIEW_AUTHORITY, rank=90,
       description="Drawing production and technical drafting."),
    _t("surveyor", "Surveyor", "مساح", SCOPE_BOTH, True,
       ENGINEERING, extra=("field_evidence.submit",), without=_NO_REVIEW_AUTHORITY,
       rank=95,
       description="Setting out, measurement and survey records."),
    _t("document_controller", "Document Controller", "مسؤول الوثائق", SCOPE_BOTH, True,
       ENGINEERING,
       extra=("project.view_all_disciplines", "document.share_external", "document.upload"),
       without=_NO_REVIEW_AUTHORITY, rank=100,
       description="Custody of project documents, revisions and distribution."),
    _t("office_staff", "Administrative Staff", "موظف إداري", SCOPE_ORG, True,
       frozenset(), extra=("task.view",), rank=110,
       description="Office administration. Starts with read access only."),

    # --- external project participants --------------------------------------
    # Every one of these is project-scoped and non-internal. `is_internal_only`
    # is False, which is what lets them be attached to a ProjectParty.
    _t("client_representative", "Client Representative", "ممثل العميل",
       SCOPE_PROJECT, False, CLIENT, rank=200,
       description="The client's contact on this project."),
    _t("contractor_representative", "Main Contractor", "المقاول الرئيسي",
       SCOPE_PROJECT, False, ENGINEERING, rank=210,
       description="The main contractor's engineer on this project."),
    _t("subcontractor_representative", "Subcontractor", "مقاول من الباطن",
       SCOPE_PROJECT, False, ENGINEERING, rank=220,
       description="A subcontractor's engineer on this project."),
    _t("external_reviewer", "External Reviewer", "مراجع خارجي",
       SCOPE_PROJECT, False, ENGINEERING, rank=230,
       description="An outside consultant reviewing work on this project."),

    # --- migration target ---------------------------------------------------
    # Where removed worker accounts land. Zero permissions on purpose: the
    # account survives so its field evidence stays attributable, and it can
    # do nothing. See docs/CONSULTING_OFFICE_REDESIGN.md §7.
    _t("archived_field_staff", "Field Staff (archived)", "عامل ميداني (مؤرشف)",
       SCOPE_ORG, True, frozenset(), rank=900, is_archived=True,
       description="Retained for historical evidence only. Holds no permissions."),
)

BY_CODE_TEMPLATE: dict[str, RoleTemplate] = {item.code: item for item in TEMPLATES}

#: Seeded for accounts migrated from the retired Consultant role by the legacy
#: backfill (`app.db.rbac_backfill`). Review and rename it.
LEGACY_CONSULTANT_TEMPLATE = _t(
    "legacy_consultant", "Consultant (legacy)", "استشاري (سابق)",
    SCOPE_PROJECT, False, LEGACY_CONSULTANT_GRANTS, rank=910,
    description="Migrated from the retired Consultant role. Review and rename it.",
)


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
