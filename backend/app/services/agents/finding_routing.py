"""Who should hear about a finding.

An automatic analysis used to notify exactly one person: the project manager
whose authority the run borrowed. That is safe and it is nearly useless — a
clash in the electrical model reaches the manager and nobody who could act on
it, so either the manager forwards everything by hand or findings quietly go
nowhere.

This decides the recipients instead, from three things the platform already
knows and an office already configures:

  * **permission** — can this person act on a finding at all;
  * **discipline** — is this finding about work they cover;
  * **responsibility** — do they carry the site, or the project.

Nothing here names a role. "The structural engineer gets the structural
findings" would be exactly the hardcoding the redesign removed; what it means
is "somebody whose disciplines include structural", and an office that models
structural and civil as one discipline, or splits MEP into three, gets the
right answer without the platform knowing how they organise.

## What this does not change

The decision to *notify at all* still belongs to
`agents.notification_policy.decide_notification` — confidence, severity and
certainty, unchanged. This only answers "and to whom". A finding nobody
qualifies for still reaches the accountable principal, because an unrouted
finding is worse than an imprecise one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.enums import UserStatus
from app.models.project import Project, ProjectMember
from app.models.rbac import Discipline
from app.models.user import User
from app.services import rbac, work_scope
from app.services.authorization import has_permission

#: A recipient must be able to do something about a finding. This is the
#: permission the AI Intelligence screen itself requires, so routing can never
#: notify somebody about a page they would be refused.
ACT_ON_FINDINGS = "ai.review_insight"


@dataclass(frozen=True)
class Recipients:
    """Who to tell, and why — the reason is kept so a run can be explained."""

    user_ids: set[uuid.UUID] = field(default_factory=set)
    reasons: dict[uuid.UUID, str] = field(default_factory=dict)

    def as_json(self) -> dict:
        return {
            "count": len(self.user_ids),
            "reasons": {str(key): value for key, value in self.reasons.items()},
        }


def _finding_discipline_codes(db: Session, insight) -> set[str]:
    """The disciplines a finding is about.

    Two vocabularies reach this. A finding raised from project data carries an
    office discipline code; one raised from a model carries IFC classification
    names (`STRUCTURAL`, `PLUMBING`…). `Discipline.ifc_disciplines` is the
    join between them, which is why an office can call something `mep` and
    still be matched by a finding tagged `PLUMBING`.
    """
    affected = insight.affected_json or {}
    raw: set[str] = set()
    for key in ("disciplines", "discipline", "affectedDisciplines"):
        value = affected.get(key)
        if isinstance(value, str):
            raw.add(value)
        elif isinstance(value, (list, tuple, set)):
            raw.update(str(item) for item in value)
    if not raw:
        return set()

    lowered = {item.strip().lower() for item in raw if item}
    upper = {item.strip().upper() for item in raw if item}
    codes = set()
    for discipline in db.query(Discipline).all():
        if discipline.code in lowered:
            codes.add(discipline.code)
            continue
        if upper & {str(name).upper() for name in (discipline.ifc_disciplines or [])}:
            codes.add(discipline.code)
    return codes


def resolve(db: Session, *, project_id: uuid.UUID, insight, principal: User) -> Recipients:
    """The people who should hear about this finding."""
    recipients = Recipients()

    def add(user_id: uuid.UUID, reason: str) -> None:
        if user_id not in recipients.user_ids:
            recipients.user_ids.add(user_id)
            recipients.reasons[user_id] = reason

    # The accountable person, always. A finding that reaches nobody is a
    # finding that did not happen, and the principal is who the run was
    # performed on behalf of.
    add(principal.id, "accountable for this project")

    project = db.get(Project, project_id)
    if project is None:
        return recipients

    codes = _finding_discipline_codes(db, insight)

    members = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.is_active.is_(True),
    ).all()

    for member in members:
        if member.user_id in recipients.user_ids:
            continue
        person = db.get(User, member.user_id)
        if person is None or person.status != UserStatus.ACTIVE:
            continue

        # Agent findings are the office's own review material. An external
        # participant is never told about one — what a contractor learns is
        # what somebody decided to tell them.
        if rbac.is_external_participant(db, person, project_id):
            continue

        # Eligibility. Routing must never tell somebody about a finding they
        # would be refused when they clicked it.
        if not has_permission(db, person, ACT_ON_FINDINGS, project_id):
            continue

        held = rbac.discipline_codes(
            rbac.disciplines_for_member(db, member.user_id, project_id)
        )

        if codes:
            if held & codes:
                add(member.user_id, f"covers {', '.join(sorted(held & codes))}")
            elif member.is_site_engineer and not held:
                # Site responsibility with no discipline recorded: they walk
                # the whole site, so a finding about any part of it is theirs.
                add(member.user_id, "carries site responsibility")
            continue

        # No discipline on the finding — it is about the project as a whole.
        # Site engineers and whoever runs the work get it; a specialist does
        # not need every general observation.
        if member.is_site_engineer:
            add(member.user_id, "carries site responsibility")
        elif work_scope.sees_all_tasks(db, person, project_id):
            add(member.user_id, "runs this project")

    return recipients
