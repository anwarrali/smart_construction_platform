"""The one place a notification is created.

Before this module owned it, notifications were built by hand at 30+ call
sites with five different shapes; `category`, `requires_action` and
`action_url` were set at some and defaulted at others, and deduplication was a
title-equality check that could never fire twice for the same subject — so a
"task due soon" notice could never become "due today", and its text froze at
whatever the first sweep rendered.

`notify()` is the single entry point. It owns:

  * the category vocabulary (DIRECT / WORKFLOW / REMINDER / DEADLINE / SYSTEM),
  * the priority vocabulary (INFO / NORMAL / IMPORTANT / CRITICAL),
  * deduplication, via an explicit `dedupe_key` that names *this subject at
    this stage* rather than comparing rendered text,
  * the localizable message key/params, alongside English fallback text.

It never commits. Callers keep their existing transaction boundary, so a
notification cannot half-commit someone else's business write.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.enums import NotificationType, TaskStatus
from app.models.notification import Notification

# --- vocabulary -------------------------------------------------------------
# Deliberately plain strings, matching the existing `category` column: naming a
# new category must not require a database enum migration.

CATEGORY_DIRECT = "DIRECT"        # something happened *to* this user
CATEGORY_WORKFLOW = "WORKFLOW"    # something needs this user's workflow action
CATEGORY_REMINDER = "REMINDERS"   # unchanged spelling: existing rows use this
CATEGORY_DEADLINE = "DEADLINE"    # something is approaching / past its date
CATEGORY_SYSTEM = "SYSTEM"

PRIORITY_INFO = "INFO"
PRIORITY_NORMAL = "NORMAL"
PRIORITY_IMPORTANT = "IMPORTANT"
PRIORITY_CRITICAL = "CRITICAL"

#: Ordered weakest → strongest, so escalation can be compared numerically.
PRIORITY_ORDER = (PRIORITY_INFO, PRIORITY_NORMAL, PRIORITY_IMPORTANT, PRIORITY_CRITICAL)


def priority_rank(value: str) -> int:
    try:
        return PRIORITY_ORDER.index((value or PRIORITY_NORMAL).upper())
    except ValueError:
        return PRIORITY_ORDER.index(PRIORITY_NORMAL)


def notify(
    db: Session,
    *,
    user_id: uuid.UUID,
    title: str,
    message: str,
    notification_type: NotificationType = NotificationType.SYSTEM,
    category: str = CATEGORY_SYSTEM,
    priority: str = PRIORITY_NORMAL,
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    requires_action: bool = False,
    action_url: str | None = None,
    dedupe_key: str | None = None,
    message_key: str | None = None,
    message_params: dict | None = None,
) -> Notification | None:
    """Create one notification, or return None when it would be a duplicate.

    `dedupe_key` is the whole idempotency story: pass one for anything a
    repeated evaluation could re-derive (reminders, deadline warnings), and
    leave it None for genuine one-off events (a new message, a share) which
    are *supposed* to arrive every time they happen.
    """
    if dedupe_key:
        # Scoped to the user: the same subject at the same stage legitimately
        # notifies several people, but never the same person twice.
        exists = db.query(Notification.id).filter(
            Notification.user_id == user_id,
            Notification.dedupe_key == dedupe_key,
        ).first()
        if exists:
            return None

    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
        category=category,
        priority=(priority or PRIORITY_NORMAL).upper(),
        project_id=project_id,
        task_id=task_id,
        related_entity_type=entity_type,
        related_entity_id=entity_id,
        requires_action=requires_action,
        action_url=action_url,
        dedupe_key=dedupe_key,
        message_key=message_key,
        message_params_json=message_params or {},
    )
    db.add(notification)
    # The session runs with autoflush disabled, so without this a second
    # `notify` in the same sweep cannot see the row just added and the dedupe
    # check above would pass twice. Idempotency must not depend on the caller
    # happening to commit in between.
    db.flush()
    return notification


# --- task deadline intelligence ---------------------------------------------
#
# These used to run inside the dashboard GET handlers, which meant a deadline
# was only ever noticed if somebody happened to open a dashboard — and the
# read request then committed writes. They now run from the reminder sweep
# (see `reminder_service`), and each stage carries its own dedupe key so the
# same task can legitimately progress:
#
#     due in 3 days  →  (nothing)
#     due tomorrow   →  task-deadline:<id>:DUE_TOMORROW   NORMAL
#     due today      →  task-deadline:<id>:DUE_TODAY      IMPORTANT
#     overdue        →  task-deadline:<id>:OVERDUE:<days-bucket>
#                                                          IMPORTANT/CRITICAL
#
# Each stage fires at most once per user, and a completed/cancelled task
# produces no stage at all — so finishing work stops future warnings.

#: Statuses that mean the work is finished or abandoned; no deadline chasing.
CLOSED_TASK_STATUSES = {TaskStatus.DONE, TaskStatus.CANCELLED}


def deadline_stage(task, today: date) -> tuple[str, str] | None:
    """(stage, priority) for a task's deadline today, or None if nothing is due.

    Bucketing overdue tasks by escalation step rather than by exact day count
    is what stops a daily "overdue by N days" nag: the key only changes when
    the situation genuinely worsens.
    """
    if task.status in CLOSED_TASK_STATUSES or not task.planned_end_date:
        return None
    days_remaining = (task.planned_end_date - today).days
    if days_remaining == 1:
        return "DUE_TOMORROW", PRIORITY_NORMAL
    if days_remaining == 0:
        return "DUE_TODAY", PRIORITY_IMPORTANT
    if days_remaining < 0:
        overdue_days = -days_remaining
        # Escalation steps, not calendar days: first day, then a week, then
        # beyond. A task overdue by 3 and by 5 days shares one notification.
        if overdue_days >= 7:
            return "OVERDUE_WEEK", PRIORITY_CRITICAL
        if overdue_days >= 3:
            return "OVERDUE_SEVERAL", PRIORITY_IMPORTANT
        return "OVERDUE", PRIORITY_IMPORTANT
    return None


def escalate_for_context(task, stage: str, priority: str) -> str:
    """Raise the priority when an overdue task is genuinely more damaging.

    Only overdue tasks escalate on context, and only for reasons that actually
    affect other people's work — a critical-path task or one with dependents
    blocks somebody else, which is the whole justification for shouting louder.
    """
    if not stage.startswith("OVERDUE"):
        return priority
    if task.is_critical_path or getattr(task, "dependents", None):
        return PRIORITY_CRITICAL
    return priority


DEADLINE_TEXT = {
    "DUE_TOMORROW": ("Task due tomorrow", "{name} is due tomorrow."),
    "DUE_TODAY": ("Task due today", "{name} is due today."),
    "OVERDUE": ("Task overdue", "{name} is overdue."),
    "OVERDUE_SEVERAL": ("Task overdue", "{name} has been overdue for several days."),
    "OVERDUE_WEEK": ("Task overdue", "{name} has been overdue for more than a week."),
}


def notify_task_deadline(db: Session, task, project, recipient_ids, stage: str, priority: str) -> int:
    """One deadline notification per recipient for this stage. Idempotent."""
    title, template = DEADLINE_TEXT[stage]
    critical = priority == PRIORITY_CRITICAL and stage.startswith("OVERDUE")
    message = template.format(name=task.name)
    if critical:
        message += " It is on the critical path or has dependent work."
    created = 0
    for user_id in recipient_ids:
        if not user_id:
            continue
        result = notify(
            db, user_id=user_id,
            title=("Critical: " + title) if critical else title,
            message=message,
            notification_type=(
                NotificationType.TASK_OVERDUE if stage.startswith("OVERDUE")
                else NotificationType.TASK_UPDATED
            ),
            category=CATEGORY_DEADLINE,
            priority=priority,
            project_id=task.project_id,
            task_id=task.id,
            entity_type="TASK",
            entity_id=task.id,
            requires_action=True,
            dedupe_key=f"task-deadline:{task.id}:{stage}",
            message_key=f"taskDeadline.{stage}",
            message_params={"name": task.name, "critical": critical},
        )
        created += int(result is not None)
    return created
