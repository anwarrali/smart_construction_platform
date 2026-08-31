"""Configurable roles, disciplines and parties — resolution and seeding.

This module answers three questions and nothing else:

  * what does this role allow (`role_permission_codes`)
  * what does this person hold, here (`resolved_permissions`)
  * who is this person, structurally — office staff or an external party's
    representative, and which disciplines do they cover

It is **not** a second authorization system. `app.services.authorization`
remains the only module the application asks "may they?", and it delegates the
first half of its answer here. Everything after that — administrator overrides,
the inactive-account rule, the project-access rule — still happens there, in
the order it always did.

## The transition, stated plainly

Permissions used to come from a role *enum* through
`permission_catalogue.role_defaults`. They now come from the `roles` /
`role_permissions` tables. Both paths exist while the backfill runs, and the
rule for choosing between them is deliberately not a feature flag:

    a user with `org_role_id` set is resolved from the database;
    a user without one falls back to the catalogue defaults for their
    legacy `User.role`.

A flag would have made the cutover a moment when every unmigrated account
silently lost all access. Keying off the column instead means an account is
migrated exactly when its row says it is, and a half-finished backfill leaves
nobody locked out. `settings.RBAC_REQUIRE_DB_ROLES` turns the fallback into a
hard failure once an operator is satisfied the backfill is complete, and the
contract migration removes the fallback entirely.

## Two rules that configuration cannot override

  * An **external** participant — one whose project membership points at a
    `ProjectParty` — never holds a permission that is not project-scoped. No
    role assignment, override or misconfiguration can give a contractor
    `platform.manage_users`.
  * A role marked `is_internal_only` cannot be assigned to an external member
    at all. The first rule is the runtime backstop for the second.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permission_catalogue import BY_CODE, CATALOGUE, role_defaults
from app.core.role_templates import (
    DISCIPLINES,
    LEGACY_CONSULTANT_TEMPLATE,
    PARTY_CLIENT,
    TEMPLATES,
    RoleTemplate,
    discipline_code_for_legacy,
    template_for_legacy,
)
from app.models.company import Company
from app.models.enums import UserRole, UserStatus
from app.models.project import ProjectMember
from app.models.rbac import (
    Discipline,
    OrganizationMembership,
    ProjectMemberDiscipline,
    ProjectParty,
    Role,
    RolePermission,
    UserDiscipline,
)
from app.models.user import User

#: Permission codes that are meaningless outside a single project. Computed
#: once from the catalogue so the external-participant rule below can never
#: drift from the catalogue's own declaration.
NON_PROJECT_SCOPED: frozenset[str] = frozenset(
    item.code for item in CATALOGUE if not item.project_scoped
)

ADMIN_LOCKED: frozenset[str] = frozenset(
    item.code for item in CATALOGUE if item.admin_locked
)

#: Authority that belongs to the consulting office. An external participant
#: never *inherits* any of it from a role — see `Permission.office_only`.
OFFICE_ONLY: frozenset[str] = frozenset(
    item.code for item in CATALOGUE if item.office_only
)

#: The subset an external participant never holds at all: certification, and
#: the governance of who else gets access. Stripped again after overrides, so
#: a mistake in Access Control cannot become a breach — see
#: `Permission.never_external`.
NEVER_EXTERNAL: frozenset[str] = frozenset(
    item.code for item in CATALOGUE if item.never_external
)


class UnmigratedUser(RuntimeError):
    """Raised when a user has no database role and the fallback is disabled."""


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

def get_role(db: Session, role_id: uuid.UUID | None) -> Role | None:
    if role_id is None:
        return None
    return db.get(Role, role_id)


def role_by_code(db: Session, code: str, organization_id: uuid.UUID | None = None) -> Role | None:
    """An office's own role of this code, or the global template of that code."""
    query = db.query(Role).filter(Role.code == code)
    if organization_id is not None:
        own = query.filter(Role.organization_id == organization_id).first()
        if own is not None:
            return own
    return query.filter(Role.organization_id.is_(None)).first()


