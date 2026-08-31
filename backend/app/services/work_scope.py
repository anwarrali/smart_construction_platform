"""How much of a project's work one person may see.

The retired model answered this with two helpers — `is_main_contractor_engineer`
and `is_consultant_engineer` — and then repeated the same two answers, by hand,
in the tasks, site-report, issue, design-change, document, attachment and
messaging endpoints. Nineteen files held a copy of a rule that only ever had
three shapes:

  * **Own work.** Execution-side people saw the tasks assigned to them.
  * **Reviewed work.** Supervision-side people saw what they were the named
    reviewer for, in their own discipline.
  * **Everything else.** Administrators, project managers and the client saw
    the project.

This module is those three shapes, written once. Nothing here decides
authorization on its own: every answer comes from `has_permission` or from a
data relationship the platform already records (task assignment, reviewer
assignment, the person's disciplines).

## Why the narrowing is not a permission on its own

"Is narrowed to their own work" was the *affiliation*, and turning it into a
permission would have re-created the same rigid axis under a new name. What
actually distinguishes the two narrow cases is data: an execution engineer is
assigned to tasks, a reviewing engineer is named on `ProjectConsultantReviewer`.
So the narrow view is the union of the two, and a person who is both sees both
— which the old either/or branching could not express at all.

## Discipline is a filter, never a grant

`project.view_all_disciplines` decides whether somebody's view is narrowed. The
disciplines themselves come from the configurable assignment, and somebody with
none recorded is not narrowed — hiding the whole project from a person the
office deliberately put on it is a worse failure than showing them a drawing
outside their specialism.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.project import ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services import rbac
from app.services.authorization import has_permission

#: Holding this means "not narrowed to my own disciplines".
ALL_DISCIPLINES = "project.view_all_disciplines"
#: Holding this means "not narrowed to my own work".
ALL_TASKS = "task.view_all"


# ---------------------------------------------------------------------------
# Discipline scope
# ---------------------------------------------------------------------------

def sees_all_disciplines(db: Session, user: User, project_id: uuid.UUID) -> bool:
    """Whether this person's view is *not* narrowed to their own disciplines.

    One question, one answer. A transitional branch stood here that read
    `engineer_affiliation` for an account with no role row; the contract step
    removed it along with the fallback it existed to protect.
    """
    return has_permission(db, user, ALL_DISCIPLINES, project_id)


def scoped_discipline_codes(
    db: Session, user: User, project_id: uuid.UUID
) -> set[str] | None:
    """The disciplines this person's view is narrowed to.

    `None` means "not narrowed" — either they hold `project.view_all_disciplines`
    or the office has recorded no discipline for them.
    """
    if sees_all_disciplines(db, user, project_id):
        return None
    codes = rbac.discipline_codes(rbac.disciplines_for_member(db, user.id, project_id))
    return codes or None


def narrow_to_disciplines(query, task_id_column, db: Session, user: User, project_id):
    """Narrow a query of task-linked records to this person's disciplines.

    Records with no task attached are project-level and stay visible: a
    contract or a general site report belongs to the project, not to one
    specialism.
    """
    codes = scoped_discipline_codes(db, user, project_id)
    if codes is None:
        return query
    task_ids = db.query(Task.id).filter(
        Task.project_id == project_id, Task.discipline.in_(codes),
    ).scalar_subquery()
    return query.filter(or_(task_id_column.is_(None), task_id_column.in_(task_ids)))


def task_is_in_scope(db: Session, user: User, project_id, task: Task | None) -> bool:
    """Whether one task-linked record falls inside this person's disciplines."""
    codes = scoped_discipline_codes(db, user, project_id)
    if codes is None or task is None:
        return True
    return (task.discipline or None) in codes


# ---------------------------------------------------------------------------
# Task scope
# ---------------------------------------------------------------------------

def sees_all_tasks(db: Session, user: User, project_id: uuid.UUID) -> bool:
    return has_permission(db, user, ALL_TASKS, project_id)


