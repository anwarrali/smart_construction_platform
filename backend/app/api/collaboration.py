"""Human-accountable owner requests, visits, reminders, action center, and activity."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import accessible_project_ids, get_current_user, user_has_project_access
from app.db.database import get_db
from app.models.audit_log import AuditLog
from app.models.collaboration import (
    AIInsightSource, MessageRecipientState, OwnerRequest, ReminderEvent,
    ReminderRule, SiteVisit, SiteVisitParticipant,
)
from app.models.design_change import DesignChange, DesignChangeAffectedDiscipline
from app.models.enums import DesignChangeStatus, IssueStatus, NotificationType, TaskStatus, UserRole
from app.models.ifc import AIInsight
from app.models.issue import Issue
from app.models.message import Message
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.site_report import SiteReport
from app.models.user import User
from app.schemas.collaboration import (
    ConvertRequestToDesignChange, MessageAccountabilityAction, OwnerRequestAction,
    OwnerRequestCreate, OwnerRequestOut, ReminderRuleUpsert, SiteVisitCreate,
    SiteVisitOut, SiteVisitUpdate,
)
from app.services.audit_service import record_audit
from app.services.collaboration_policy import (
    assert_human_authority, can_transition_owner_request, choose_discipline_assignee,
)
from app.services.reminder_service import evaluate_project_reminders
from app.services.scheduler import status as scheduler_status
from app.services.messaging_authorization import active_project_participant_ids


router = APIRouter(tags=["Project Collaboration"])
ACTIVE_REQUEST_STATUSES = {"SUBMITTED", "ASSIGNED", "UNDER_REVIEW", "NEEDS_CLARIFICATION", "ACCEPTED", "CONVERTED_TO_DESIGN_CHANGE"}
TERMINAL_REQUEST_STATUSES = {"REJECTED", "COMPLETED"}
VISIT_STATUSES = {"SCHEDULED", "CONFIRMED", "COMPLETED", "CANCELLED", "RESCHEDULED"}


def _project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    value = db.get(Project, project_id)
    if not value:
        raise HTTPException(status_code=404, detail="Project not found")
    if not user_has_project_access(db, user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    return value


def _request(db: Session, user: User, request_id: uuid.UUID) -> OwnerRequest:
    value = db.get(OwnerRequest, request_id)
    if not value:
        raise HTTPException(status_code=404, detail="Owner request not found")
    _project(db, user, value.project_id)
    return value


def _visit_payload(value: SiteVisit) -> dict:
    return {key: getattr(value, key) for key in (
        "id", "project_id", "engineer_id", "created_by_id", "title", "scheduled_start",
        "scheduled_end", "visit_type", "location", "notes", "status", "reschedule_reason",
        "completed_at", "cancelled_at", "created_at", "updated_at",
    )} | {"participant_ids": [item.user_id for item in value.participants]}


def _notify(db: Session, *, user_id, project_id, title, message, category, entity_type, entity_id,
            requires_action=False, action_url=None):
    db.add(Notification(
        user_id=user_id, project_id=project_id, title=title, message=message,
        type=NotificationType.SYSTEM, category=category, requires_action=requires_action,
        related_entity_type=entity_type, related_entity_id=entity_id, action_url=action_url,
    ))


def _route_owner_request(db: Session, item: OwnerRequest) -> uuid.UUID | None:
    memberships = db.query(ProjectMember).filter(
        ProjectMember.project_id == item.project_id, ProjectMember.is_active == True,
    ).all()
    candidates = [{
        "id": member.user_id, "role": member.role_on_project.value,
        "discipline": member.project_discipline or (
            member.user.engineer_profile.discipline.value if member.user.engineer_profile else None
        ), "active": member.is_active,
    } for member in memberships]
    return choose_discipline_assignee(item.discipline, candidates)


@router.post("/owner-requests", response_model=OwnerRequestOut, status_code=201)
def create_owner_request(payload: OwnerRequestCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _project(db, current_user, payload.project_id)
    if current_user.role not in {UserRole.OWNER, UserRole.PROJECT_MANAGER, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Only an owner or project manager can submit a client request")
    if current_user.role == UserRole.OWNER and project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Owners can submit requests only for their own project")
    item = OwnerRequest(
        project_id=payload.project_id, created_by_id=current_user.id,
        title=payload.title.strip(), description=payload.description.strip(),
        category=payload.category.upper(), discipline=payload.discipline.lower() if payload.discipline else None,
        floor=payload.floor, room=payload.room, related_document_id=payload.related_document_id,
        priority=payload.priority.upper(), due_at=payload.due_at,
    )
    db.add(item); db.flush()
    item.assigned_to_id = _route_owner_request(db, item)
    item.status = "ASSIGNED" if item.assigned_to_id else "SUBMITTED"
    recipients = {value for value in (item.assigned_to_id, project.project_manager_id) if value and value != current_user.id}
    for user_id in recipients:
        _notify(db, user_id=user_id, project_id=item.project_id, title=f"Owner request: {item.title}",
                message=f"{item.category.replace('_', ' ').title()} request requires engineering review.",
                category="REQUESTS", entity_type="OWNER_REQUEST", entity_id=item.id,
                requires_action=user_id == item.assigned_to_id, action_url=f"/requests/{item.id}")
    record_audit(db, actor_id=current_user.id, action="owner_request_submitted", entity_type="owner_request",
                 entity_id=item.id, project_id=item.project_id,
                 details={"category": item.category, "discipline": item.discipline, "assignedToId": item.assigned_to_id})
    db.commit(); db.refresh(item); return item


@router.get("/owner-requests", response_model=list[OwnerRequestOut])
def list_owner_requests(project_id: uuid.UUID | None = None, status: str | None = None,
                        priority: str | None = None, discipline: str | None = None, assigned_to_me: bool = False,
                        db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(OwnerRequest)
    accessible = accessible_project_ids(db, current_user)
    if accessible is not None:
        query = query.filter(OwnerRequest.project_id.in_(accessible))
    if project_id:
        _project(db, current_user, project_id); query = query.filter(OwnerRequest.project_id == project_id)
    if status: query = query.filter(OwnerRequest.status == status.upper())
    if priority: query = query.filter(OwnerRequest.priority == priority.upper())
    if discipline: query = query.filter(OwnerRequest.discipline == discipline.lower())
    if assigned_to_me: query = query.filter(OwnerRequest.assigned_to_id == current_user.id)
    return query.order_by(OwnerRequest.created_at.desc()).limit(500).all()


@router.get("/owner-requests/{request_id}", response_model=OwnerRequestOut)
def get_owner_request(request_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _request(db, current_user, request_id)


@router.patch("/owner-requests/{request_id}", response_model=OwnerRequestOut)
def update_owner_request(request_id: uuid.UUID, payload: OwnerRequestAction,
                         db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = _request(db, current_user, request_id); project = db.get(Project, item.project_id)
    is_manager = current_user.role == UserRole.ADMIN or project.project_manager_id == current_user.id
    is_assignee = item.assigned_to_id == current_user.id
    is_requester = item.created_by_id == current_user.id
    if payload.assigned_to_id is not None:
        if not is_manager: raise HTTPException(status_code=403, detail="Only project management can reassign requests")
        if payload.assigned_to_id not in active_project_participant_ids(db, item.project_id):
            raise HTTPException(status_code=400, detail="Assignee must be an active project participant")
        item.assigned_to_id = payload.assigned_to_id
    if payload.status:
        target = payload.status.upper()
        if not can_transition_owner_request(item.status, target):
            raise HTTPException(status_code=409, detail=f"Cannot move request from {item.status} to {target}")
        if target == "UNDER_REVIEW" and not (is_assignee or is_manager or (is_requester and item.status == "NEEDS_CLARIFICATION")):
            raise HTTPException(status_code=403, detail="You cannot start this review")
        if target in {"ACCEPTED", "REJECTED", "COMPLETED"} and not (is_assignee or is_manager):
            raise HTTPException(status_code=403, detail="Engineering review authority is required")
        if target == "NEEDS_CLARIFICATION" and not (is_assignee or is_manager):
            raise HTTPException(status_code=403, detail="Engineering review authority is required")
        item.status = target
    if payload.response_text is not None:
        if not (is_assignee or is_manager): raise HTTPException(status_code=403, detail="Only the assigned engineer or PM can respond")
        item.response_text = payload.response_text; item.responded_at = datetime.now(timezone.utc)
    if payload.clarification_text is not None:
        if not (is_requester or is_assignee or is_manager): raise HTTPException(status_code=403, detail="You cannot add clarification")
        item.clarification_text = payload.clarification_text
    if (is_assignee or is_manager) and item.acknowledged_at is None:
        item.acknowledged_at = datetime.now(timezone.utc)
    record_audit(db, actor_id=current_user.id, action="owner_request_updated", entity_type="owner_request",
                 entity_id=item.id, project_id=item.project_id, details={"status": item.status, "assignedToId": item.assigned_to_id})
    db.commit(); db.refresh(item); return item


@router.post("/owner-requests/{request_id}/convert-to-design-change", status_code=201)
def convert_owner_request(request_id: uuid.UUID, payload: ConvertRequestToDesignChange,
                          db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = _request(db, current_user, request_id); project = db.get(Project, item.project_id)
    if not assert_human_authority("HUMAN"):
        raise HTTPException(status_code=403, detail="AI cannot create an official design decision")
    if current_user.role == UserRole.WORKER or not (current_user.role == UserRole.ADMIN or project.project_manager_id == current_user.id or item.assigned_to_id == current_user.id):
        raise HTTPException(status_code=403, detail="Assigned engineering or project management authority is required")
    if item.status not in {"UNDER_REVIEW", "ACCEPTED"}:
        raise HTTPException(status_code=409, detail="Request must be under review or accepted before conversion")
    if item.converted_design_change_id:
        raise HTTPException(status_code=409, detail="Request has already been converted")
    discipline = (item.discipline or "architectural").lower()
    change = DesignChange(
        project_id=item.project_id, owner_request_id=item.id, title=payload.title or item.title,
        description=payload.description or item.description,
        reason=payload.reason or f"Created after human review of owner request {item.id}",
        source_discipline=discipline, proposed_by_id=current_user.id, status=DesignChangeStatus.PROPOSED,
    )
    db.add(change); db.flush()
    for value in set(payload.affected_disciplines or [discipline]):
        db.add(DesignChangeAffectedDiscipline(design_change_id=change.id, discipline=value.lower(), acknowledged=False))
    item.converted_design_change_id = change.id; item.status = "CONVERTED_TO_DESIGN_CHANGE"
    record_audit(db, actor_id=current_user.id, action="owner_request_converted_to_design_change",
                 entity_type="design_change", entity_id=change.id, project_id=item.project_id,
                 details={"ownerRequestId": str(item.id), "status": "proposed", "requiresApproval": True})
    db.commit(); return {"id": change.id, "status": change.status, "ownerRequestId": item.id,
                         "message": "Design change proposed; the existing human approval workflow still applies."}


def _visit_conflicts(db: Session, engineer_id, start, end, exclude_id=None):
    query = db.query(SiteVisit).filter(
        SiteVisit.engineer_id == engineer_id, SiteVisit.status.notin_(["CANCELLED", "COMPLETED"]),
        SiteVisit.scheduled_start < end, SiteVisit.scheduled_end > start,
    )
    if exclude_id: query = query.filter(SiteVisit.id != exclude_id)
    return query.order_by(SiteVisit.scheduled_start).all()


@router.post("/site-visits", response_model=SiteVisitOut, status_code=201)
def create_site_visit(payload: SiteVisitCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _project(db, current_user, payload.project_id)
    if current_user.role not in {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.ENGINEER}:
        raise HTTPException(status_code=403, detail="Engineering or project management authority is required")
    engineer_id = payload.engineer_id or current_user.id
    if current_user.role == UserRole.ENGINEER and engineer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Engineers can schedule only their own visits")
    if engineer_id not in active_project_participant_ids(db, payload.project_id):
        raise HTTPException(status_code=400, detail="Engineer must be an active project participant")
    conflicts = _visit_conflicts(db, engineer_id, payload.scheduled_start, payload.scheduled_end)
    if conflicts and not payload.allow_conflict:
        raise HTTPException(status_code=409, detail={"message": "Site visit conflicts with an existing visit", "conflicts": [str(x.id) for x in conflicts]})
    participant_ids = set(payload.participant_ids)
    if not participant_ids.issubset(active_project_participant_ids(db, payload.project_id)):
        raise HTTPException(status_code=400, detail="All participants must belong to this project")
    item = SiteVisit(project_id=payload.project_id, engineer_id=engineer_id, created_by_id=current_user.id,
                     title=payload.title, scheduled_start=payload.scheduled_start, scheduled_end=payload.scheduled_end,
                     visit_type=payload.visit_type.upper(), location=payload.location or project.location, notes=payload.notes)
    db.add(item); db.flush(); now = datetime.now(timezone.utc)
    for user_id in participant_ids:
        db.add(SiteVisitParticipant(site_visit_id=item.id, user_id=user_id, notified_at=now))
        if user_id != current_user.id:
            _notify(db, user_id=user_id, project_id=item.project_id, title=f"Site visit scheduled: {item.title}",
                    message=f"Visit scheduled for {item.scheduled_start.isoformat()}.", category="SITE_VISITS",
                    entity_type="SITE_VISIT", entity_id=item.id, action_url=f"/schedule?visit={item.id}")
    record_audit(db, actor_id=current_user.id, action="site_visit_scheduled", entity_type="site_visit",
                 entity_id=item.id, project_id=item.project_id, details={"start": item.scheduled_start, "participants": list(participant_ids)})
    db.commit(); db.refresh(item); return _visit_payload(item)


@router.get("/site-visits", response_model=list[SiteVisitOut])
def list_site_visits(project_id: uuid.UUID | None = None, engineer_id: uuid.UUID | None = None,
                     date_from: datetime | None = None, date_to: datetime | None = None,
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(SiteVisit); accessible = accessible_project_ids(db, current_user)
    if accessible is not None: query = query.filter(SiteVisit.project_id.in_(accessible))
    if project_id: _project(db, current_user, project_id); query = query.filter(SiteVisit.project_id == project_id)
    if engineer_id: query = query.filter(SiteVisit.engineer_id == engineer_id)
    if date_from: query = query.filter(SiteVisit.scheduled_end >= date_from)
    if date_to: query = query.filter(SiteVisit.scheduled_start <= date_to)
    return [_visit_payload(item) for item in query.order_by(SiteVisit.scheduled_start).limit(1000).all()]


@router.patch("/site-visits/{visit_id}", response_model=SiteVisitOut)
def update_site_visit(visit_id: uuid.UUID, payload: SiteVisitUpdate,
                      db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.get(SiteVisit, visit_id)
    if not item: raise HTTPException(status_code=404, detail="Site visit not found")
    project = _project(db, current_user, item.project_id)
    if not (current_user.role == UserRole.ADMIN or current_user.id in {item.engineer_id, project.project_manager_id}):
        raise HTTPException(status_code=403, detail="You cannot change this visit")
    old_start, old_end, old_status = item.scheduled_start, item.scheduled_end, item.status
    start, end = payload.scheduled_start or item.scheduled_start, payload.scheduled_end or item.scheduled_end
    if end <= start: raise HTTPException(status_code=400, detail="scheduledEnd must be after scheduledStart")
    conflicts = _visit_conflicts(db, item.engineer_id, start, end, item.id)
    if conflicts and not payload.allow_conflict:
        raise HTTPException(status_code=409, detail={"message": "Site visit conflicts with an existing visit", "conflicts": [str(x.id) for x in conflicts]})
    changed_time = (start, end) != (old_start, old_end)
    item.scheduled_start, item.scheduled_end = start, end
    if changed_time: item.status = "RESCHEDULED"; item.reschedule_reason = payload.reschedule_reason
    if payload.status:
        status = payload.status.upper()
        if status not in VISIT_STATUSES: raise HTTPException(status_code=400, detail="Unsupported visit status")
        item.status = status
        if status == "COMPLETED": item.completed_at = datetime.now(timezone.utc)
        if status == "CANCELLED": item.cancelled_at = datetime.now(timezone.utc)
    if payload.notes is not None: item.notes = payload.notes
    if payload.participant_ids is not None:
        ids = set(payload.participant_ids)
        if not ids.issubset(active_project_participant_ids(db, item.project_id)):
            raise HTTPException(status_code=400, detail="All participants must belong to this project")
        item.participants.clear(); db.flush()
        for user_id in ids: item.participants.append(SiteVisitParticipant(user_id=user_id))
    verb = "cancelled" if item.status == "CANCELLED" else "rescheduled" if changed_time else "updated"
    for participant in item.participants:
        if participant.user_id != current_user.id:
            _notify(db, user_id=participant.user_id, project_id=item.project_id, title=f"Site visit {verb}: {item.title}",
                    message=f"Current schedule: {item.scheduled_start.isoformat()}.", category="SITE_VISITS",
                    entity_type="SITE_VISIT", entity_id=item.id, action_url=f"/schedule?visit={item.id}")
    record_audit(db, actor_id=current_user.id, action=f"site_visit_{verb}", entity_type="site_visit", entity_id=item.id,
                 project_id=item.project_id, details={"oldStart": old_start, "newStart": item.scheduled_start, "oldStatus": old_status, "newStatus": item.status})
    db.commit(); db.refresh(item); return _visit_payload(item)


@router.get("/site-visits/{visit_id}/report-prefill")
def site_visit_report_prefill(visit_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.get(SiteVisit, visit_id)
    if not item: raise HTTPException(status_code=404, detail="Site visit not found")
    _project(db, current_user, item.project_id)
    return {"siteVisitId": item.id, "projectId": item.project_id, "engineerId": item.engineer_id,
            "reportDate": item.scheduled_start.date(), "visitType": item.visit_type,
            "summaryText": f"{item.visit_type.replace('_', ' ').title()}: {item.title}"}


@router.post("/messages/{message_id}/accountability")
def update_message_accountability(message_id: uuid.UUID, payload: MessageAccountabilityAction,
                                  db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    message = db.get(Message, message_id)
    state = db.query(MessageRecipientState).filter(MessageRecipientState.message_id == message_id,
                                                     MessageRecipientState.user_id == current_user.id).first()
    if not message or not state: raise HTTPException(status_code=404, detail="Message accountability record not found")
    action = payload.action.upper(); now = datetime.now(timezone.utc)
    if action == "READ": state.read_at = state.read_at or now; state.response_status = "READ"
    elif action == "ACKNOWLEDGE": state.read_at = state.read_at or now; state.acknowledged_at = now; state.response_status = "ACKNOWLEDGED"
    elif action == "RESPONDED": state.responded_at = now; state.response_status = "RESPONDED"
    elif action == "RESOLVED": state.resolved_at = now; state.response_status = "RESOLVED"
    else: raise HTTPException(status_code=400, detail="Unsupported accountability action")
    record_audit(db, actor_id=current_user.id, action=f"message_{action.lower()}", entity_type="message",
                 entity_id=message.id, project_id=message.conversation.project_id, details={"status": state.response_status})
    db.commit(); return {"messageId": message.id, "status": state.response_status, "readAt": state.read_at,
                         "acknowledgedAt": state.acknowledged_at, "respondedAt": state.responded_at}


@router.put("/projects/{project_id}/reminder-rules")
def upsert_reminder_rule(project_id: uuid.UUID, payload: ReminderRuleUpsert,
                         db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _project(db, current_user, project_id)
    if not (current_user.role == UserRole.ADMIN or project.project_manager_id == current_user.id):
        raise HTTPException(status_code=403, detail="Only project management can configure reminders")
    rule = db.query(ReminderRule).filter(ReminderRule.project_id == project_id,
        ReminderRule.target_type == payload.target_type.upper(), ReminderRule.priority == payload.priority.upper()).first()
    if not rule:
        rule = ReminderRule(project_id=project_id, target_type=payload.target_type.upper(), priority=payload.priority.upper())
        db.add(rule)
    for key, value in payload.model_dump(exclude={"target_type", "priority"}).items(): setattr(rule, key, value)
    record_audit(db, actor_id=current_user.id, action="reminder_rule_configured", entity_type="reminder_rule",
                 entity_id=rule.id, project_id=project_id, details=payload.model_dump())
    db.commit(); db.refresh(rule); return rule


@router.post("/projects/{project_id}/reminders/run")
def run_reminders(project_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Manual sweep. The scheduler runs the same evaluation automatically."""
    project = _project(db, current_user, project_id)
    if not (current_user.role == UserRole.ADMIN or project.project_manager_id == current_user.id):
        raise HTTPException(status_code=403, detail="Only project management can run reminders")
    result = evaluate_project_reminders(db, project_id, actor_id=current_user.id)
    db.commit()
    return result


