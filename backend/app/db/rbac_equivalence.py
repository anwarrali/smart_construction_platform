"""Prove the configurable role model grants exactly what the enum model did.

For every account, and for every project that account can reach, this computes
the permission set twice — once through `legacy_effective_permissions`, which
is the retired resolution preserved verbatim, and once through
`effective_permissions`, which is the live one — and reports every difference.

The gate is not "the diff is small". It is:

    every difference must be one that was declared in advance.

Undeclared differences fail the run. That distinction matters because this
redesign *does* change some behaviour on purpose, and a check that simply
asserted equality would have had to be weakened until it proved nothing. The
declared changes are listed in `INTENTIONAL_CHANGES` below, each with the
reason it exists, and each one is separately asserted by a test — so "expected"
here never means "unexplained".

    python -m app.db.rbac_equivalence
    python -m app.db.rbac_equivalence --verbose
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

import app.models  # noqa: F401  - configure all SQLAlchemy relationships
from app.db.database import SessionLocal
from app.models.enums import UserRole, UserStatus
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.authorization import effective_permissions, legacy_effective_permissions


@dataclass(frozen=True)
class IntentionalChange:
    """One behaviour change this redesign makes on purpose."""

    key: str
    summary: str
    reason: str

    def applies(self, user: User, gained: set[str], lost: set[str]) -> bool:
        raise NotImplementedError


@dataclass(frozen=True)
class WorkerLosesEverything(IntentionalChange):
    def applies(self, user: User, gained: set[str], lost: set[str]) -> bool:
        # A retired worker account keeps its row so its field evidence stays
        # attributable, and holds nothing. Losing permissions is the point;
        # gaining any would be a bug.
        return user.role == UserRole.WORKER and not gained


@dataclass(frozen=True)
class ConsultantDocumentRuleMadeExplicit(IntentionalChange):
    def applies(self, user: User, gained: set[str], lost: set[str]) -> bool:
        return (
            user.role == UserRole.ENGINEER
            and user.engineer_affiliation == "external_consultant"
            and not gained
            and lost == {"project.view_all_disciplines"}
        )


@dataclass(frozen=True)
class ExternalPartyLosesOfficeAuthority(IntentionalChange):
    def applies(self, user: User, gained: set[str], lost: set[str]) -> bool:
        from app.services import rbac

        return (
            user.engineer_affiliation == "main_contractor"
            and not gained
            and bool(lost)
            and lost <= (rbac.OFFICE_ONLY | rbac.NON_PROJECT_SCOPED)
        )


@dataclass(frozen=True)
class ProjectManagerScopeFromMembership(IntentionalChange):
    def applies(self, user: User, gained: set[str], lost: set[str]) -> bool:
        # A project manager's own project memberships now count. The retired
        # model skipped them, so this can only ever *add* projects to the set
        # they reach — never remove one, and never change which permissions
        # they hold on a project they already reached. A loss here would mean
        # something else went wrong.
        return user.role == UserRole.PROJECT_MANAGER and not lost


INTENTIONAL_CHANGES: tuple[IntentionalChange, ...] = (
    WorkerLosesEverything(
        key="worker_archived",
        summary="Worker accounts hold no permissions",
        reason=(
            "Workers are no longer platform users. The account is retained and "
            "deactivated so historical field evidence stays attributable, and it "
            "is moved onto a role with an empty permission set."
        ),
    ),
    ExternalPartyLosesOfficeAuthority(
        key="external_party_office_authority",
        summary="External participants hold none of the office's own authority",
        reason=(
            "Reviewing work, approving a design change, certifying a payment "
            "claim, verifying evidence and running the project team are what "
            "the consulting office is engaged to do. The retired model let a "
            "main-contractor engineer *hold* those permissions and relied on an "
            "`is_consultant_engineer(...)` guard at each endpoint to stop them "
            "using any — so the permission set was always wider than the real "
            "behaviour, and any endpoint that forgot the guard was a hole. "
            "`Permission.office_only` moves the restriction into the resolution "
            "itself, which narrows what these accounts hold to match what they "
            "could already do. No external participant loses an ability they "
            "were actually able to exercise."
        ),
    ),
    ProjectManagerScopeFromMembership(
        key="project_manager_membership_honoured",
        summary="A project manager's project memberships now count toward project access",
        reason=(
            "`user_has_project_access` and `accessible_project_ids` each carried "
            "an early return for `role == UserRole.PROJECT_MANAGER` that answered "
            "\"the projects you manage\" and skipped the membership check below "
            "it. A project manager added to another office project as, say, a "
            "discipline reviewer was therefore locked out of it, while somebody "
            "in an identically-permissioned role the office happened to call "
            "something else was not. `manageable_project` carried the matching "
            "refusal. All three are gone, and everyone resolves through the same "
            "union: owner, assigned manager, or active member, then the "
            "permission. This widens access for exactly one shape of account — a "
            "PROJECT_MANAGER who is a member elsewhere — and it widens it to what "
            "their membership already said. Nothing loses access."
        ),
    ),
    ConsultantDocumentRuleMadeExplicit(
        key="consultant_document_scope_explicit",
        summary="Consultant reviewers no longer carry project.view_all_disciplines",
        reason=(
            "`project.view_all_disciplines` is a new code that names a rule the "
            "platform "
            "already enforced in `document_access`: an ordinary Engineer saw "
            "every document on a project, a consultant-side reviewer was "
            "narrowed to their own discipline. Because the code did not exist "
            "before, the retired resolution reports it for every Engineer, "
            "while the `senior_engineer` template these accounts migrate onto "
            "withholds it. No document becomes unreadable and none becomes "
            "readable: the reviewer keeps exactly the discipline-scoped access "
            "they had, and the rule producing it is now written down instead of "
            "inferred from an affiliation string."
        ),
    ),
)


@dataclass
class Difference:
    user_email: str
    user_role: str
    project: str | None
    gained: set[str] = field(default_factory=set)
    lost: set[str] = field(default_factory=set)
    explained_by: str | None = None

    def render(self) -> str:
        where = f" on {self.project}" if self.project else " (global)"
        parts = [f"{self.user_email} [{self.user_role}]{where}"]
        if self.gained:
            parts.append(f"      gained: {', '.join(sorted(self.gained))}")
        if self.lost:
            parts.append(f"      lost  : {', '.join(sorted(self.lost))}")
        if self.explained_by:
            parts.append(f"      expected: {self.explained_by}")
        return "\n".join(parts)


@dataclass
class EquivalenceReport:
    users_checked: int = 0
    pairs_checked: int = 0
    identical: int = 0
    expected: list[Difference] = field(default_factory=list)
    unexpected: list[Difference] = field(default_factory=list)
    unmigrated: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unexpected

    def render(self, verbose: bool = False) -> str:
        lines = [
            "RBAC old-vs-new permission equivalence",
            f"  accounts checked        : {self.users_checked}",
            f"  (user, project) pairs   : {self.pairs_checked}",
            f"  identical               : {self.identical}",
            f"  expected differences    : {len(self.expected)}",
            f"  UNEXPECTED differences  : {len(self.unexpected)}",
        ]
        if self.unmigrated:
            lines.append(
                f"  accounts without a database role: {len(self.unmigrated)} "
                "(resolved through the fallback, so they cannot differ)"
            )
        if verbose and self.expected:
            lines.append("\n  Expected differences:")
            lines += [f"    {item.render()}" for item in self.expected]
        if self.unexpected:
            lines.append("\n  UNEXPECTED differences — the gate fails:")
            lines += [f"    {item.render()}" for item in self.unexpected]
        lines.append("")
        lines.append("  RESULT: PASS" if self.ok else "  RESULT: FAIL")
        return "\n".join(lines)


def _explain(user: User, gained: set[str], lost: set[str]) -> str | None:
    for change in INTENTIONAL_CHANGES:
        if change.applies(user, gained, lost):
            return f"{change.key} — {change.summary}"
    return None


def _projects_for(db: Session, user: User) -> list[Project]:
    """Projects worth checking this account against.

    Membership, ownership and management — the three ways somebody reaches a
    project. A global (project-less) comparison is always done as well, because
    that is where the non-project-scoped permissions live and where an external
    participant's ceiling has to hold.
    """
    member_ids = db.query(ProjectMember.project_id).filter(
        ProjectMember.user_id == user.id
    ).scalar_subquery()
    return (
        db.query(Project)
        .filter(
            (Project.id.in_(member_ids))
            | (Project.owner_id == user.id)
            | (Project.project_manager_id == user.id)
        )
        .all()
    )


def run(db: Session) -> EquivalenceReport:
    report = EquivalenceReport()

    for user in db.query(User).order_by(User.email).all():
        report.users_checked += 1
        if user.org_role_id is None and user.status == UserStatus.ACTIVE:
            report.unmigrated.append(user.email)

        contexts: list[tuple[str | None, object]] = [(None, None)]
        contexts += [(project.name, project.id) for project in _projects_for(db, user)]

        for label, project_id in contexts:
            report.pairs_checked += 1
            old = legacy_effective_permissions(db, user, project_id)
            new = effective_permissions(db, user, project_id)
            if old == new:
                report.identical += 1
                continue
            difference = Difference(
                user_email=user.email,
                user_role=user.role.value if user.role else "?",
                project=label,
                gained=new - old,
                lost=old - new,
            )
            explanation = _explain(user, difference.gained, difference.lost)
            if explanation:
                difference.explained_by = explanation
                report.expected.append(difference)
            else:
                report.unexpected.append(difference)

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare old and new permission resolution for every account.",
    )
    parser.add_argument("--verbose", action="store_true",
                        help="List the expected differences as well as the unexpected ones.")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        report = run(db)
    finally:
        db.close()

    print(report.render(verbose=args.verbose))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