def reviewable_task_ids(db: Session, user: User, project_id: uuid.UUID) -> set[uuid.UUID]:
    """Tasks this person is the named reviewer for on this project.

    Resolved through `consultant_approval_service`, which already encodes the
    project's approval mode, the reviewer's discipline assignment and the
    per-engineer remit an administrator may have configured. Duplicating any of
    that here is exactly what this module exists to stop.
    """
    from app.services.consultant_approval_service import can_consultant_review_task

    if not has_permission(db, user, "task.review", project_id):
        return set()
    candidates = db.query(Task).filter(
        Task.project_id == project_id, Task.review_required.is_(True),
    ).all()
    return {
        task.id for task in candidates
        if can_consultant_review_task(db, user, task)
    }


def narrow_to_own_work(query, db: Session, user: User, project_id: uuid.UUID):
    """Narrow a task query to the work this person holds or reviews.

    The union is the point. Somebody who is assigned work *and* reviews other
    work sees both, which the retired either/or branching could not express —
    it asked which side of the old owner/contractor/consultant triangle you
    were on and gave you one answer.
    """
    if sees_all_tasks(db, user, project_id):
        return query
    reviewable = reviewable_task_ids(db, user, project_id)
    condition = Task.assignees.any(User.id == user.id)
    if reviewable:
        condition = or_(condition, Task.id.in_(reviewable))
    return query.filter(condition)


def can_see_task(db: Session, user: User, task: Task) -> bool:
    """Whether this person may open one task."""
    if sees_all_tasks(db, user, task.project_id):
        return True
    if any(assignee.id == user.id for assignee in task.assignees):
        return True
    from app.services.consultant_approval_service import can_consultant_review_task

    return (
        has_permission(db, user, "task.review", task.project_id)
        and can_consultant_review_task(db, user, task)
    )


def report_discipline_id(db: Session, user: User, project_id, task: Task | None):
    """Which discipline a site report should be filed under.

    Site Engineer is a project responsibility, not a discipline — a project can
    have a civil one, an architectural one and an electrical one at the same
    time, and the report has to say which visit it records or a project with
    several of them produces an undifferentiated pile.

    Resolved from what is actually known, most specific first:

      1. the discipline of the task the report is about;
      2. the reporter's discipline on this project, when they have exactly one —
         somebody covering several has not told us which one this visit was, and
         guessing would be worse than leaving it open.

    Returns `None` when neither answers, which is a legitimate state: a general
    site walk belongs to the project, not to a specialism.
    """
    from app.models.rbac import Discipline

    codes: list[str] = []
    if task is not None and task.discipline:
        codes.append(task.discipline)
    else:
        held = rbac.disciplines_for_member(db, user.id, project_id)
        if len(held) == 1:
            codes.append(held[0].code)
    for code in codes:
        match = db.query(Discipline).filter(
            Discipline.code == code,
        ).order_by(Discipline.organization_id.nullslast()).first()
        if match is not None:
            return match.id
    return None


# ---------------------------------------------------------------------------
# Responsibility on a project
# ---------------------------------------------------------------------------

def is_site_engineer(db: Session, user: User, project_id: uuid.UUID) -> bool:
    """Whether this person carries site responsibility on this project.

    A project responsibility, not a role: a project may have any number of site
    engineers, of any disciplines, and the same person may be one here and not
    there.
    """
    return rbac.membership_context(db, user.id, project_id).is_site_engineer


def site_engineer_ids(
    db: Session, project_id: uuid.UUID, *, discipline_codes: set[str] | None = None
) -> set[uuid.UUID]:
    """The project's site engineers, optionally narrowed to disciplines.

    Used by notification routing to find the people who actually walk the site
    a finding is about.
    """
    members = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.is_active.is_(True),
        ProjectMember.is_site_engineer.is_(True),
    ).all()
    if discipline_codes is None:
        return {member.user_id for member in members}
    matched = set()
    for member in members:
        held = rbac.discipline_codes(
            rbac.disciplines_for_member(db, member.user_id, project_id)
        )
        if held & discipline_codes:
            matched.add(member.user_id)
    return matched