def role_permission_codes(db: Session, role_id: uuid.UUID | None) -> set[str]:
    """Permissions this role grants. Unknown codes are dropped, never trusted."""
    if role_id is None:
        return set()
    rows = db.query(RolePermission).filter(
        RolePermission.role_id == role_id, RolePermission.allowed.is_(True),
    ).all()
    return {row.permission_code for row in rows if row.permission_code in BY_CODE}


def set_role_permission(
    db: Session, *, role: Role, code: str, allowed: bool | None
) -> None:
    """Grant, deny or clear one permission on a role.

    `allowed=None` removes the row, which for a role means "does not hold it" —
    a role's stored rows are the whole truth about it, so absence and an
    explicit denial mean the same thing at resolution time. The distinction is
    kept because an administrator who deliberately switched something off
    should see that, rather than a blank.
    """
    row = db.query(RolePermission).filter(
        RolePermission.role_id == role.id, RolePermission.permission_code == code,
    ).first()
    if allowed is None:
        if row is not None:
            db.delete(row)
        return
    if row is None:
        db.add(RolePermission(role_id=role.id, permission_code=code, allowed=allowed))
    else:
        row.allowed = allowed


# ---------------------------------------------------------------------------
# Membership shape
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MembershipContext:
    """How a person relates to one project, structurally."""

    member: ProjectMember | None
    party: ProjectParty | None

    @property
    def is_member(self) -> bool:
        return self.member is not None

    @property
    def is_external(self) -> bool:
        """True when this person takes part on behalf of an outside party."""
        return self.party is not None

    @property
    def is_site_engineer(self) -> bool:
        return bool(self.member and self.member.is_site_engineer)


def membership_context(
    db: Session, user_id: uuid.UUID, project_id: uuid.UUID | None
) -> MembershipContext:
    if project_id is None:
        return MembershipContext(None, None)
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
        ProjectMember.is_active.is_(True),
    ).first()
    if member is None:
        return MembershipContext(None, None)
    party = db.get(ProjectParty, member.party_id) if member.party_id else None
    return MembershipContext(member, party)


def is_external_participant(db: Session, user: User, project_id: uuid.UUID | None) -> bool:
    """Whether this person is on the project for an outside party.

    Two sources, and the order matters. A membership that points at a
    `ProjectParty` is decisive — it is a statement about this project, made by
    whoever added them. Failing that, the account's own `is_internal` flag
    answers for contexts with no project.

    `is_internal` is only consulted for an account the backfill has reached.
    Before that it is an unset column, not a claim, and reading it as one would
    make every unmigrated user look like an outsider and strip their office-wide
    permissions — the platform had no external participants before this
    redesign, so "not yet decided" resolves to staff.
    """
    if project_id is not None and membership_context(db, user.id, project_id).is_external:
        return True
    if user.org_role_id is None:
        # Pre-backfill, the only externality signal a row carries is the
        # retired affiliation. Reading it here is what stops the migration
        # window from being a period in which a contractor's engineer could
        # approve the office's design changes. `is_internal` is not consulted
        # because it has not been decided for this account yet.
        return user.engineer_affiliation == "main_contractor"
    return not bool(user.is_internal)


# ---------------------------------------------------------------------------
# Effective permissions
# ---------------------------------------------------------------------------

