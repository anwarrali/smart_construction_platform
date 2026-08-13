"""Reminder evaluation shared by the secured endpoint and the background scheduler.

The rules themselves (interval, maximum, quiet hours) already live in
`collaboration_policy.reminder_is_due`; this module owns *what* is waiting for
action, *who* must be reminded, and the idempotency that stops a reminder from
being sent twice for the same waiting state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.collaboration import MessageRecipientState, OwnerRequest, ReminderEvent, ReminderRule
from app.models.enums import NotificationType, ProjectStatus
from app.models.message import Message
from app.models.notification import Notification
from app.models.project import Project
from app.services.audit_service import record_audit
from app.services.collaboration_policy import reminder_is_due

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
    """Every item in one project still waiting on a named person."""
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
        db.add(Notification(
            user_id=recipient, project_id=project_id,
            title=("Escalation: " if escalation else "Response reminder: ") + label,
            message=f"This {target_type.lower().replace('_', ' ')} is still waiting for action. Reminder {sequence}.",
            type=NotificationType.SYSTEM, category="REMINDERS", requires_action=True,
            related_entity_type=target_type, related_entity_id=target_id,
        ))
        created += 1
    if created:
        record_audit(
            db, actor_id=actor_id, action="reminders_dispatched", entity_type="project",
            entity_id=project_id, project_id=project_id,
            details={"count": created, "trigger": "MANUAL" if actor_id else "SCHEDULER"},
        )
    return {"created": created, "evaluated": len(targets), "generatedAt": now}


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
