from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
import uuid
from datetime import date, datetime, time, timezone

from app.db.database import get_db
from app.services.authorization import require
from app.models.user import User
from app.models.design_change import DesignChange, DesignChangeAffectedDiscipline
from app.schemas.design_change import DesignChangeOut, DesignChangeCreate
from app.core.deps import get_current_user, is_consultant_engineer, user_has_project_access, accessible_project_ids
from app.models.enums import DesignChangeStatus, UserRole
from app.models.attachment import Attachment
from app.models.project import Project, ProjectMember
from app.models.notification import Notification
from app.models.enums import NotificationType
from app.services.audit_service import record_audit

router = APIRouter(prefix="/design-changes", tags=["Design Changes"])


def _important_for_owner(query):
    return query.filter(or_(
        DesignChange.expected_cost_impact.isnot(None),
        DesignChange.expected_schedule_impact_days.isnot(None),
        DesignChange.status.in_([DesignChangeStatus.APPROVED, DesignChangeStatus.REJECTED, DesignChangeStatus.IMPLEMENTED]),
    ))

@router.get("", response_model=List[DesignChangeOut])
def list_design_changes(
    project_id: Optional[uuid.UUID] = None,
    status: Optional[DesignChangeStatus] = None,
    discipline: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    proposed_by_id: Optional[uuid.UUID] = None,
    has_attachments: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(DesignChange)
    if current_user.role != UserRole.ADMIN:
        accessible_ids = accessible_project_ids(db, current_user) or []
        query = query.filter(DesignChange.project_id.in_(accessible_ids))
    if current_user.role == UserRole.OWNER:
        query = _important_for_owner(query)
    if project_id:
        query = query.filter(DesignChange.project_id == project_id)
    if status:
        query = query.filter(DesignChange.status == status)
    effective_discipline = discipline
    # `User.role` is never literally CONSULTANT: `UserCreateByAdmin` persists
    # that request as ENGINEER with `engineer_affiliation="external_consultant"`
    # (see app.schemas.user, "persist the unified Engineer role"), so this must
    # check `is_consultant_engineer`, not the retired role value, to actually
    # auto-scope a Consultant Engineer's own list to their discipline.
    if is_consultant_engineer(current_user) and current_user.engineer_profile:
        effective_discipline = current_user.engineer_profile.discipline.value
    if effective_discipline:
        affected_ids = db.query(DesignChangeAffectedDiscipline.design_change_id).filter(
            DesignChangeAffectedDiscipline.discipline == effective_discipline
        )
        query = query.filter((DesignChange.source_discipline == effective_discipline) | DesignChange.id.in_(affected_ids))
    if date_from:
        query = query.filter(DesignChange.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        query = query.filter(DesignChange.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if proposed_by_id:
        query = query.filter(DesignChange.proposed_by_id == proposed_by_id)
    attachment_exists = db.query(Attachment.id).filter(Attachment.entity_type == "DESIGN_CHANGE", Attachment.entity_id == DesignChange.id).exists()
    if has_attachments is not None:
        query = query.filter(attachment_exists if has_attachments else ~attachment_exists)
    items = query.order_by(DesignChange.created_at.desc()).all()
    counts = dict(db.query(Attachment.entity_id, func.count(Attachment.id)).filter(
        Attachment.entity_type == "DESIGN_CHANGE", Attachment.entity_id.in_([item.id for item in items])
    ).group_by(Attachment.entity_id).all()) if items else {}
    for item in items:
        item.attachment_count = counts.get(item.id, 0)
    return items

@router.get("/project/{project_id}", response_model=List[DesignChangeOut])
def get_design_changes_by_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = db.query(DesignChange).filter(DesignChange.project_id == project_id)
    if current_user.role == UserRole.OWNER:
        query = _important_for_owner(query)
    return query.all()

@router.get("/{change_id}", response_model=DesignChangeOut)
def get_design_change_by_id(
    change_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    change = db.query(DesignChange).filter(DesignChange.id == change_id).first()
    if not change:
        raise HTTPException(status_code=404, detail="Design change not found")
    if not user_has_project_access(db, current_user, change.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this design change")
    if current_user.role == UserRole.OWNER and not _important_for_owner(
        db.query(DesignChange).filter(DesignChange.id == change.id)
    ).first():
        raise HTTPException(status_code=403, detail="This design change is not classified as owner-relevant")
    if is_consultant_engineer(current_user) and current_user.engineer_profile:
        disciplines = {change.source_discipline, *(item.discipline for item in change.affected_disciplines)}
        if current_user.engineer_profile.discipline.value not in disciplines:
            raise HTTPException(status_code=403, detail="This design change is outside your discipline")
    change.attachment_count = db.query(Attachment).filter(Attachment.entity_type == "DESIGN_CHANGE", Attachment.entity_id == change.id).count()
    return change

@router.post("", response_model=DesignChangeOut)
def create_design_change(
    change_data: DesignChangeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require(db, current_user, "design_change.propose", change_data.project_id)
    if not user_has_project_access(db, current_user, change_data.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    new_change = DesignChange(
        project_id=change_data.project_id,
        task_id=change_data.task_id,
        title=change_data.title,
        description=change_data.description,
        reason=change_data.reason,
        related_drawings=change_data.related_drawings,
        expected_cost_impact=change_data.expected_cost_impact,
        expected_schedule_impact_days=change_data.expected_schedule_impact_days,
        source_discipline=change_data.source_discipline,
        proposed_by_id=current_user.id,
        status=DesignChangeStatus.PROPOSED
    )
    db.add(new_change)
    db.flush()
    # Create affected discipline records
    for discipline in change_data.affected_disciplines:
        aff = DesignChangeAffectedDiscipline(
            design_change_id=new_change.id,
            discipline=discipline,
            acknowledged=False
        )
        db.add(aff)
    project = db.get(Project, change_data.project_id)
    relevant_disciplines = {change_data.source_discipline, *change_data.affected_disciplines}
    memberships = db.query(ProjectMember).filter(ProjectMember.project_id == change_data.project_id,
        ProjectMember.is_active == True).all()
    recipients = {project.project_manager_id if project else None}
    for member in memberships:
        profile = member.user.engineer_profile
        if member.role_on_project in {UserRole.ENGINEER, UserRole.CONSULTANT} and profile and profile.discipline.value in relevant_disciplines:
            recipients.add(member.user_id)
        if member.is_site_engineer:
            recipients.add(member.user_id)
    for recipient in recipients - {None}:
        db.add(Notification(user_id=recipient, title="New Design Change",
                            message=f"A new {new_change.source_discipline} Design Change was created for {project.name if project else 'the project'}: {new_change.title}",
                            type=NotificationType.DESIGN_CHANGE, project_id=new_change.project_id,
                            related_entity_type="DESIGN_CHANGE", related_entity_id=new_change.id))
    record_audit(db, actor_id=current_user.id, action="created", entity_type="design_change",
                 entity_id=new_change.id, project_id=new_change.project_id,
                 details={"disciplines": sorted(relevant_disciplines)})
    db.commit()
    db.refresh(new_change)
    return new_change

@router.put("/{change_id}/acknowledge/{discipline}", response_model=DesignChangeOut)
def acknowledge_design_change(
    change_id: uuid.UUID,
    discipline: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    change = db.query(DesignChange).filter(DesignChange.id == change_id).first()
    if not change:
        raise HTTPException(status_code=404, detail="Design change not found")
    if not user_has_project_access(db, current_user, change.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this design change")
    if current_user.engineer_profile and current_user.engineer_profile.discipline.value != discipline:
        raise HTTPException(status_code=403, detail="You cannot acknowledge another discipline")
        
    aff = db.query(DesignChangeAffectedDiscipline).filter(
        DesignChangeAffectedDiscipline.design_change_id == change_id,
        DesignChangeAffectedDiscipline.discipline == discipline
    ).first()
    
    if not aff:
        raise HTTPException(status_code=404, detail="Affected discipline not found for this design change")
        
    aff.acknowledged = True
    aff.acknowledged_by_id = current_user.id
    
    # Discipline acknowledgement completes technical coordination but does not approve the change.
    all_aff = db.query(DesignChangeAffectedDiscipline).filter(
        DesignChangeAffectedDiscipline.design_change_id == change_id
    ).all()
    
    if all(a.acknowledged for a in all_aff):
        change.status = DesignChangeStatus.UNDER_REVIEW
        
    record_audit(db, actor_id=current_user.id, action="discipline_acknowledged", entity_type="design_change",
                 entity_id=change.id, project_id=change.project_id, details={"discipline": discipline})
    db.commit()
    db.refresh(change)
    return change

@router.put("/{change_id}/approve", response_model=DesignChangeOut)
def approve_design_change(
    change_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    change = db.query(DesignChange).filter(DesignChange.id == change_id).first()
    if not change:
        raise HTTPException(status_code=404, detail="Design change not found")
        
    # The capability is configurable. Project access is re-checked inside
    # `require`, and the discipline restriction below still applies on top.
    require(db, current_user, "design_change.approve", change.project_id)
    # "Official approval rests with the assigned consultant alone" (see the
    # catalogue entry): the catalogue default now covers ENGINEER broadly, the
    # same shape as `ifc.upload`/`ifc.view`, because a Consultant Engineer's
    # `User.role` is ENGINEER, not the retired UserRole.CONSULTANT value — so
    # this hard gate is what actually keeps a non-consultant (e.g. Main
    # Contractor) Engineer from approving, matching `reject_design_change`.
    if not is_consultant_engineer(current_user):
        raise HTTPException(status_code=403, detail="Only an assigned consultant can approve this design change")
    if current_user.engineer_profile:
        relevant = {change.source_discipline, *(item.discipline for item in change.affected_disciplines)}
        if current_user.engineer_profile.discipline.value not in relevant:
            raise HTTPException(status_code=403, detail="This design change is outside your discipline")
    change.status = DesignChangeStatus.APPROVED
    change.approved_by_id = current_user.id
    project = db.get(Project, change.project_id)
    recipients = {change.proposed_by_id, project.project_manager_id if project else None, project.owner_id if project else None}
    for recipient in recipients - {None, current_user.id}:
        db.add(Notification(
            user_id=recipient, title="Design change approved",
            message=f"{change.title} was approved.",
            type=NotificationType.DESIGN_CHANGE, project_id=change.project_id,
            related_entity_type="DESIGN_CHANGE", related_entity_id=change.id,
        ))
    record_audit(db, actor_id=current_user.id, action="approved", entity_type="design_change", entity_id=change.id, project_id=change.project_id)
    db.commit()
    db.refresh(change)
    return change

@router.put("/{change_id}/reject", response_model=DesignChangeOut)
def reject_design_change(
    change_id: uuid.UUID,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    change = db.get(DesignChange, change_id)
    if not change:
        raise HTTPException(status_code=404, detail="Design change not found")
    if not is_consultant_engineer(current_user) or not user_has_project_access(db, current_user, change.project_id):
        raise HTTPException(status_code=403, detail="Only an assigned consultant can reject this design change")
    if current_user.engineer_profile:
        relevant = {change.source_discipline, *(item.discipline for item in change.affected_disciplines)}
        if current_user.engineer_profile.discipline.value not in relevant:
            raise HTTPException(status_code=403, detail="This design change is outside your discipline")
    change.status = DesignChangeStatus.REJECTED
    change.approved_by_id = current_user.id
    change.review_notes = data.get("reviewNotes") or data.get("review_notes")
    project = db.get(Project, change.project_id)
    recipients = {change.proposed_by_id, project.project_manager_id if project else None, project.owner_id if project else None}
    for recipient in recipients - {None, current_user.id}:
        db.add(Notification(
            user_id=recipient, title="Design change rejected",
            message=f"{change.title} was rejected.",
            type=NotificationType.DESIGN_CHANGE, project_id=change.project_id,
            related_entity_type="DESIGN_CHANGE", related_entity_id=change.id,
        ))
    record_audit(db, actor_id=current_user.id, action="rejected", entity_type="design_change", entity_id=change.id, project_id=change.project_id)
    db.commit()
    db.refresh(change)
    return change

@router.delete("/{change_id}")
def delete_design_change(change_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    change = db.get(DesignChange, change_id)
    if not change:
        raise HTTPException(status_code=404, detail="Design change not found")
    if change.proposed_by_id != current_user.id or change.status not in {DesignChangeStatus.PROPOSED, DesignChangeStatus.REJECTED}:
        raise HTTPException(status_code=403, detail="Only the proposer can delete a proposed or rejected change")
    db.delete(change); db.commit()
    return {"message": "Design change deleted"}
