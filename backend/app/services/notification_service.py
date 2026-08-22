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

Since push was added, `notify()` fans out to channels:

    notify()
      ├── PostgreSQL row (always, synchronous, inside the caller's transaction)
      └── push queue     (mobile + web, dispatched *after* that commit)

The ordering is the whole design. The database row is the notification; push is
a doorbell for it. A push that fails costs the user a buzz, never the record —
and because delivery is queued on the session and flushed by an `after_commit`
listener, a rolled-back transaction never rings a doorbell for something that
did not happen. See `app.services.push.dispatcher`.

Adding a channel later (Telegram, SMS) means one more provider under
`app.services.push` and one more line in `_fan_out`; no call site changes.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.enums import NotificationStatus, NotificationType, TaskStatus
from app.models.notification import Notification
from app.services.push import PushMessage, queue_push
from app.services.realtime import EventType, publish_event

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
    _fan_out(db, notification)
    return notification



def _fan_out(db: Session, notification: Notification) -> None:
    """Hand the persisted notification to every non-database channel.

    Two channels, answering different questions:

      * **push** — reach someone who is not looking at the application.
      * **realtime** — keep an application that *is* open in sync.

    Both are deliberately kept: suppressing push because a tab might be open
    would trade a duplicate (harmless) for a missed notification (not), and
    the frontend absorbs the overlap because both paths converge on the same
    idempotent store update.

    Neither can lose the row. Push is queued and flushed on `after_commit`;
    the realtime event rides `pg_notify` on this very session, which
    PostgreSQL delivers only if the transaction commits. Same guarantee,
    obtained two different ways.
    """
    queue_push(db, notification.user_id, build_push_message(notification))
    publish_event(
        db,
        event_type=EventType.NOTIFICATION_CREATED,
        user_id=notification.user_id,
        project_id=notification.project_id,
        entity_type=notification.related_entity_type,
        entity_id=notification.related_entity_id,
    )


def build_push_message(notification: Notification) -> PushMessage:
    """The wire form of a notification.

    The routing payload names the *subject* (project, entity type, entity id)
    and never a resolved URL, because the URL is role-dependent: the web app
    prefixes a project workspace with /engineer, /project-manager or
    /consultant-engineer, and the mobile app uses neither. Each client already
    owns that mapping (`utils/projectRoutes.ts`, `app_router.dart`), so the
    server would only be guessing at a role it is not sending to.

    `clickPath` is therefore the one path both clients genuinely share: the
    notification's own detail route, which each resolves onward using the
    payload below.
    """
    data = {
        "notificationId": str(notification.id),
        "type": notification.type.value if notification.type else "system",
        "category": notification.category or CATEGORY_SYSTEM,
        "priority": notification.priority or PRIORITY_NORMAL,
    }
    if notification.project_id:
        data["projectId"] = str(notification.project_id)
    if notification.task_id:
        data["taskId"] = str(notification.task_id)
    if notification.related_entity_type:
        data["entityType"] = notification.related_entity_type
    if notification.related_entity_id:
        data["entityId"] = str(notification.related_entity_id)
    if notification.message_key:
        data["messageKey"] = notification.message_key

    return PushMessage(
        title=notification.title,
        body=notification.message,
        notification_id=notification.id,
        data=data,
        click_path=f"/notifications/{notification.id}",
        # Same subject at the same stage collapses on the device, so a phone
        # that was off all afternoon shows one entry per subject rather than
        # a screenful of the same warning.
        collapse_key=notification.dedupe_key,
    )


# --- public service interface -----------------------------------------------
# `notify()` remains the primitive. These are the verbs the rest of the
# application should reach for, so that "who receives this" is expressed once
# here rather than as a loop rewritten at every call site.


def notify_user(db: Session, *, user_id: uuid.UUID, **kwargs) -> Notification | None:
    """One notification for one person. A thin alias for `notify`."""
    return notify(db, user_id=user_id, **kwargs)


def notify_users(db: Session, *, user_ids, **kwargs) -> list[Notification]:
    """One notification each, for several people.

    Duplicate and empty ids are dropped rather than rejected: callers assemble
    recipients by unioning "the assignee", "the manager" and "the reviewer",
    and those overlap constantly. Notifying somebody twice for one event is
    the bug this prevents.
    """
    seen: set[uuid.UUID] = set()
    created: list[Notification] = []
    for user_id in user_ids:
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        notification = notify(db, user_id=user_id, **kwargs)
        if notification is not None:
            created.append(notification)
    return created


def notify_project_users(
    db: Session,
    *,
    project_id: uuid.UUID,
    exclude_user_id: uuid.UUID | None = None,
    roles=None,
    **kwargs,
) -> list[Notification]:
    """Notify the project's team.

    Membership is read from `project_members` plus the project's own manager
    and owner — the same three sources `user_has_project_access` consults — so
    this cannot reach anybody who would be refused the project on a GET, and a
    notification therefore never leaks work across projects.

    `exclude_user_id` is normally the actor: telling somebody about the thing
    they just did is noise, and it is the most common complaint about
    notification systems.
    """
    # Imported here rather than at module scope: `app.models.project` pulls in
    # models that transitively import this module, and a top-level import
    # would close that cycle at startup.
    from app.models.project import Project, ProjectMember

    project = db.get(Project, project_id)
    if project is None:
        return []

    member_query = select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
    if roles:
        member_query = member_query.where(ProjectMember.role.in_(list(roles)))
    recipient_ids = [row[0] for row in db.execute(member_query).all()]
    if not roles:
        # The manager and owner are not necessarily rows in project_members.
        recipient_ids.extend([project.project_manager_id, project.owner_id])

    recipients = [uid for uid in recipient_ids if uid and uid != exclude_user_id]
    return notify_users(db, user_ids=recipients, project_id=project_id, **kwargs)


def mark_as_read(db: Session, *, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Mark one notification read. False when it is not this user's.

    Ownership is part of the WHERE clause rather than a check before it: an
    "exists but belongs to somebody else" branch is how cross-user information
    leaks, and the caller has no legitimate reason to tell the two cases apart.
    """
    result = db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True, status=NotificationStatus.READ, read_at=func.now())
    )
    if result.rowcount:
        return True
    # Already read counts as success: the client's intent is satisfied, and a
    # 404 here would make a double-tap look like an error.
    return db.query(Notification.id).filter(
        Notification.id == notification_id, Notification.user_id == user_id
    ).first() is not None


def mark_all_as_read(
    db: Session, *, user_id: uuid.UUID, project_id: uuid.UUID | None = None
) -> int:
    """Mark this user's unread notifications read. Returns how many changed."""
    statement = update(Notification).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    )
    if project_id:
        statement = statement.where(Notification.project_id == project_id)
    result = db.execute(
        statement.values(is_read=True, status=NotificationStatus.READ, read_at=func.now())
    )
    return int(result.rowcount or 0)


def unread_count(
    db: Session, *, user_id: uuid.UUID, project_id: uuid.UUID | None = None
) -> int:
    """Unread total. Served by ix_notifications_user_unread."""
    statement = select(func.count(Notification.id)).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    )
    if project_id:
        statement = statement.where(Notification.project_id == project_id)
    return int(db.execute(statement).scalar() or 0)


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
