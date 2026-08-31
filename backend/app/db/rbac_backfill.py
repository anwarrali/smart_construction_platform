"""Move existing accounts and projects onto the configurable role model.

Idempotent and re-runnable: every step looks for what it would create before
creating it, so an interrupted run is resumed by running it again rather than
by cleaning up after it.

Nothing is deleted. The retired `User.role`, `ProjectMember.role_on_project`
and `engineer_affiliation` columns are left exactly as they are — this fills in
the new columns beside them. That is what makes the run reversible in practice
as well as on paper: until the contract migration drops those columns, the
legacy resolution still works and `app.db.rbac_equivalence` can compare the two.

## The two places this deliberately does not do the literal thing

**External consultants become office staff.** An `external_consultant` account
is the reviewing side of the old owner/contractor/consultant triangle, and in
the new product the consulting office *is* the reviewer. Migrating them to an
outside party would have put the office's own reviewers behind deny-by-default
external document scoping. See `LEGACY_ROLE_MAP` in `app.core.role_templates`.

**Contractor access is preserved explicitly rather than by default.** Main
contractor engineers become external participants, and external participants
only read documents that were explicitly shared with their party. Applied
naively that would silently revoke document access those people have today, so
this backfill writes the shares that reproduce it. New documents are
deny-by-default from here on; existing access is carried over as visible,
auditable rows rather than as an invisible rule.

Run it with:

    python -m app.db.rbac_backfill            # apply
    python -m app.db.rbac_backfill --dry-run  # report only
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

import app.models  # noqa: F401  - configure all SQLAlchemy relationships
from app.core.role_templates import (
    discipline_code_for_legacy,
    PARTY_CLIENT,
    PARTY_CONSULTANT,
    PARTY_MAIN_CONTRACTOR,
    template_for_legacy,
)
from app.db.database import SessionLocal
from app.models.company import Company
from app.models.document import Document
from app.models.enums import UserRole
from app.models.permission import RolePermissionOverride
from app.models.project import Project, ProjectMember
from app.models.rbac import (
    Discipline,
    DocumentPartyShare,
    ProjectMemberDiscipline,
    ProjectParty,
    Role,
    UserDiscipline,
)
from app.models.user import EngineerProfile, User
from app.services import rbac

#: Affiliations that describe somebody working for the main contractor. These
#: are the accounts that become external project participants.
CONTRACTOR_AFFILIATIONS = frozenset({"main_contractor"})


@dataclass
class BackfillReport:
    tenant_name: str = ""
    roles_seeded: int = 0
    disciplines_seeded: int = 0
    users_mapped: int = 0
    users_by_role: dict = field(default_factory=lambda: defaultdict(int))
    user_disciplines: int = 0
    memberships: int = 0
    project_roles: int = 0
    member_disciplines: int = 0
    parties_created: int = 0
    members_attached_to_party: int = 0
    document_shares: int = 0
    workers_archived: int = 0
    organizations_classified: int = 0
    unmapped_users: list = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "RBAC backfill",
            f"  consulting office        : {self.tenant_name}",
            f"  organizations classified : {self.organizations_classified}",
            f"  roles seeded             : {self.roles_seeded}",
            f"  disciplines seeded       : {self.disciplines_seeded}",
            f"  users given an office role: {self.users_mapped}",
        ]
        for code in sorted(self.users_by_role):
            lines.append(f"      {code:<28} {self.users_by_role[code]}")
        lines += [
            f"  office memberships       : {self.memberships}",
            f"  user disciplines         : {self.user_disciplines}",
            f"  project roles assigned   : {self.project_roles}",
            f"  member disciplines       : {self.member_disciplines}",
            f"  project parties created  : {self.parties_created}",
            f"  members attached to party: {self.members_attached_to_party}",
            f"  document shares written  : {self.document_shares}",
            f"  worker accounts archived : {self.workers_archived}",
        ]
        if self.unmapped_users:
            lines.append(f"  UNMAPPED USERS           : {len(self.unmapped_users)}")
            for item in self.unmapped_users[:20]:
                lines.append(f"      {item}")
        return "\n".join(lines)


def _legacy_role_overrides(db: Session) -> dict[UserRole, dict[str, bool]]:
    """Whatever an administrator had configured, keyed by the legacy role.

    Folded into every template that inherits from that role, so a permission an
    office had switched on or off before the redesign is still on or off after
    it. Without this the equivalence gate would fail on any installation that
    had ever used Access Control.
    """
    result: dict[UserRole, dict[str, bool]] = defaultdict(dict)
    for row in db.query(RolePermissionOverride).all():
        result[row.role][row.permission_code] = row.allowed
    return result


def _classify_organizations(db: Session, tenant: Company, report: BackfillReport) -> None:
    """Give every pre-redesign company row a kind.

    A company is classified by what its people did, because that is the only
    evidence the old model left. This is a label, not a hierarchy: nothing
    joins one organization to another, and a contractor row here is never how
    a contractor takes part in a project.
    """
    for company in db.query(Company).all():
        if company.id == tenant.id:
            if company.kind != "CONSULTING_OFFICE" or not company.is_tenant:
                company.kind = "CONSULTING_OFFICE"
                company.is_tenant = True
                report.organizations_classified += 1
            continue
        if company.kind != "OTHER":
            continue  # already classified by an earlier run
        affiliations = {
            value for (value,) in db.query(User.engineer_affiliation)
            .filter(User.company_id == company.id).all()
        }
        roles = {
            value for (value,) in db.query(User.role)
            .filter(User.company_id == company.id).all()
        }
        if affiliations & CONTRACTOR_AFFILIATIONS or UserRole.WORKER in roles:
            company.kind = "CONTRACTOR"
        elif roles == {UserRole.OWNER}:
            company.kind = "CLIENT"
        else:
            company.kind = "OTHER"
        report.organizations_classified += 1


def _map_users(
    db: Session, tenant: Company, roles: dict[str, Role], report: BackfillReport
) -> None:
    for user in db.query(User).all():
        if user.org_role_id is not None:
            continue
        template = template_for_legacy(user.role, user.engineer_affiliation)
        role = roles.get(template.code)
        if role is None:
            report.unmapped_users.append(f"{user.email} ({user.role}/{user.engineer_affiliation})")
            continue
        # The person's office. `company_id` is where the old model recorded
        # who they worked for; when it is missing they join the tenant, which
        # is the only office this deployment has.
        organization_id = user.company_id or tenant.id
        rbac.assign_org_role(
            db, user=user, role=role, organization_id=organization_id,
            job_title=role.name_en,
        )
        report.users_mapped += 1
        report.memberships += 1
        report.users_by_role[template.code] += 1
        if user.role == UserRole.WORKER:
            report.workers_archived += 1


def _map_user_disciplines(
    db: Session, disciplines: dict[str, Discipline], report: BackfillReport
) -> None:
    """`EngineerProfile.discipline` becomes a row in the many-to-many table.

    Read from the profile rather than from a normalized alias, because the
    alias map was lossy — it folded `structural` into `civil` and `hvac` into
    `mechanical` — and a backfill that inherited that loss would make the new
    model no better than the enum it replaces.
    """
    for profile in db.query(EngineerProfile).all():
        if profile.discipline is None:
            continue
        discipline = disciplines.get(profile.discipline.value)
        if discipline is None:
            continue
        held = db.query(UserDiscipline).filter(
            UserDiscipline.user_id == profile.user_id,
            UserDiscipline.discipline_id == discipline.id,
        ).first()
        if held is not None:
            continue
        db.add(UserDiscipline(
            user_id=profile.user_id, discipline_id=discipline.id, is_primary=True,
        ))
        report.user_disciplines += 1


def _party_name_for(user: User, fallback: str) -> str:
    """The best available name for the firm somebody works for."""
    return (user.organization or "").strip() or fallback


def _ensure_party(
    db: Session, *, project: Project, kind: str, name: str, report: BackfillReport,
    is_primary: bool = False, created_by_id=None,
) -> ProjectParty:
    party = db.query(ProjectParty).filter(
        ProjectParty.project_id == project.id,
        ProjectParty.kind == kind,
        ProjectParty.display_name == name,
    ).first()
    if party is None:
        party = ProjectParty(
            project_id=project.id, kind=kind, display_name=name,
            is_primary=is_primary, created_by_id=created_by_id,
        )
        db.add(party)
        db.flush()
        report.parties_created += 1
    return party


def _map_projects(
    db: Session, tenant: Company, roles: dict[str, Role],
    disciplines: dict[str, Discipline], report: BackfillReport,
) -> None:
    for project in db.query(Project).all():
        # Every project belongs to the office. A project with no company was
        # possible before; it is not a meaningful state now.
        if project.company_id is None:
            project.company_id = tenant.id

        members = db.query(ProjectMember).filter(
            ProjectMember.project_id == project.id
        ).all()

        # --- the client -----------------------------------------------------
        client_party = None
        if project.owner_id:
            owner = db.get(User, project.owner_id)
            if owner is not None:
                client_party = _ensure_party(
                    db, project=project, kind=PARTY_CLIENT,
                    name=_party_name_for(owner, owner.full_name or "Client"),
                    report=report, is_primary=True,
                )

        # --- contractors, grouped by the firm each person names -------------
        contractor_parties: dict[str, ProjectParty] = {}
        consultant_parties: dict[str, ProjectParty] = {}
        for member in members:
            user = db.get(User, member.user_id)
            if user is None:
                continue
            if user.engineer_affiliation in CONTRACTOR_AFFILIATIONS:
                name = _party_name_for(user, "Main Contractor")
                if name not in contractor_parties:
                    contractor_parties[name] = _ensure_party(
                        db, project=project, kind=PARTY_MAIN_CONTRACTOR, name=name,
                        report=report, is_primary=not contractor_parties,
                    )
            elif user.role == UserRole.WORKER:
                # Worker accounts belonged to the contractor. They are archived
                # and hold nothing, but attaching them to the party keeps the
                # historical picture of the project honest.
                name = _party_name_for(user, "Main Contractor")
                if name not in contractor_parties:
                    contractor_parties[name] = _ensure_party(
                        db, project=project, kind=PARTY_MAIN_CONTRACTOR, name=name,
                        report=report, is_primary=not contractor_parties,
                    )

        # --- project roles, parties and disciplines per member --------------
        for member in members:
            user = db.get(User, member.user_id)
            if user is None:
                continue

            if member.project_role_id is None:
                # Derived from the *person*, not from `role_on_project`.
                #
                # `role_on_project` looks like the obvious source and is the
                # wrong one. The old `add_project_member` required it to equal
                # the user's global role, so it never carried authority of its
                # own — with a single exception: an external-consultant
                # Engineer was stored as `role_on_project=CONSULTANT`. Mapping
                # that value literally would hand them the retired CONSULTANT
                # role's defaults, which include `schedule.view` — a permission
                # an Engineer does not hold. The migration would then have
                # granted portfolio schedule access to every consultant
                # engineer on every project, silently.
                #
                # Deriving from the person instead guarantees the project role
                # is a subset of the office role, so the union in
                # `rbac.resolved_permissions` cannot widen anybody. The
                # site-engineer flag is the one genuine project-level
                # distinction, and it maps to a template with the same
                # permissions plus the field-evidence codes it already had.
                if member.is_site_engineer and user.role == UserRole.ENGINEER:
                    template_code = "site_engineer"
                else:
                    template_code = template_for_legacy(
                        user.role, user.engineer_affiliation
                    ).code
                role = roles.get(template_code)
                if role is not None:
                    member.project_role_id = role.id
                    report.project_roles += 1

            # Office staff are never attached to an external party, whatever
            # else is true of them. A project manager who also happens to be
            # recorded as the project's `owner_id` is still office staff, and
            # attaching them to the client party would make them external —
            # stripping the review and management authority their job needs.
            role_is_internal = bool(
                db.get(Role, user.org_role_id).is_internal_only
                if user.org_role_id else True
            )
            if member.party_id is not None and role_is_internal:
                # Repair a row an earlier run attached before this rule existed.
                member.party_id = None

            if member.party_id is None and not role_is_internal:
                if user.id == project.owner_id or member.role_on_project == UserRole.OWNER:
                    if client_party is not None:
                        member.party_id = client_party.id
                        report.members_attached_to_party += 1
                elif (
                    user.engineer_affiliation in CONTRACTOR_AFFILIATIONS
                    or user.role == UserRole.WORKER
                ):
                    name = _party_name_for(user, "Main Contractor")
                    party = contractor_parties.get(name)
                    if party is not None:
                        member.party_id = party.id
                        report.members_attached_to_party += 1

            if member.project_discipline:
                code = discipline_code_for_legacy(member.project_discipline)
                discipline = disciplines.get(code) if code else None
                if discipline is not None:
                    held = db.query(ProjectMemberDiscipline).filter(
                        ProjectMemberDiscipline.project_member_id == member.id,
                        ProjectMemberDiscipline.discipline_id == discipline.id,
                    ).first()
                    if held is None:
                        db.add(ProjectMemberDiscipline(
                            project_member_id=member.id, discipline_id=discipline.id,
                        ))
                        report.member_disciplines += 1

        # --- preserve the document access contractors already had -----------
        # Deny-by-default is the rule from here on. Applying it retroactively
        # would revoke access silently, so what they could read today is
        # written down as explicit shares instead.
        if contractor_parties or consultant_parties:
            document_ids = [
                row[0] for row in db.query(Document.id).filter(
                    Document.project_id == project.id
                ).all()
            ]
            for party in list(contractor_parties.values()) + list(consultant_parties.values()):
                existing = {
                    row[0] for row in db.query(DocumentPartyShare.document_id).filter(
                        DocumentPartyShare.party_id == party.id
                    ).all()
                }
                for document_id in document_ids:
                    if document_id in existing:
                        continue
                    db.add(DocumentPartyShare(
                        document_id=document_id, party_id=party.id,
                        note="Carried over from pre-redesign project-wide access.",
                    ))
                    report.document_shares += 1

    db.flush()


def run(db: Session, *, dry_run: bool = False, commit: bool = True) -> BackfillReport:
    """Apply the backfill.

    `commit=False` leaves the work in the caller's open transaction instead of
    writing it. Tests use it to build a world, migrate it and assert on the
    result without touching the shared development database.
    """
    report = BackfillReport()

    tenant = rbac.ensure_tenant_organization(db)
    report.tenant_name = tenant.name
    _classify_organizations(db, tenant, report)

    disciplines = rbac.seed_disciplines(db)
    report.disciplines_seeded = len(disciplines)

    needs_legacy_consultant = db.query(User).filter(
        User.role == UserRole.CONSULTANT
    ).first() is not None
    roles = rbac.seed_roles(
        db,
        include_legacy_consultant=needs_legacy_consultant,
        role_overrides=_legacy_role_overrides(db),
    )
    report.roles_seeded = len(roles)

    _map_users(db, tenant, roles, report)
    _map_user_disciplines(db, disciplines, report)
    _map_projects(db, tenant, roles, disciplines, report)

    if dry_run:
        db.rollback()
    elif commit:
        db.commit()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill the configurable RBAC model.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change and roll back.")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        report = run(db, dry_run=args.dry_run)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(report.render())
    if args.dry_run:
        print("\n(dry run — nothing was written)")
    if report.unmapped_users:
        print("\nSome accounts could not be mapped. Nothing was skipped silently.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
