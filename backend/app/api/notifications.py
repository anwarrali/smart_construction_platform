from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
import uuid

from app.db.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.schemas.notification import NotificationOut, NotificationResponse
from app.core.deps import get_current_user, user_has_project_access, is_main_contractor_engineer, is_consultant_engineer
from app.models.enums import NotificationStatus, NotificationType, UserRole

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("", response_model=NotificationResponse)
def list_notifications(
    page: int = 1,
    limit: int = 20,
    project_id: Optional[uuid.UUID] = None,
    unread: Optional[bool] = None,
    notification_type: Optional[NotificationType] = None,
    category: Optional[str] = None,
    requires_action: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    if current_user.role == UserRole.ENGINEER:
        if not (is_main_contractor_engineer(current_user) or is_consultant_engineer(current_user)):
            raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
        if not project_id:
            raise HTTPException(status_code=400, detail="Engineer notification queries require a selected project")
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if project_id:
        if not user_has_project_access(db, current_user, project_id):
            raise HTTPException(status_code=403, detail="You do not have access to this project")
        query = query.filter(Notification.project_id == project_id)
    if unread is not None:
        query = query.filter(Notification.is_read == (not unread))
    if notification_type:
        query = query.filter(Notification.type == notification_type)
    if category:
        query = query.filter(Notification.category == category.upper())
    if requires_action is not None:
        query = query.filter(Notification.requires_action == requires_action)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            Notification.title.ilike(term),
            Notification.message.ilike(term),
        ))
    query = query.order_by(Notification.created_at.desc())
    total = query.count()
    
    offset = (page - 1) * limit
    notifications = query.offset(offset).limit(limit).all()
    
    return {
        "items": notifications,
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": (total + limit - 1) // limit,
    }

@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()
    return {"count": count}

@router.put("/read-all")
def mark_all_read(
    project_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role == UserRole.ENGINEER and not project_id:
        raise HTTPException(status_code=400, detail="Engineer notification actions require a selected project")
    query = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    )
    if project_id:
        if not user_has_project_access(db, current_user, project_id):
            raise HTTPException(status_code=403, detail="You do not have access to this project")
        query = query.filter(Notification.project_id == project_id)
    query.update({Notification.is_read: True, Notification.status: NotificationStatus.READ}, synchronize_session=False)
    db.commit()
    return {"message": "All notifications marked as read"}

@router.put("/{notification_id}/read")
def mark_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = True
    notification.status = NotificationStatus.READ
    db.commit()
    return {"message": "Notification marked as read"}