def is_client_participant(db: Session, user: User, project_id: uuid.UUID | None) -> bool:
    """Whether this person is on this project as the client.

    The client portal's audience, asked as a *relationship* rather than as an
    identity. `UserRole.OWNER` was the identity, and it could not answer the
    questions a consulting office actually has: an office may have several
    client contacts on one project, the same person may be the client on one
    project and nothing on another, and a client is an external party whose
    access hangs off `ProjectParty` like any other.

    Two sources, and the order matters — the same order and the same reason as
    `is_external_participant`. A membership pointing at a `ProjectParty` of
    kind CLIENT is decisive: it is a statement about this project. Failing
    that, an account the backfill has not reached carries only its retired
    role, so that answers until the row is migrated. `rbac_backfill` creates
    the client party and attaches the owner's membership to it, so the bridge
    is for the migration window only and goes with the contract step.

    Deliberately *not* a permission. What the client may see is
    `client_portal.view` and the document scope; this is which *rows* the
    client rule narrows to, which is a question about who somebody is on a
    project, not about what they are allowed to do.
    """
    if project_id is not None:
        context = membership_context(db, user.id, project_id)
        if context.is_external and context.party is not None:
            return context.party.kind == PARTY_CLIENT
        if context.member is not None:
            # On the project as office staff. Whatever the retired column says,
            # they are not the client here.
            return False
    return False


#: Roles that exist to hold history rather than to be worked under. A role with
#: no `legacy_role` is one the platform refuses to create accounts under
#: (`user_service.legacy_role_for`), and that is the same predicate as "nobody
#: may be staffed onto a project under it" — today that is exactly the archived
#: field-staff role retired worker accounts sit on.
def _archived_role_ids(db: Session):
    return db.query(Role.id).filter(Role.legacy_role.is_(None)).scalar_subquery()


def staffable_filter(db: Session):
    """SQL condition for "this account may be put on a project".

    Active, and not parked on a role that exists only to hold history. It used
    to read `User.role.in_([ENGINEER, CONSULTANT])`, which is the assumption a
    configurable office cannot carry: an office that wants its General Manager
    or its Document Controller on a project had no way to say so, because
    neither is one of two retired enum values.

    The `WORKER` clause is the pre-backfill bridge — an account the backfill has
    not reached carries no role row, so the retired column is the only signal
    that it is a retired worker. It goes with the contract step.
    """
    return and_(
        User.status == UserStatus.ACTIVE,
        ~User.org_role_id.in_(_archived_role_ids(db)),
    )


def is_staffable(db: Session, user: User) -> bool:
    """The row-level form of `staffable_filter`, for an account already loaded."""
    if user.status != UserStatus.ACTIVE:
        return False
    role = get_role(db, user.org_role_id)
    return bool(role is not None and role.legacy_role)


def resolved_permissions(
    db: Session, user: User, project_id: uuid.UUID | None = None
) -> set[str]:
    """Everything the person's roles grant, before administrator overrides.

    The union of the office role and the project role. Union rather than
    replacement, because "Senior Engineer in the office, Project Manager on
    this job" has to mean both — the previous model could not express it at
    all, since a project role was required to equal the global one.

    Narrowing is still possible and still happens after this, through
    `UserPermissionOverride`, which `app.services.authorization` applies.
    """
    if user.org_role_id is None:
        # No fallback any more. An account without a role is a bug — the
        # backstop fills the column for anything created without one, and the
        # backfill reached everything that predates it — so resolving one
        # through the retired enum would be guessing at authority rather than
        # reading it. Failing loudly is the point of the contract step.
        raise UnmigratedUser(
            f"User {user.id} has no org_role_id. Run app.db.rbac_backfill."
        )
    granted = role_permission_codes(db, user.org_role_id)

    context = membership_context(db, user.id, project_id)
    if context.member is not None and context.member.project_role_id is not None:
        granted |= role_permission_codes(db, context.member.project_role_id)

    if context.is_external or (user.org_role_id is not None and not user.is_internal):
        # What a *role* confers. An external participant's authority is
        # confined to the projects they were added to, and a role never carries
        # the office's own job into an outside firm — whatever the role says.
        #
        # This is the whole `office_only` set, not just the locked subset,
        # because inheritance is where a mistake is silent: the seeded
        # contractor template inherits an Engineer's permissions, and an office
        # renaming or re-permissioning a role should never quietly hand a
        # contractor authority nobody decided to give them. Deliberate
        # delegation is a different act, and it happens through an override —
        # see `authorization.effective_permissions`.
        granted -= NON_PROJECT_SCOPED
        granted -= OFFICE_ONLY

    role = get_role(db, user.org_role_id)
    if role is not None and role.undeletable:
        # The office administrator cannot be configured out of administering.
        granted |= ADMIN_LOCKED

    return granted


