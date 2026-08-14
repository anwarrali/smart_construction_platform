"""Persistent, reviewable IFC ↔ project intelligence APIs."""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.tasks import _is_project_manager, _next_task_code
from app.core.deps import get_current_user
from app.db.database import get_db
from app.models.enums import IssueSeverity, IssueStatus, NotificationType, TaskPriority, TaskStatus, UserRole
from app.models.ifc import AIInsight, IFCElement, IFCEntityLink, IFCModelVersion
from app.models.issue import Issue
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.schemas.ai_insight import AIInsightCreateTask, AIInsightOut, AIInsightReview
from app.models.collaboration import AIInsightSource
from app.services.ai_insight_engine import alignment_facts, run_project_intelligence
from app.services.audit_service import record_audit
from app.services.authorization import require
from app.services.collaboration_policy import choose_discipline_assignee
from app.services.ifc_policy import can_ifc

router = APIRouter(prefix="/projects/{project_id}/ai-intelligence", tags=["AI Intelligence"])


def _require(db: Session, user: User, project_id: uuid.UUID, permission: str = "VIEW") -> None:
    if not can_ifc(db, user, project_id, permission):
        raise HTTPException(status_code=403, detail="Project intelligence permission required")


def _insight(db: Session, project_id, insight_id) -> AIInsight:
    item=db.query(AIInsight).filter(AIInsight.id==insight_id,AIInsight.project_id==project_id).first()
    if not item:raise HTTPException(status_code=404,detail="AI insight not found")
    return item


def _current_version(db: Session, project_id: uuid.UUID) -> IFCModelVersion | None:
    """The revision the review queue is about: the active one, else the newest processed one."""
    return db.query(IFCModelVersion).filter(
        IFCModelVersion.project_id == project_id,
        IFCModelVersion.processing_status.in_(["READY", "READY_WITH_WARNINGS"]),
    ).order_by(IFCModelVersion.is_active.desc(), IFCModelVersion.created_at.desc()).first()


def _scope_to_current_revision(db: Session, project_id: uuid.UUID, query):
    """Hide findings that belong to a superseded IFC revision.

    Both insight engines fingerprint a finding per model revision, so uploading a
    new revision re-detects the same condition and stores it again against the
    new revision id. The rows are distinct records of distinct revisions, but the
    review queue showed all of them at once: several cards with an identical
    title, of which only one changed state when it was reviewed. Resolving one
    left an identical card behind and put another copy in the resolved view,
    which read as a duplicate being created by the action.

    Only the current revision is actionable, so that is what the queue shows.
    Insights that are not tied to a revision at all remain visible, and the
    superseded rows are preserved and still reachable with an explicit
    `model_revision_id` or `include_superseded`.
    """
    version = _current_version(db, project_id)
    if version is None:
        return query
    return query.filter(or_(
        AIInsight.model_revision_id == version.id,
        AIInsight.model_revision_id.is_(None),
    ))


def _notify_issue_owners(db: Session, issue: Issue, *, actor_id: uuid.UUID, discipline: str | None) -> None:
    """Tell the people who have to act on a newly raised issue.

    An issue promoted out of an AI insight was previously written to the
    database silently: it appeared in the Issues list, but nobody was told it
    existed. Routing reuses the same discipline rule the owner-request workflow
    uses, so the engineer responsible for that discipline is notified, together
    with the project manager who is accountable for it — and nobody else.
    """
    project = db.get(Project, issue.project_id)
    memberships = db.query(ProjectMember).filter(
        ProjectMember.project_id == issue.project_id, ProjectMember.is_active == True,  # noqa: E712
    ).all()
    candidates = [{
        "id": member.user_id, "role": member.role_on_project.value,
        "discipline": member.project_discipline or (
            member.user.engineer_profile.discipline.value if member.user.engineer_profile else None
        ), "active": member.is_active,
    } for member in memberships]
    assignee = choose_discipline_assignee(discipline, candidates) if discipline else None

    recipients = {value for value in (assignee, project.project_manager_id if project else None) if value}
    for user_id in recipients - {actor_id}:
        db.add(Notification(
            user_id=user_id, project_id=issue.project_id,
            title=f"Issue raised: {issue.title}"[:250],
            message="An AI insight was reviewed and promoted to a project issue. Engineering review is required.",
            type=NotificationType.SYSTEM, category="ISSUES",
            requires_action=user_id == assignee,
            related_entity_type="ISSUE", related_entity_id=issue.id,
            action_url=f"/projects/{issue.project_id}/issues?issueId={issue.id}",
        ))