@router.get("/reminders/scheduler-status")
def reminder_scheduler_status(current_user: User = Depends(get_current_user)):
    if current_user.role not in {UserRole.ADMIN, UserRole.PROJECT_MANAGER}:
        raise HTTPException(status_code=403, detail="Only project management can inspect the scheduler")
    return scheduler_status()


@router.get("/my-action-center")
def my_action_center(project_id: uuid.UUID | None = None, priority: str | None = None,
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    accessible = accessible_project_ids(db, current_user); ids = accessible
    if project_id: _project(db, current_user, project_id); ids = [project_id]
    request_q = db.query(OwnerRequest).filter(OwnerRequest.assigned_to_id == current_user.id,
                                              OwnerRequest.status.in_(ACTIVE_REQUEST_STATUSES))
    if ids is not None: request_q = request_q.filter(OwnerRequest.project_id.in_(ids))
    if priority: request_q = request_q.filter(OwnerRequest.priority == priority.upper())
    messages = db.query(MessageRecipientState).filter(MessageRecipientState.user_id == current_user.id,
        MessageRecipientState.response_status.in_(["UNREAD", "READ", "NEEDS_RESPONSE", "ACKNOWLEDGED"])).all()
    notification_q = db.query(Notification).filter(Notification.user_id == current_user.id, Notification.requires_action == True, Notification.is_read == False)
    if ids is not None: notification_q = notification_q.filter(or_(Notification.project_id.in_(ids), Notification.project_id.is_(None)))
    visits_q = db.query(SiteVisit).filter(SiteVisit.engineer_id == current_user.id, SiteVisit.scheduled_start >= datetime.now(timezone.utc), SiteVisit.status.notin_(["CANCELLED", "COMPLETED"]))
    if ids is not None: visits_q = visits_q.filter(SiteVisit.project_id.in_(ids))
    ai_q = db.query(AIInsight).filter(AIInsight.status.in_(["NEW", "OPEN", "UNDER_REVIEW"]))
    if ids is not None: ai_q = ai_q.filter(AIInsight.project_id.in_(ids))
    task_q = db.query(Task).filter(Task.status == TaskStatus.UNDER_REVIEW)
    if ids is not None: task_q = task_q.filter(Task.project_id.in_(ids))
    requests = request_q.order_by(OwnerRequest.due_at.asc().nullslast(), OwnerRequest.created_at).limit(200).all()
    return {
        "generatedAt": datetime.now(timezone.utc),
        "counts": {"needsMyResponse": len(messages) + len(requests), "ownerRequests": len(requests),
                   "requiresActionNotifications": notification_q.count(), "upcomingSiteVisits": visits_q.count(),
                   "aiAlertsRequiringReview": ai_q.count(), "tasksUnderReview": task_q.count()},
        "ownerRequests": requests, "messageAccountability": [{"messageId": x.message_id, "status": x.response_status,
            "reminderCount": x.reminder_count} for x in messages[:200]],
        "upcomingSiteVisits": [_visit_payload(x) for x in visits_q.order_by(SiteVisit.scheduled_start).limit(50).all()],
        "notifications": notification_q.order_by(Notification.created_at.desc()).limit(100).all(),
    }


@router.get("/projects/{project_id}/activity")
def project_activity(project_id: uuid.UUID, limit: int = Query(default=100, ge=1, le=500),
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _project(db, current_user, project_id)
    rows = db.query(AuditLog).filter(AuditLog.project_id == project_id).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [{"id": row.id, "occurredAt": row.created_at, "action": row.action, "entityType": row.entity_type,
             "entityId": row.entity_id, "actorId": row.actor_id,
             "details": json.loads(row.details) if row.details else {}} for row in rows]


@router.get("/projects/{project_id}/communication-analytics")
def communication_analytics(project_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _project(db, current_user, project_id)
    requests = db.query(OwnerRequest).filter(OwnerRequest.project_id == project_id).all()
    answered = [x for x in requests if x.responded_at]
    response_hours = [(x.responded_at - x.created_at).total_seconds() / 3600 for x in answered]
    by_discipline = {}
    for item in requests: by_discipline[item.discipline or "general"] = by_discipline.get(item.discipline or "general", 0) + 1
    pending_messages = db.query(MessageRecipientState).join(Message).filter(
        Message.conversation.has(project_id=project_id), Message.requires_response == True,
        MessageRecipientState.response_status.notin_(["RESPONDED", "RESOLVED"])).count()
    unread_critical = db.query(MessageRecipientState).join(Message).filter(
        Message.conversation.has(project_id=project_id), Message.priority == "CRITICAL",
        MessageRecipientState.read_at.is_(None)).count()
    return {"ownerRequestCount": len(requests), "unansweredRequests": sum(x.status in ACTIVE_REQUEST_STATUSES and not x.responded_at for x in requests),
            "averageOwnerRequestResponseHours": round(sum(response_hours) / len(response_hours), 2) if response_hours else None,
            "requestsByDiscipline": by_discipline, "unansweredImportantMessages": pending_messages,
            "unreadCriticalMessages": unread_critical, "calculation": "DETERMINISTIC_DATABASE_QUERY"}


@router.get("/projects/{project_id}/digest")
def project_digest(project_id: uuid.UUID, period: str = "weekly", db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _project(db, current_user, project_id)
    from datetime import timedelta
    days = 1 if period.lower() == "daily" else 7
    since = datetime.now(timezone.utc) - timedelta(days=days)
    verified_tasks = db.query(Task).filter(Task.project_id == project_id, Task.status == TaskStatus.DONE,
                                           Task.review_status == "approved", Task.updated_at >= since).count()
    delayed_tasks = db.query(Task).filter(Task.project_id == project_id, Task.planned_end_date < datetime.now(timezone.utc).date(),
                                          Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED])).count()
    approved_changes = db.query(DesignChange).filter(DesignChange.project_id == project_id,
        DesignChange.status == DesignChangeStatus.APPROVED, DesignChange.updated_at >= since).count()
    new_issues = db.query(Issue).filter(Issue.project_id == project_id, Issue.created_at >= since).count()
    resolved_issues = db.query(Issue).filter(Issue.project_id == project_id,
        Issue.status.in_([IssueStatus.RESOLVED, IssueStatus.CLOSED]), Issue.updated_at >= since).count()
    reports = db.query(SiteReport).filter(SiteReport.project_id == project_id, SiteReport.created_at >= since).count()
    visits = db.query(SiteVisit).filter(SiteVisit.project_id == project_id, SiteVisit.status == "COMPLETED",
                                       SiteVisit.completed_at >= since).count()
    answered_requests = db.query(OwnerRequest).filter(OwnerRequest.project_id == project_id,
        OwnerRequest.responded_at >= since).count()
    metrics = {"verifiedTasksCompleted": verified_tasks, "delayedTasks": delayed_tasks,
               "approvedDesignChanges": approved_changes, "newIssues": new_issues,
               "resolvedIssues": resolved_issues, "siteReportsAdded": reports,
               "siteVisitsCompleted": visits, "ownerRequestsAnswered": answered_requests}
    summary = (f"{verified_tasks} tasks were completed and verified; {delayed_tasks} tasks are delayed. "
               f"{approved_changes} design changes were approved, {new_issues} issues were opened, and "
               f"{answered_requests} owner requests were answered.")
    return {"period": period.lower(), "since": since, "generatedAt": datetime.now(timezone.utc),
            "metrics": metrics, "summary": summary, "metricSource": "DETERMINISTIC_DATABASE_QUERY",
            "aiGeneratedMetrics": False, "officialProgressUsesVerifiedDataOnly": True}
