from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
import uuid

from app.core.config import settings
from app.db.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.schemas.device_token import (
    DeviceTokenOut,
    DeviceTokenRegister,
    DeviceTokenUnregister,
)
from app.schemas.notification import NotificationOut, NotificationResponse
from app.core.deps import get_current_user, user_has_project_access, is_main_contractor_engineer, is_consultant_engineer
from app.models.enums import NotificationStatus, NotificationType, UserRole
from app.services import device_token_service, notification_service
from app.services.realtime import EventType, publish_event

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
    project_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if project_id and not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    return {
        "count": notification_service.unread_count(
            db, user_id=current_user.id, project_id=project_id
        )
    }


# --- push device registration -----------------------------------------------
# Mounted under /notifications rather than a router of its own: a device token
# exists for exactly one reason, and keeping it here means one authentication
# story and one place to look. Both routes are scoped to the caller — the
# user id always comes from the access token, never from the request body, so
# there is no shape of request that registers or removes somebody else's
# device.


@router.post("/devices", response_model=DeviceTokenOut, status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceTokenRegister,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Register this device for push. Safe to call on every app start."""
    record = device_token_service.register_device(
        db,
        user_id=current_user.id,
        token=payload.token.strip(),
        platform=payload.platform,
        device_id=payload.device_id,
        device_name=payload.device_name,
        app_version=payload.app_version,
    )
    db.commit()
    db.refresh(record)
    return record


@router.get("/devices", response_model=List[DeviceTokenOut])
def list_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The caller's own registered devices. Never returns the tokens."""
    return device_token_service.list_devices(db, user_id=current_user.id)


@router.delete("/devices", status_code=status.HTTP_204_NO_CONTENT)
def unregister_device(
    payload: DeviceTokenUnregister,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire this device on sign-out, so the next user of it is not reached."""
    device_token_service.unregister_device(
        db,
        user_id=current_user.id,
        token=(payload.token or "").strip() or None,
        device_id=(payload.device_id or "").strip() or None,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- read state -------------------------------------------------------------
# PATCH is the correct verb for a partial state change and is what new clients
# should call. PUT is kept alongside it because the shipped web and Flutter
# clients call PUT today, and breaking installed apps to tidy a verb would be
# a poor trade. Both share one implementation.


def _mark_all_read(project_id, db: Session, current_user: User):
    if current_user.role == UserRole.ENGINEER and not project_id:
        raise HTTPException(status_code=400, detail="Engineer notification actions require a selected project")
    if project_id and not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    updated = notification_service.mark_all_as_read(
        db, user_id=current_user.id, project_id=project_id
    )
    if updated:
        # Targeted at this user only: their *other* open tabs need to drop
        # their unread badge too. Nobody else's count changed.
        publish_event(
            db, event_type=EventType.NOTIFICATION_UPDATED,
            user_id=current_user.id, project_id=project_id,
        )
    db.commit()
    return {"message": "All notifications marked as read", "updated": updated}


def _mark_read(notification_id: uuid.UUID, db: Session, current_user: User):
    # Ownership is enforced inside the UPDATE's WHERE clause, so a
    # notification belonging to somebody else is indistinguishable from one
    # that does not exist — which is the point.
    if not notification_service.mark_as_read(
        db, notification_id=notification_id, user_id=current_user.id
    ):
        raise HTTPException(status_code=404, detail="Notification not found")
    publish_event(
        db, event_type=EventType.NOTIFICATION_UPDATED,
        user_id=current_user.id, entity_type="NOTIFICATION", entity_id=notification_id,
    )
    db.commit()
    return {"message": "Notification marked as read"}


@router.patch("/read-all")
def mark_all_read_patch(
    project_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _mark_all_read(project_id, db, current_user)


@router.put("/read-all")
def mark_all_read(
    project_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return _mark_all_read(project_id, db, current_user)


@router.patch("/{notification_id}/read")
def mark_read_patch(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _mark_read(notification_id, db, current_user)


@router.put("/{notification_id}/read")
def mark_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return _mark_read(notification_id, db, current_user)


@router.get("/{notification_id}", response_model=NotificationOut)
def get_notification(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """One notification, for resolving a push tap into a destination.

    A client that was opened by a notification tap knows only the id, and both
    clients route from `relatedEntityType`/`relatedEntityId`/`projectId`. The
    user filter is part of the query, so this cannot be used to probe whether
    another user's notification id exists.
    """
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


# --- development-only test trigger ------------------------------------------


@router.post("/dev/test-notification", response_model=NotificationOut)
def send_test_notification(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a notification to **the caller only**, for wiring up push.

    Three separate things make this safe to have in the tree:

      * it is off unless NOTIFICATION_DEV_TEST_ENABLED is explicitly true, and
        that flag defaults to false — a production deployment that changes
        nothing gets a 404 here;
      * it requires a valid access token, like every other route;
      * the recipient is `current_user.id` and there is no parameter that can
        change it, so even with the flag on it cannot be used to send a
        notification to anybody else.

    A 404 rather than a 403 when disabled: an endpoint that is switched off
    should not confirm its own existence.
    """
    if not settings.NOTIFICATION_DEV_TEST_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")

    notification = notification_service.notify_user(
        db,
        user_id=current_user.id,
        title="Test notification",
        message=(
            "If you can see this in your notification centre and on your "
            "device, push delivery is working."
        ),
        notification_type=NotificationType.SYSTEM,
        category=notification_service.CATEGORY_SYSTEM,
        priority=notification_service.PRIORITY_NORMAL,
        message_key="dev.testNotification",
    )
    db.commit()
    db.refresh(notification)
    return notification
