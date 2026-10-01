"""Move a database from the retired role model onto the configurable one.

**For a legacy database only.** A fresh deployment never needs this:
`bootstrap_admin` seeds the role templates before it creates the first
administrator (`rbac.seed_fresh_database`). This exists for one situation — a
database whose accounts still describe people by the retired six-value
`users.role` enum and `engineer_affiliation` strings, and have no office role.

It must run **before** the migration that removes those columns
(`e1a9c3d5f720`), which refuses to proceed while any account lacks an office
role. The order for such a database is:

    alembic upgrade c84d6e2f1a37        # the last revision with the legacy columns
    python -m app.db.rbac_backfill      # this
    alembic upgrade head                # removes the legacy schema

The legacy values are read with raw SQL — the ORM no longer maps the columns —
and the run refuses, without changing anything, on a database that has no such
columns (already migrated) or no accounts at all (fresh).

Idempotent and re-runnable: every step looks for what it would create before
creating it. Everything happens in one transaction; any failure rolls the
whole run back. An `engineer_affiliation` the platform does not recognise
fails the run (`UnknownAffiliation`) rather than guessing a role: guessing
high would hand an outsider internal access, guessing low would silently strip
a legitimate account. Fix the row and run again.

## The two places this deliberately does not do the literal thing

**External consultants become office staff.** An `external_consultant` account
is the reviewing side of the old owner/contractor/consultant triangle, and the
consulting office *is* the reviewer. See `app.db.legacy_rbac.LEGACY_ROLE_MAP`.

**Contractor access is preserved explicitly rather than by default.** Main
contractor engineers become external participants, and external participants
only read documents that were explicitly shared with their party. Applied
naively that would silently revoke document access those people had, so this
backfill writes the shares that reproduce it.

Run it with:

    python -m app.db.rbac_backfill            # apply
    python -m app.db.rbac_backfill --dry-run  # report only
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

import app.models  # noqa: F401  - configure all SQLAlchemy relationships
from app.core.role_templates import (
    PARTY_CLIENT,
    PARTY_CONSULTANT,
    PARTY_MAIN_CONTRACTOR,
    discipline_code_for_legacy,
)
from app.db.database import SessionLocal
from app.db.legacy_rbac import (
    CONTRACTOR_AFFILIATIONS,
    LEGACY_INHERITS,
    template_for_legacy,
)
from app.models.company import Company
from app.models.document import Document
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


class NothingToBackfill(Exception):
    """The database holds nothing in the retired model; no change was made."""


@dataclass(frozen=True)
class LegacyAccount:
    role: str
    affiliation: str | None


@dataclass
class LegacySnapshot:
    """The retired columns, read once with raw SQL."""

    accounts: dict[uuid.UUID, LegacyAccount]
    member_roles: dict[uuid.UUID, str]
    #: Retired role-keyed overrides, already translated to template codes.
    role_overrides: dict[str, dict[str, bool]]


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
            "RBAC backfill (legacy database)",
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


# ---------------------------------------------------------------------------
# Reading the retired model
# ---------------------------------------------------------------------------

def legacy_schema_present(db: Session) -> bool:
    """Whether `users.role` still exists — that is, the legacy columns are present."""
    return db.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'users' AND column_name = 'role'"
    )).first() is not None


def read_legacy_snapshot(db: Session) -> LegacySnapshot:
    accounts = {
        row.id: LegacyAccount(role=row.role, affiliation=row.engineer_affiliation)
        for row in db.execute(text(
            "SELECT id, role::text AS role, engineer_affiliation FROM users"
        ))
    }
    member_roles = {
        row.id: row.role
        for row in db.execute(text(
            "SELECT id, role_on_project::text AS role FROM project_members"
        ))
    }
    by_legacy: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in db.execute(text(
        "SELECT role::text AS role, permission_code, allowed FROM role_permission_overrides"
    )):
        by_legacy[row.role][row.permission_code] = row.allowed
    role_overrides = {
        template: dict(by_legacy[legacy])
        for template, legacy in LEGACY_INHERITS.items()
        if legacy is not None and by_legacy.get(legacy)
    }
    return LegacySnapshot(accounts, member_roles, role_overrides)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _classify_organizations(
    db: Session, tenant: Company, legacy: LegacySnapshot, report: BackfillReport
) -> None:
    """Give every pre-redesign company row a kind, from what its people did."""
    for company in db.query(Company).all():
        if company.id == tenant.id:
            if company.kind != "CONSULTING_OFFICE" or not company.is_tenant:
                company.kind = "CONSULTING_OFFICE"
                company.is_tenant = True
                report.organizations_classified += 1
            continue
        if company.kind != "OTHER":
            continue  # already classified by an earlier run
        people = [
            legacy.accounts[user_id]
            for (user_id,) in db.query(User.id).filter(User.company_id == company.id).all()
            if user_id in legacy.accounts
        ]
        affiliations = {person.affiliation for person in people}
        roles = {person.role for person in people}
        if affiliations & CONTRACTOR_AFFILIATIONS or "WORKER" in roles:
            company.kind = "CONTRACTOR"
        elif roles == {"OWNER"}:
            company.kind = "CLIENT"
        else:
            company.kind = "OTHER"
        report.organizations_classified += 1


def _map_users(
    db: Session, tenant: Company, roles: dict[str, Role], legacy: LegacySnapshot,
    report: BackfillReport,
) -> None:
    for user in db.query(User).all():
        if user.org_role_id is not None:
            continue
        account = legacy.accounts[user.id]
        # Raises `UnknownAffiliation` for an unrecognised value: the run stops
        # and rolls back rather than guessing a role.
        code = template_for_legacy(account.role, account.affiliation)
        role = roles.get(code)
        if role is None:
            report.unmapped_users.append(f"{user.email} ({account.role}/{account.affiliation})")
            continue
        organization_id = user.company_id or tenant.id
        rbac.assign_org_role(
            db, user=user, role=role, organization_id=organization_id,
            job_title=role.name_en,
        )
        report.users_mapped += 1
        report.memberships += 1
        report.users_by_role[code] += 1
        if account.role == "WORKER":
            report.workers_archived += 1


def _map_user_disciplines(
    db: Session, disciplines: dict[str, Discipline], report: BackfillReport
) -> None:
    """`EngineerProfile.discipline` becomes a row in the many-to-many table."""
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


def _is_contractor_side(account: LegacyAccount | None) -> bool:
    return bool(account) and (
        account.affiliation in CONTRACTOR_AFFILIATIONS or account.role == "WORKER"
    )


def _map_projects(
    db: Session, tenant: Company, roles: dict[str, Role],
    disciplines: dict[str, Discipline], legacy: LegacySnapshot, report: BackfillReport,
) -> None:
    for project in db.query(Project).all():
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
        # Worker accounts belonged to the contractor; they are archived and hold
        # nothing, but attaching them keeps the project's history honest.
        contractor_parties: dict[str, ProjectParty] = {}
        consultant_parties: dict[str, ProjectParty] = {}
        for member in members:
            user = db.get(User, member.user_id)
            if user is None or not _is_contractor_side(legacy.accounts.get(user.id)):
                continue
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
            account = legacy.accounts.get(user.id)

            if member.project_role_id is None and account is not None:
                # Derived from the *person*, not from `role_on_project`, which
                # never carried authority of its own (it had to equal the
                # account's role), except that an external-consultant Engineer
                # was stored as CONSULTANT — and mapping that literally would
                # hand them the retired Consultant defaults. Deriving from the
                # person keeps the project role a subset of the office role.
                if member.is_site_engineer and account.role == "ENGINEER":
                    template_code = "site_engineer"
                else:
                    template_code = template_for_legacy(account.role, account.affiliation)
                role = roles.get(template_code)
                if role is not None:
                    member.project_role_id = role.id
                    report.project_roles += 1

            # Office staff are never attached to an external party.
            role_is_internal = bool(
                db.get(Role, user.org_role_id).is_internal_only
                if user.org_role_id else True
            )
            if member.party_id is not None and role_is_internal:
                member.party_id = None

            if member.party_id is None and not role_is_internal:
                if user.id == project.owner_id or legacy.member_roles.get(member.id) == "OWNER":
                    if client_party is not None:
                        member.party_id = client_party.id
                        report.members_attached_to_party += 1
                elif _is_contractor_side(account):
                    party = contractor_parties.get(_party_name_for(user, "Main Contractor"))
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


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run(db: Session, *, dry_run: bool = False, commit: bool = True) -> BackfillReport:
    """Apply the backfill to a legacy database.

    Raises `NothingToBackfill`, without changing anything, on a database that
    no longer has the legacy columns or has no accounts at all.

    `commit=False` leaves the work in the caller's open transaction instead of
    writing it.
    """
    if not legacy_schema_present(db):
        raise NothingToBackfill(
            "This database has no legacy role columns: it was created after the "
            "configurable role model, or has already been migrated. Nothing to backfill."
        )
    if db.query(User.id).first() is None:
        raise NothingToBackfill(
            "This database has no accounts. A fresh deployment is initialized by "
            "`python -m app.db.bootstrap_admin`, which seeds the roles; it does not "
            "need the backfill."
        )

    legacy = read_legacy_snapshot(db)
    report = BackfillReport()

    tenant = rbac.ensure_tenant_organization(db)
    report.tenant_name = tenant.name
    _classify_organizations(db, tenant, legacy, report)

    disciplines = rbac.seed_disciplines(db)
    report.disciplines_seeded = len(disciplines)

    roles = rbac.seed_roles(db, role_overrides=legacy.role_overrides)
    report.roles_seeded = len(roles)

    _map_users(db, tenant, roles, legacy, report)
    _map_user_disciplines(db, disciplines, report)
    _map_projects(db, tenant, roles, disciplines, legacy, report)

    if dry_run:
        db.rollback()
    elif commit:
        db.commit()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill a legacy database onto configurable roles.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change and roll back.")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        report = run(db, dry_run=args.dry_run)
    except NothingToBackfill as reason:
        db.rollback()
        print(reason)
        return 0
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