@router.get("/insights", response_model=list[AIInsightOut])
def list_insights(project_id:uuid.UUID,status:str|None=None,severity:str|None=None,category:str|None=None,model_revision_id:uuid.UUID|None=None,
                  include_superseded:bool=False,
                  page:int=Query(1,ge=1),page_size:int=Query(100,ge=1,le=200),db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    _require(db,current_user,project_id);q=db.query(AIInsight).filter(AIInsight.project_id==project_id)
    # The two engines label an untouched finding "OPEN" and "NEW" respectively.
    # They mean the same thing to a reviewer, so the one filter option matches both.
    if status:q=q.filter(AIInsight.status.in_(["OPEN","NEW"] if status.upper() in {"OPEN","NEW"} else [status.upper()]))
    if severity:q=q.filter(AIInsight.severity==severity.upper())
    if category:q=q.filter(AIInsight.category==category.upper())
    if model_revision_id:q=q.filter(AIInsight.model_revision_id==model_revision_id)
    elif not include_superseded:q=_scope_to_current_revision(db,project_id,q)
    return q.order_by(AIInsight.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()


@router.get("/overview")
def intelligence_overview(project_id:uuid.UUID,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    _require(db,current_user,project_id)
    # The headline counts have to describe the same rows the review queue lists,
    # otherwise "3 open insights" sits above a list showing one.
    items=_scope_to_current_revision(db,project_id,db.query(AIInsight).filter(AIInsight.project_id==project_id)).all()
    version=_current_version(db,project_id)
    alignment=alignment_facts(db,project_id,version) if version else None
    open_items=[item for item in items if item.status in {"OPEN","NEW","ACKNOWLEDGED","UNDER_REVIEW","CONFIRMED"}]
    return {"openInsights":len(open_items),"severityCounts":dict(Counter(item.severity for item in open_items)),
            "categoryCounts":dict(Counter(item.category for item in open_items)),"statusCounts":dict(Counter(item.status for item in items)),
            "alignment":alignment,"latestRevision":{"id":str(version.id),"revisionCode":version.revision_code,"title":version.title} if version else None,
            "engineeringReviewNotice":"Automated analysis — engineering review required."}


@router.get("/insights/{insight_id}/sources")
def insight_sources(project_id: uuid.UUID, insight_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id); _insight(db, project_id, insight_id)
    return db.query(AIInsightSource).filter(AIInsightSource.project_id == project_id,
        AIInsightSource.insight_id == insight_id).order_by(AIInsightSource.created_at).all()


@router.post("/run")
def run_intelligence(project_id:uuid.UUID,version_id:uuid.UUID|None=None,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    _require(db,current_user,project_id,"REVIEW_SUGGESTION")
    result=run_project_intelligence(db,project_id,version_id)
    record_audit(db,actor_id=current_user.id,action="ai_intelligence_run",entity_type="project",entity_id=project_id,project_id=project_id,details=result);db.commit()
    return result


@router.patch("/insights/{insight_id}",response_model=AIInsightOut)
def review_insight(project_id:uuid.UUID,insight_id:uuid.UUID,payload:AIInsightReview,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    _require(db,current_user,project_id,"REVIEW_FINDING")
    require(db,current_user,"ai.review_insight",project_id)
    item=_insight(db,project_id,insight_id);status=payload.status.upper()
    aliases={"UNDER_REVIEW":"ACKNOWLEDGED","CONFIRMED":"ACKNOWLEDGED","DISMISSED":"FALSE_POSITIVE"}
    status=aliases.get(status,status)
    if status not in {"OPEN","ACKNOWLEDGED","RESOLVED","FALSE_POSITIVE"}:raise HTTPException(status_code=400,detail="Unsupported review status")
    # Repeating a review is a no-op, not a second event. Without this a second
    # Resolve on the same finding wrote another audit record and moved
    # resolved_at, so the activity trail showed the same insight being resolved
    # over and over.
    if item.status==status and item.review_note==payload.note:return item
    item.status=status;item.review_note=payload.note;item.reviewed_by_id=current_user.id;item.reviewed_at=datetime.now(timezone.utc)
    if status=="RESOLVED":item.resolved_at=datetime.now(timezone.utc)
    record_audit(db,actor_id=current_user.id,action="ai_insight_reviewed",entity_type="ai_insight",entity_id=item.id,project_id=project_id,details={"status":status,"note":payload.note});db.commit();db.refresh(item);return item


@router.post("/insights/{insight_id}/create-issue",status_code=201)
def insight_to_issue(project_id:uuid.UUID,insight_id:uuid.UUID,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    _require(db,current_user,project_id,"REVIEW_FINDING")
    require(db,current_user,"ai.promote_insight",project_id)
    item=_insight(db,project_id,insight_id)
    if item.applied_entity_id:raise HTTPException(status_code=409,detail="This insight has already created a project work item")
    severity=IssueSeverity.HIGH if item.severity in {"CRITICAL","WARNING"} else IssueSeverity.MEDIUM
    issue=Issue(project_id=project_id,title=item.title,description=f"{item.description}\n\nEvidence: {item.evidence_json}\n\nAutomated analysis — engineering review required.\nInsight: {item.id}",category="AI_INTELLIGENCE",severity=severity,status=IssueStatus.OPEN,raised_by_id=current_user.id,affects_schedule=item.category=="REVISION")
    db.add(issue);db.flush();item.applied_entity_type="ISSUE";item.applied_entity_id=issue.id;item.status="CONFIRMED";item.reviewed_by_id=current_user.id;item.reviewed_at=datetime.now(timezone.utc)
    for element_id in (item.affected_json or {}).get("elements",[])[:200]:
        try: eid=uuid.UUID(element_id)
        except (ValueError,TypeError):continue
        if db.get(IFCElement,eid):db.add(IFCEntityLink(project_id=project_id,version_id=item.model_revision_id,ifc_element_id=eid,linked_entity_type="ISSUE",linked_entity_id=issue.id,link_type="AI_INSIGHT",source="USER",confidence=1,confirmed_by_id=current_user.id,confirmed_at=datetime.now(timezone.utc)))
    _notify_issue_owners(db,issue,actor_id=current_user.id,discipline=(item.evidence_json or {}).get("discipline"))
    record_audit(db,actor_id=current_user.id,action="issue_created_from_ai_insight",entity_type="issue",entity_id=issue.id,project_id=project_id,details={"insightId":str(item.id)});db.commit();return {"id":issue.id,"title":issue.title}


@router.post("/insights/{insight_id}/create-task",status_code=201)
def insight_to_task(project_id:uuid.UUID,insight_id:uuid.UUID,payload:AIInsightCreateTask,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    _require(db,current_user,project_id,"REVIEW_SUGGESTION")
    if not _is_project_manager(db,current_user,project_id):raise HTTPException(status_code=403,detail="Only the assigned Project Manager can create a task from an insight")
    item=_insight(db,project_id,insight_id)
    if item.category!="SUGGESTED_TASK":raise HTTPException(status_code=400,detail="Only reviewed task suggestions can create tasks")
    if item.applied_entity_id:raise HTTPException(status_code=409,detail="This suggestion has already created a task")
    evidence=item.evidence_json or {};title=(payload.title or item.title).strip();discipline=payload.discipline or evidence.get("discipline")
    task=Task(project_id=project_id,task_code=_next_task_code(db,project_id),name=title,description=payload.description or item.description,discipline=discipline,priority=TaskPriority.MEDIUM,status=TaskStatus.BACKLOG,created_by_id=current_user.id,progress_percentage=0,review_required=True)
    db.add(task);db.flush();item.applied_entity_type="TASK";item.applied_entity_id=task.id;item.status="CONFIRMED";item.reviewed_by_id=current_user.id;item.reviewed_at=datetime.now(timezone.utc)
    for element_id in (item.affected_json or {}).get("elements",[])[:500]:
        try:eid=uuid.UUID(element_id)
        except (ValueError,TypeError):continue
        if db.get(IFCElement,eid):db.add(IFCEntityLink(project_id=project_id,version_id=item.model_revision_id,ifc_element_id=eid,linked_entity_type="TASK",linked_entity_id=task.id,link_type="AI_SUGGESTION",source="USER",confidence=1,confirmed_by_id=current_user.id,confirmed_at=datetime.now(timezone.utc)))
    record_audit(db,actor_id=current_user.id,action="task_created_from_ai_insight",entity_type="task",entity_id=task.id,project_id=project_id,details={"insightId":str(item.id)});db.commit();return {"id":task.id,"taskCode":task.task_code,"name":task.name}
