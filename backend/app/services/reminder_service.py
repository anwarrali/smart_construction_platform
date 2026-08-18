"""Reminder evaluation shared by the secured endpoint and the background scheduler.

The rules themselves (interval, maximum, quiet hours) already live in
`collaboration_policy.reminder_is_due`; this module owns *what* is waiting for
action, *who* must be reminded, and the idempotency that stops a reminder from
being sent twice for the same waiting state.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.collaboration import MessageRecipientState, OwnerRequest, ReminderEvent, ReminderRule
from app.models.enums import IssueSeverity, IssueStatus, NotificationType, ProjectStatus, TaskStatus
from app.models.issue import Issue
from app.models.message import Conversation, Message
from app.models.notification import Notification
from app.models.project import Project
from app.models.site_report import SiteReport
from app.models.task import Task
from app.services.audit_service import record_audit
from app.services.collaboration_policy import reminder_is_due
from app.services.notification_service import (
    CATEGORY_DEADLINE,
    CATEGORY_REMINDER,
    CATEGORY_WORKFLOW,
    PRIORITY_CRITICAL,
    PRIORITY_IMPORTANT,
    PRIORITY_NORMAL,
    deadline_stage,
    escalate_for_context,
    notify,
    notify_task_deadline,
    priority_rank,
)

# Owner-request states that still expect a human action. READ is deliberately
# absent from the "handled" set: reading a message is not handling it.
ACTIVE_REQUEST_STATUSES = {
    "SUBMITTED", "ASSIGNED", "UNDER_REVIEW", "NEEDS_CLARIFICATION",
    "ACCEPTED", "CONVERTED_TO_DESIGN_CHANGE",
}
HANDLED_MESSAGE_STATUSES = ["RESPONDED", "RESOLVED"]

DEFAULT_INTERVALS = {"NORMAL": (1440, 1440), "HIGH": (360, 360), "CRITICAL": (120, 120)}


def effective_rule(db: Session, project_id, priority: str, target_type: str = "IMPORTANT_COMMUNICATION") -> ReminderRule:
    """Configured rule for the project, or the platform default (never persisted)."""
    rule = db.query(ReminderRule).filter(
        ReminderRule.project_id == project_id,
        ReminderRule.target_type == target_type,
        ReminderRule.priority == priority,
    ).first()
    if rule:
        return rule
    first, repeat = DEFAULT_INTERVALS.get(priority, DEFAULT_INTERVALS["NORMAL"])
    return ReminderRule(
        project_id=project_id, target_type=target_type, priority=priority,
        first_reminder_minutes=first, repeat_interval_minutes=repeat,
        maximum_reminders=3, enabled=True,
    )


def collect_targets(db: Session, project_id: uuid.UUID) -> list[tuple]:
    """Every item in one project still waiting on a named person.

    Every collector here is *state-aware by query*: an item only appears while
    it is genuinely still waiting. That is what makes "stop reminding once it
    is handled" structural rather than something a later check has to
    remember — a verified report, an answered consultation or a resolved issue
    simply stops being selected.
    """
    targets: list[tuple] = []
    for item in db.query(OwnerRequest).filter(
        OwnerRequest.project_id == project_id,
        OwnerRequest.status.in_(ACTIVE_REQUEST_STATUSES),
        OwnerRequest.assigned_to_id.isnot(None),
    ).all():
        targets.append(("OWNER_REQUEST", item.id, item.assigned_to_id, item.priority, item.created_at, item.title))
    states = db.query(MessageRecipientState, Message).join(
        Message, Message.id == MessageRecipientState.message_id,
    ).filter(
        Message.conversation.has(project_id=project_id),
        Message.requires_response == True,  # noqa: E712 - SQLAlchemy boolean comparison
        MessageRecipientState.response_status.notin_(HANDLED_MESSAGE_STATUSES),
    ).all()
    for state, message in states:
        targets.append(("MESSAGE", message.id, state.user_id, message.priority, message.created_at, message.content[:80]))
    targets.extend(_site_report_targets(db, project_id))
    targets.extend(_consultation_targets(db, project_id))
    targets.extend(_issue_targets(db, project_id))
    return targets


def _site_report_targets(db: Session, project_id: uuid.UUID) -> list[tuple]:
    """Site reports still awaiting the assigned Project Manager's verification.

    `review_status == "submitted"` is the waiting state; verifying or
    rejecting moves it out of this query, which is what stops the reminders.
    """
    project = db.get(Project, project_id)
    if not project or not project.project_manager_id:
        return []
    reports = db.query(SiteReport).filter(
        SiteReport.project_id == project_id,
        SiteReport.review_status == "submitted",
    ).all()
    return [
        ("SITE_REPORT", report.id, project.project_manager_id, "NORMAL",
         report.created_at, f"Site report {report.report_date}")
        for report in reports
        # A manager who filed the report themselves is not chased to verify it.
        if report.submitted_by_id != project.project_manager_id
    ]


def _consultation_targets(db: Session, project_id: uuid.UUID) -> list[tuple]:
    """Entity shares ("Ask for Opinion") where the recipient has not replied.

    A consultation is answered as soon as the recipient posts *anything* later
    in that conversation — that is the natural signal, and it means replying
    in the UI stops the reminders with no extra bookkeeping.
    """
    shares = db.query(Message).options(
        joinedload(Message.conversation).selectinload(Conversation.participants)
    ).join(Conversation, Conversation.id == Message.conversation_id).filter(
        Conversation.project_id == project_id,
        Message.shared_entity_type.isnot(None),
        Message.deleted_at.is_(None),
    ).all()
    if not shares:
        return []
    # One query for every reply that could answer any of these shares, instead
    # of one per share.
    conversation_ids = {share.conversation_id for share in shares}
    replies = db.query(Message.conversation_id, Message.sender_id, Message.created_at).filter(
        Message.conversation_id.in_(conversation_ids),
        Message.deleted_at.is_(None),
    ).all()

    targets: list[tuple] = []
    for share in shares:
        for participant in share.conversation.participants:
            if participant.user_id == share.sender_id:
                continue
            answered = any(
                conversation_id == share.conversation_id
                and sender_id == participant.user_id
                and created_at > share.created_at
                for conversation_id, sender_id, created_at in replies
            )
            if answered:
                continue
            targets.append((
                "CONSULTATION", share.id, participant.user_id, "NORMAL",
                share.created_at,
                f"{share.shared_entity_type.replace('_', ' ').title()} shared with you",
            ))
    return targets


def _issue_targets(db: Session, project_id: uuid.UUID) -> list[tuple]:
    """Unresolved issues that still need somebody to act.

    Severity drives the interval through the existing `ReminderRule` priority
    lookup, so a critical issue is chased sooner than a low one without any
    separate schedule. Low-severity issues are deliberately not chased at all:
    a daily nudge about every minor open issue is exactly the spam this system
    is meant to avoid.
    """
    project = db.get(Project, project_id)
    issues = db.query(Issue).filter(
        Issue.project_id == project_id,
        Issue.status.in_([IssueStatus.OPEN, IssueStatus.IN_PROGRESS]),
        Issue.severity.in_([IssueSeverity.HIGH, IssueSeverity.CRITICAL]),
    ).all()
    targets: list[tuple] = []
    for issue in issues:
        recipient = issue.assigned_to_id or (project.project_manager_id if project else None)
        if not recipient:
            continue
        priority = "CRITICAL" if issue.severity == IssueSeverity.CRITICAL else "HIGH"
        targets.append(("ISSUE", issue.id, recipient, priority, issue.created_at, issue.title))
    return targets


def evaluate_project_reminders(db: Session, project_id: uuid.UUID, *, actor_id: uuid.UUID | None = None,
                               now: datetime | None = None) -> dict:
    """Create the reminders that are due for one project. Safe to call repeatedly."""
    now = now or datetime.now(timezone.utc)
    targets = collect_targets(db, project_id)
    created = 0
    for target_type, target_id, recipient_id, priority, waiting_since, label in targets:
        rule = effective_rule(db, project_id, priority)
        if not rule.enabled:
            continue
        history = db.query(ReminderEvent).filter(
            ReminderEvent.target_type == target_type,
            ReminderEvent.target_id == target_id,
            ReminderEvent.recipient_id == recipient_id,
        ).order_by(ReminderEvent.sent_at.desc()).all()
        if not reminder_is_due(
            now=now, waiting_since=waiting_since,
            last_sent_at=history[0].sent_at if history else None,
            first_minutes=rule.first_reminder_minutes, repeat_minutes=rule.repeat_interval_minutes,
            sent_count=len(history), maximum=rule.maximum_reminders,
            quiet_start=rule.quiet_hours_start, quiet_end=rule.quiet_hours_end,
        ):
            continue
        sequence = len(history) + 1
        escalation = bool(sequence >= rule.maximum_reminders and rule.escalation_recipient_id)
        recipient = rule.escalation_recipient_id if escalation else recipient_id
        db.add(ReminderEvent(
            project_id=project_id, rule_id=rule.id if rule.id else None,
            target_type=target_type, target_id=target_id, recipient_id=recipient,
            event_type="ESCALATION" if escalation else "REMINDER",
            sequence_number=sequence, sent_at=now,
            metadata_json={"originalRecipientId": str(recipient_id)},
        ))
        notify(
            db, user_id=recipient, project_id=project_id,
            title=("Escalation: " if escalation else "Response reminder: ") + label,
            message=f"This {target_type.lower().replace('_', ' ')} is still waiting for action. Reminder {sequence}.",
            notification_type=NotificationType.SYSTEM,
            category=CATEGORY_REMINDER,
            priority=_reminder_priority(priority, sequence, rule.maximum_reminders, escalation),
            entity_type=target_type, entity_id=target_id, requires_action=True,
            # The ReminderEvent ledger above is the real idempotency guard (the
            # `reminder_is_due` check reads it), so the key here only has to
            # stop a duplicate *within* one sweep — hence the sequence number,
            # which legitimately differs for a genuine follow-up reminder.
            dedupe_key=f"reminder:{target_type}:{target_id}:{recipient}:{sequence}",
            message_key="reminder.escalation" if escalation else "reminder.waiting",
            message_params={"label": label, "sequence": sequence,
                            "target": target_type.lower().replace("_", " ")},
        )
        # The session runs with autoflush disabled, so without this the history
        # query above cannot see reminders written earlier in the same session
        # and would send the same nudge again. Idempotency must not depend on
        # the caller happening to commit between sweeps.
        db.flush()
        created += 1

    # Deadlines are evaluated on the calendar date, not on `now`: see the
    # docstring of `evaluate_task_deadlines`.
    created += evaluate_task_deadlines(db, project_id)

    if created:
        record_audit(
            db, actor_id=actor_id, action="reminders_dispatched", entity_type="project",
            entity_id=project_id, project_id=project_id,
            details={"count": created, "trigger": "MANUAL" if actor_id else "SCHEDULER"},
        )
    return {"created": created, "evaluated": len(targets), "generatedAt": now}


def _reminder_priority(base_priority: str, sequence: int, maximum: int, escalation: bool) -> str:
    """How loudly to present a reminder.

    Escalation is expressed as priority on a *new* notification rather than by
    editing the earlier one, so the user's history keeps saying what they were
    actually told at the time.
    """
    if escalation:
        return PRIORITY_CRITICAL
    if (base_priority or "").upper() == "CRITICAL":
        return PRIORITY_CRITICAL
    # The last permitted nudge is the loudest one the recipient will get.
    if sequence >= max(maximum, 1):
        return PRIORITY_IMPORTANT
    if (base_priority or "").upper() == "HIGH" or sequence > 1:
        return PRIORITY_IMPORTANT
    return PRIORITY_NORMAL


def evaluate_task_deadlines(db: Session, project_id: uuid.UUID, *, today: date | None = None) -> int:
    """Deadline warnings for one project's open tasks. Idempotent per stage.

    This replaces the old dashboard-triggered sync. Loading assignees and
    dependents eagerly keeps the sweep to a fixed number of queries instead of
    the per-task lazy loads the previous implementation performed.

    `today` is a calendar date, deliberately *not* derived from the sweep's UTC
    instant: `Task.planned_end_date` is a plain date entered in the project's
    own terms, and `datetime.now(timezone.utc).date()` disagrees with the
    server's calendar date for part of every day — which for a "due today"
    warning is a whole day wrong. The rest of the codebase compares planned
    dates against `date.today()`, and this stays consistent with it.
    """
    today = today or date.today()
    project = db.get(Project, project_id)
    if not project:
        return 0
    tasks = db.query(Task).options(
        selectinload(Task.assignees), selectinload(Task.dependents),
    ).filter(
        Task.project_id == project_id,
        Task.planned_end_date.isnot(None),
        Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
    ).all()
    created = 0
    for task in tasks:
        stage = deadline_stage(task, today)
        if not stage:
            continue
        stage_name, priority = stage
        priority = escalate_for_context(task, stage_name, priority)
        recipients = {assignee.id for assignee in task.assignees}
        # The manager is only pulled in once the date has actually passed —
        # an upcoming deadline is the assignee's business, a missed one is
        # the project's.
        if stage_name.startswith("OVERDUE") and project.project_manager_id:
            recipients.add(project.project_manager_id)
        created += notify_task_deadline(db, task, project, recipients, stage_name, priority)
    return created


def evaluate_all_projects(db: Session, *, now: datetime | None = None) -> dict:
    """Scheduler entry point. Each project is isolated: one failure never stops the rest."""
    now = now or datetime.now(timezone.utc)
    summary = {"projects": 0, "created": 0, "evaluated": 0, "failed": 0, "generatedAt": now}
    project_ids = [row[0] for row in db.query(Project.id).filter(
        Project.status.notin_([ProjectStatus.COMPLETED, ProjectStatus.CANCELLED]),
    ).all()]
    for project_id in project_ids:
        try:
            result = evaluate_project_reminders(db, project_id, actor_id=None, now=now)
            db.commit()
            summary["projects"] += 1
            summary["created"] += result["created"]
            summary["evaluated"] += result["evaluated"]
        except Exception:
            db.rollback()
            summary["failed"] += 1
    return summary
