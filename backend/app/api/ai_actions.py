import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, user_has_project_access
from app.db.database import get_db
from app.models.ai_governance import AIActionVersion
from app.models.enums import UserRole
from app.models.project import Project
from app.models.user import User
from app.schemas.ai_action import AIActionPage, AIActionRevertRequest, AIActionRevertResult
from app.services.ai_action_history_service import revert_action, undo_status


router = APIRouter(prefix="/ai/actions", tags=["AI Action History"])


def _action_or_404(db: Session, action_id: uuid.UUID) -> AIActionVersion:
    action = db.get(AIActionVersion, action_id)
    if not action:
        raise HTTPException(status_code=404, detail="AI action not found")
    return action


def _can_view_project_actions(db: Session, user: User, project_id: uuid.UUID) -> bool:
    project = db.get(Project, project_id)
    return bool(
        user.role == UserRole.ADMIN
        or (project and project.project_manager_id == user.id)
        or (project and project.owner_id == user.id)
    )


def _serialize(db: Session, action: AIActionVersion) -> dict:
    available, reason = undo_status(db, action)
    return {
        **{column.name: getattr(action, column.name) for column in AIActionVersion.__table__.columns},
        "undo_available": available,
        "undo_reason": reason,
    }


@router.get("", response_model=AIActionPage)
def list_ai_actions(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Project access is required")
    query = db.query(AIActionVersion).filter(AIActionVersion.project_id == project_id)
    if not _can_view_project_actions(db, current_user, project_id):
        query = query.filter(AIActionVersion.actor_user_id == current_user.id)
    total = query.count()
    items = query.order_by(AIActionVersion.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_serialize(db, item) for item in items], "page": page, "page_size": page_size, "total": total}


@router.get("/{action_id}")
def get_ai_action(
    action_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    action = _action_or_404(db, action_id)
    if not user_has_project_access(db, current_user, action.project_id):
        raise HTTPException(status_code=403, detail="Project access is required")
    if action.actor_user_id != current_user.id and not _can_view_project_actions(db, current_user, action.project_id):
        raise HTTPException(status_code=403, detail="This action is not visible to the current user")
    return _serialize(db, action)


@router.post("/{action_id}/revert", response_model=AIActionRevertResult)
def revert_ai_action(
    action_id: uuid.UUID,
    payload: AIActionRevertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    action = _action_or_404(db, action_id)
    reverted = revert_action(
        db,
        action=action,
        actor=current_user,
        request_id=payload.request_id,
        reason=payload.reason,
    )
    return {"action": _serialize(db, reverted), "message": "A compensating revert was applied; complete history was preserved."}


@router.post("/revert-last", response_model=AIActionRevertResult)
def revert_last_ai_action(
    project_id: uuid.UUID,
    payload: AIActionRevertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    action = db.query(AIActionVersion).filter(
        AIActionVersion.project_id == project_id,
        AIActionVersion.actor_user_id == current_user.id,
        AIActionVersion.result == "APPLIED",
        AIActionVersion.undo_policy == "AUTOMATIC_PROGRESS_COMPENSATION",
    ).order_by(AIActionVersion.created_at.desc()).first()
    if not action:
        raise HTTPException(status_code=409, detail="No automatically reversible AI action is available")
    reverted = revert_action(db, action=action, actor=current_user, request_id=payload.request_id, reason=payload.reason)
    return {"action": _serialize(db, reverted), "message": "The latest eligible AI progress action was reverted."}