def disciplines_for_user(db: Session, user_id: uuid.UUID) -> list[Discipline]:
    """The disciplines this person practises.

    Falls back to the retired single-valued `EngineerProfile.discipline` for an
    account the backfill has not reached. Without that bridge a consultant
    reviewer would lose their discipline narrowing during the migration window
    — the narrowing is what keeps them out of other specialisms' documents, so
    losing it silently would be a widening, not a degradation.
    """
    rows = db.query(UserDiscipline).filter(UserDiscipline.user_id == user_id).all()
    held = [row.discipline for row in rows if row.discipline is not None]
    if held:
        return held

    from app.models.user import EngineerProfile

    profile = db.query(EngineerProfile).filter(
        EngineerProfile.user_id == user_id
    ).first()
    if profile is None or profile.discipline is None:
        return []
    legacy = db.query(Discipline).filter(
        Discipline.legacy_code == profile.discipline.value,
        Discipline.organization_id.is_(None),
    ).first()
    return [legacy] if legacy is not None else []


def disciplines_for_member(
    db: Session, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[Discipline]:
    """The disciplines this person covers on this project.

    Falls back to everything they practise when the project assignment does not
    name any, so an office that never uses per-project disciplines behaves as
    though the person brought their whole profile.
    """
    context = membership_context(db, user_id, project_id)
    if context.member is not None:
        rows = db.query(ProjectMemberDiscipline).filter(
            ProjectMemberDiscipline.project_member_id == context.member.id,
        ).all()
        chosen = [row.discipline for row in rows if row.discipline is not None]
        if chosen:
            return chosen
    return disciplines_for_user(db, user_id)


def discipline_codes(disciplines: list[Discipline]) -> set[str]:
    return {item.code for item in disciplines}


def ifc_discipline_names(disciplines: list[Discipline]) -> set[str]:
    """IFC classification names these disciplines cover.

    The join that makes a person scoped to `mep` match a coordination finding
    tagged `PLUMBING`. Before this, the organization vocabulary and the IFC
    vocabulary had no relationship and such a match was impossible.
    """
    names: set[str] = set()
    for item in disciplines:
        names.update(str(value).upper() for value in (item.ifc_disciplines or []))
    return names


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def seed_disciplines(db: Session) -> dict[str, Discipline]:
    """Create the shared discipline list. Idempotent."""
    existing = {
        row.code: row
        for row in db.query(Discipline).filter(Discipline.organization_id.is_(None)).all()
    }
    for template in DISCIPLINES:
        row = existing.get(template.code)
        if row is None:
            row = Discipline(
                organization_id=None,
                code=template.code,
                name_en=template.name_en,
                name_ar=template.name_ar,
                ifc_disciplines=list(template.ifc_disciplines),
                legacy_code=template.legacy_code,
                rank=template.rank,
            )
            db.add(row)
            existing[template.code] = row
        else:
            # Refresh the derived mapping without touching a renamed label:
            # an office may have renamed the discipline, and re-seeding must
            # not undo that.
            row.ifc_disciplines = list(template.ifc_disciplines)
            row.legacy_code = template.legacy_code
    db.flush()
    return existing


def seed_roles(
    db: Session,
    *,
    organization_id: uuid.UUID | None = None,
    include_legacy_consultant: bool = False,
    role_overrides: dict[UserRole, dict[str, bool]] | None = None,
) -> dict[str, Role]:
    """Create the role templates and their permissions. Idempotent.

    `role_overrides` carries whatever an administrator had configured on the
    retired `RolePermissionOverride` table, keyed by the legacy role. Those
    decisions are folded into every template that inherits from that role, so
    configuration made before the redesign survives it — which is also what
    keeps the equivalence gate empty for an office that had customised its
    permissions.
    """
    overrides = role_overrides or {}
    # `legacy_consultant` is seeded unconditionally. It used to be opt-in, and
    # that was a hole: `template_for_legacy` maps `UserRole.CONSULTANT` onto it,
    # so without the row there is no role for such an account to migrate to —
    # `template_role_for_legacy_user` returns None, the backfill skips it, and
    # under `RBAC_REQUIRE_DB_ROLES` the account cannot resolve at all. No *new*
    # account is ever CONSULTANT (`UserCreateByAdmin` rewrites it), but rows
    # from before the redesign exist, and a mapping that only works when the
    # caller remembers a keyword argument is not a mapping.
    #
    # `include_legacy_consultant` is kept so existing callers do not break; it
    # no longer changes anything.
    templates: list[RoleTemplate] = [*TEMPLATES, LEGACY_CONSULTANT_TEMPLATE]

    query = db.query(Role)
    query = (
        query.filter(Role.organization_id == organization_id)
        if organization_id is not None
        else query.filter(Role.organization_id.is_(None))
    )
    existing = {row.code: row for row in query.all()}

    result: dict[str, Role] = {}
    for template in templates:
        role = existing.get(template.code)
        if role is None:
            role = Role(
                organization_id=organization_id,
                code=template.code,
                name_en=template.name_en,
                name_ar=template.name_ar,
                description=template.description,
                scope=template.scope,
                is_internal_only=template.is_internal_only,
                is_system=True,
                undeletable=template.undeletable,
                rank=template.rank,
                legacy_role=template.legacy_role,
                legacy_affiliation=template.legacy_affiliation,
            )
            db.add(role)
            db.flush()
        elif role.legacy_role is None and template.legacy_role is not None:
            # A row seeded before the provisioning columns existed. Filling it
            # here means a deployment that re-seeds gets the same answer the
            # migration wrote, so the two can never disagree.
            role.legacy_role = template.legacy_role
            role.legacy_affiliation = template.legacy_affiliation
        result[template.code] = role

        codes = template.permissions()
        for code, allowed in overrides.get(template.inherits, {}).items():
            if code not in BY_CODE:
                continue
            codes.add(code) if allowed else codes.discard(code)

        held = {
            row.permission_code: row
            for row in db.query(RolePermission).filter(
                RolePermission.role_id == role.id
            ).all()
        }
        for code in codes:
            row = held.get(code)
            if row is None:
                db.add(RolePermission(role_id=role.id, permission_code=code, allowed=True))
            else:
                row.allowed = True
        # Re-seeding never *removes* a permission an administrator added on
        # purpose; it only ensures the template's own set is present. Removing
        # is an explicit action through the access-control API.
    db.flush()
    return result


def ensure_tenant_organization(db: Session, *, name: str | None = None) -> Company:
    """The consulting office this deployment belongs to.

    Picks the existing tenant if one is marked, otherwise promotes the office
    the platform administrator already belongs to, otherwise creates one. There
    is deliberately no path that promotes an arbitrary company: guessing which
    of several rows is the office would be worse than asking.
    """
    tenant = db.query(Company).filter(Company.is_tenant.is_(True)).first()
    if tenant is not None:
        return tenant

    admin = (
        db.query(User)
        .filter(User.role == UserRole.ADMIN, User.company_id.isnot(None))
        .order_by(User.created_at.asc())
        .first()
    )
    if admin is not None:
        tenant = db.get(Company, admin.company_id)
        if tenant is not None:
            tenant.is_tenant = True
            tenant.kind = "CONSULTING_OFFICE"
            db.flush()
            return tenant

    tenant = Company(
        name=name or "Consulting Office",
        kind="CONSULTING_OFFICE",
        is_tenant=True,
        is_active=True,
    )
    db.add(tenant)
    db.flush()
    return tenant


# ---------------------------------------------------------------------------
# Assignment helpers used by the API and the backfill
# ---------------------------------------------------------------------------

def assign_org_role(
    db: Session, *, user: User, role: Role, organization_id: uuid.UUID,
    job_title: str | None = None,
) -> OrganizationMembership:
    """Give somebody an office role, and record the membership behind it."""
    user.org_role_id = role.id
    user.is_internal = bool(role.is_internal_only)
    membership = db.query(OrganizationMembership).filter(
        OrganizationMembership.user_id == user.id,
        OrganizationMembership.organization_id == organization_id,
    ).first()
    if membership is None:
        membership = OrganizationMembership(
            user_id=user.id, organization_id=organization_id, role_id=role.id,
            job_title=job_title,
        )
        db.add(membership)
    else:
        membership.role_id = role.id
        membership.is_active = True
        if job_title is not None:
            membership.job_title = job_title
    db.flush()
    return membership


def set_user_disciplines(
    db: Session, *, user: User, discipline_ids: list[uuid.UUID], primary_id: uuid.UUID | None = None
) -> None:
    """Replace the disciplines a person practises."""
    wanted = set(discipline_ids)
    for row in db.query(UserDiscipline).filter(UserDiscipline.user_id == user.id).all():
        if row.discipline_id not in wanted:
            db.delete(row)
        else:
            row.is_primary = row.discipline_id == primary_id
            wanted.discard(row.discipline_id)
    for discipline_id in wanted:
        db.add(UserDiscipline(
            user_id=user.id, discipline_id=discipline_id,
            is_primary=discipline_id == primary_id,
        ))
    db.flush()


def resolve_discipline(
    db: Session, value: str | None, organization_id: uuid.UUID | None = None
) -> Discipline | None:
    """Find a discipline from a code or a legacy string."""
    if not value:
        return None
    code = discipline_code_for_legacy(value) or value.strip().lower().replace(" ", "_")
    query = db.query(Discipline).filter(
        Discipline.code == code,
        or_(
            Discipline.organization_id.is_(None),
            Discipline.organization_id == organization_id,
        ) if organization_id is not None else Discipline.organization_id.is_(None),
    )
    return query.order_by(Discipline.organization_id.nullslast()).first()


def template_role_for_legacy_user(db: Session, user: User) -> Role | None:
    """The seeded role an existing account migrates onto."""
    template = template_for_legacy(user.role, user.engineer_affiliation)
    return role_by_code(db, template.code, user.company_id)


def role_label_for(db: Session, user: User) -> str:
    """The office's own name for this person's role.

    Used where something needs to *describe* somebody — an AI prompt, an
    audit line, a directory listing. Deliberately the configured name rather
    than a code, because a role called "Resident Engineer" is more useful to a
    language model than a stable identifier it has never seen, and the office
    chose that word for a reason.

    Falls back to the retired enum for an account the backfill has not reached.

    Reads its inputs with `getattr` because this is a *label*, not a decision:
    it is called from prompt assembly and logging, where being handed a partial
    object should produce a duller string rather than an exception. Nothing in
    `resolved_permissions` is written this way — an authorization check that
    shrugged at a missing column would be exactly the wrong kind of tolerant.
    """
    role = get_role(db, getattr(user, "org_role_id", None))
    if role is not None:
        return role.name_en
    legacy = getattr(user, "role", None)
    return legacy.value if legacy is not None else "unknown"


def active_users_missing_roles(db: Session) -> int:
    """How many live accounts the backfill has not reached. Zero means done."""
    return (
        db.query(User)
        .filter(User.org_role_id.is_(None), User.status == UserStatus.ACTIVE)
        .count()
    )
