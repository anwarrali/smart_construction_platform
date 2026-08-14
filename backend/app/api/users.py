from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
import uuid
from datetime import datetime, timezone

from app.db.database import get_db
from app.models.user import User, EngineerProfile
from app.models.project import Project, ProjectMember
from app.models.task import Task, TaskComment, task_assignees
from app.models.issue import Issue
from app.models.document import Document, MediaAsset
from app.models.site_report import SiteReport
from app.models.design_change import DesignChange
from app.models.message import Message
from app.models.attachment import Attachment
from app.models.cost_validation import CostValidation
from app.models.voice_recording import VoiceRecording
from app.models.enums import UserRole, UserStatus, EngineerDiscipline
from app.schemas.user import (
    UserOut,
    UserUpdate,
    UserAdminUpdate,
    ChangePasswordRequest,
    UserCreateByAdmin,
    UserCreateResponse,
    EngineerCreateRequest,
    OwnerCreateRequest,
)
from app.core.deps import get_current_user, require_can_create_user
from app.services.authorization import require_permission
from app.core.permissions import can_create_team_role, can_manage_all_users, is_engineer
from app.core.security import hash_password, verify_password
from app.services.user_service import create_provisioned_user, generate_temporary_password
from app.services.file_storage import save_upload
from app.services.audit_service import record_audit
from app.models.notification import Notification
from app.models.password_reset import PasswordResetToken
from app.models.enums import NotificationType
from sqlalchemy import or_

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserOut])
def list_users(
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("platform.manage_users")),
):
    query = db.query(User)
    if current_user.company_id:
        query = query.filter(User.company_id == current_user.company_id)

    if role:
        query = query.filter(User.role == role)
    if status:
        query = query.filter(User.status == status)
    if search:
        query = query.filter(User.full_name.ilike(f"%{search}%") | User.email.ilike(f"%{search}%"))
    return query.order_by(User.full_name).all()


@router.get("/search", response_model=List[UserOut])
def search_users(
    q: str,
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search existing company users by name or email (for assigning to projects)."""
    if current_user.role not in {UserRole.ADMIN, UserRole.PROJECT_MANAGER}:
        raise HTTPException(status_code=403, detail="Not authorized to search users")

    query = db.query(User).filter(
        User.status == UserStatus.ACTIVE,
        User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"),
    )
    if current_user.company_id:
        query = query.filter(User.company_id == current_user.company_id)
    if role:
        query = query.filter(User.role == role)
    elif current_user.role == UserRole.PROJECT_MANAGER:
        query = query.filter(User.role.in_([UserRole.ENGINEER, UserRole.CONSULTANT]))

    return query.limit(20).all()


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreateByAdmin,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a complete active user account with an administrator-supplied password."""
    if not can_create_team_role(current_user.role, user_data.role):
        raise HTTPException(
            status_code=403,
            detail=f"You are not authorized to create users with role '{user_data.role.value}'",
        )

    discipline = None
    employee_id = None
    if user_data.engineer_profile:
        discipline = user_data.engineer_profile.discipline
        employee_id = user_data.engineer_profile.employee_id

    try:
        user, _ = create_provisioned_user(
            db,
            creator=current_user,
            email=user_data.email,
            full_name=user_data.full_name,
            role=user_data.role,
            phone_number=user_data.phone_number,
            organization=user_data.organization,
            engineer_affiliation=user_data.engineer_affiliation,
            engineer_discipline=discipline,
            employee_id=employee_id,
            password=user_data.password,
            send_email=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = UserCreateResponse.model_validate(user)
    record_audit(db, actor_id=current_user.id, action="created", entity_type="user", entity_id=user.id,
                 details={"role": user.role.value, "engineer_affiliation": user.engineer_affiliation, "direct_account": True})
    db.commit()
    return response


@router.post("/engineers", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
def create_engineer(
    data: EngineerCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = UserRole.ENGINEER
    if not can_create_team_role(current_user.role, role):
        raise HTTPException(status_code=403, detail="Not authorized to create engineer accounts")

    try:
        user, temp_password = create_provisioned_user(
            db,
            creator=current_user,
            email=data.email,
            full_name=data.full_name,
            role=role,
            phone_number=data.phone_number,
            engineer_discipline=data.discipline,
            employee_id=data.employee_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = UserCreateResponse.model_validate(user)
    response.temporary_password = temp_password
    return response


@router.post("/owners", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
def create_owner(
    data: OwnerCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_create_team_role(current_user.role, UserRole.OWNER):
        raise HTTPException(status_code=403, detail="Not authorized to create owner accounts")

    try:
        user, temp_password = create_provisioned_user(
            db,
            creator=current_user,
            email=data.email,
            full_name=data.full_name,
            role=UserRole.OWNER,
            phone_number=data.phone_number,
            organization=data.organization,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = UserCreateResponse.model_validate(user)
    response.temporary_password = temp_password
    return response


@router.get("/profile", response_model=UserOut)
def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/profile", response_model=UserOut)
def update_profile(
    update_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if update_data.email is not None:
        existing = db.query(User).filter(User.email == update_data.email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = update_data.email

    if update_data.full_name is not None:
        current_user.full_name = update_data.full_name
    if update_data.phone_number is not None:
        current_user.phone_number = update_data.phone_number
    if update_data.avatar_url is not None:
        current_user.avatar_url = update_data.avatar_url
    if update_data.telegram_chat_id is not None:
        current_user.telegram_chat_id = update_data.telegram_chat_id
    if update_data.notify_by_email is not None:
        current_user.notify_by_email = update_data.notify_by_email
    if update_data.notify_by_telegram is not None:
        current_user.notify_by_telegram = update_data.notify_by_telegram

    if update_data.engineer_profile and current_user.engineer_profile:
        ep = current_user.engineer_profile
        ep.discipline = update_data.engineer_profile.discipline
        ep.license_number = update_data.engineer_profile.license_number
        ep.years_of_experience = update_data.engineer_profile.years_of_experience
        ep.can_act_as_project_manager = update_data.engineer_profile.can_act_as_project_manager
    elif update_data.engineer_profile:
        ep = EngineerProfile(
            user_id=current_user.id,
            discipline=update_data.engineer_profile.discipline,
            license_number=update_data.engineer_profile.license_number,
            years_of_experience=update_data.engineer_profile.years_of_experience,
            can_act_as_project_manager=update_data.engineer_profile.can_act_as_project_manager,
        )
        db.add(ep)

    db.commit()
    db.refresh(current_user)
    return current_user


@router.put("/change-password")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")

    current_user.hashed_password = hash_password(data.new_password)
    current_user.must_change_password = False
    if not current_user.invitation_accepted:
        current_user.invitation_accepted = True
    if current_user.status == UserStatus.PENDING:
        current_user.status = UserStatus.ACTIVE
    db.commit()
    return {"message": "Password updated successfully"}


@router.post("/avatar")
async def upload_avatar(
    avatar: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    avatar_url, _ = await save_upload(avatar, "avatars")
    current_user.avatar_url = avatar_url
    db.commit()
    return {"avatarUrl": avatar_url}


@router.get("/{user_id}", response_model=UserOut)
def get_user_by_id(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_manage_all_users(current_user.role) and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this user")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if current_user.company_id and user.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this user")
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user_by_admin(
    user_id: uuid.UUID,
    update_data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("platform.manage_users")),
):
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if current_user.company_id and user.company_id != current_user.company_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this user")

        if update_data.email is not None:
            normalized_email = update_data.email.lower().strip()
            existing = db.query(User).filter(User.email == normalized_email, User.id != user.id).first()
            if existing:
                raise HTTPException(status_code=400, detail="Email already in use")
            user.email = normalized_email
        if update_data.full_name is not None:
            user.full_name = update_data.full_name.strip()
        if update_data.phone_number is not None:
            user.phone_number = update_data.phone_number
        if update_data.organization is not None:
            user.organization = update_data.organization
        if update_data.status is not None:
            if user.id == current_user.id and update_data.status != UserStatus.ACTIVE:
                raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
            user.status = update_data.status
        if update_data.role is not None:
            if user.id == current_user.id and update_data.role != UserRole.ADMIN:
                raise HTTPException(status_code=400, detail="You cannot remove your own administrator role")
            user.role = UserRole.ENGINEER if update_data.role == UserRole.CONSULTANT else update_data.role

        if user.role == UserRole.ENGINEER:
            affiliation = update_data.engineer_affiliation or (
                user.engineer_affiliation
                if user.engineer_affiliation in {"internal_engineer", "main_contractor", "external_consultant"}
                else ("external_consultant" if update_data.role == UserRole.CONSULTANT else "internal_engineer")
            )
            if affiliation not in {"internal_engineer", "main_contractor", "external_consultant"}:
                raise HTTPException(status_code=400, detail="Unsupported Engineer organization side")
            user.engineer_affiliation = affiliation
        else:
            user.engineer_affiliation = None
        if user.role == UserRole.ENGINEER and user.engineer_affiliation == "external_consultant" and not (user.organization or "").strip():
            raise HTTPException(status_code=400, detail="External consultant company/organization is required")

        if user.role == UserRole.ENGINEER:
            if not update_data.engineer_profile and not user.engineer_profile:
                raise HTTPException(status_code=400, detail="Specialization is required for Engineer and Consultant users")
            if update_data.engineer_profile:
                if user.engineer_profile:
                    user.engineer_profile.discipline = update_data.engineer_profile.discipline
                    user.engineer_profile.license_number = update_data.engineer_profile.license_number
                    user.engineer_profile.years_of_experience = update_data.engineer_profile.years_of_experience
                    user.engineer_profile.employee_id = update_data.engineer_profile.employee_id
                    user.engineer_profile.can_act_as_project_manager = False
                else:
                    user.engineer_profile = EngineerProfile(
                        user_id=user.id,
                        discipline=update_data.engineer_profile.discipline,
                        license_number=update_data.engineer_profile.license_number,
                        years_of_experience=update_data.engineer_profile.years_of_experience,
                        employee_id=update_data.engineer_profile.employee_id,
                        can_act_as_project_manager=False,
                    )
        else:
            user.engineer_profile = None

        record_audit(db, actor_id=current_user.id, action="updated", entity_type="user", entity_id=user.id,
                     details={"fields": sorted(update_data.model_fields_set), "role": user.role.value})
        db.commit()
        db.refresh(user)
        return user
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Could not update user. Check role, specialization, and database migrations.") from exc


@router.put("/{user_id}/deactivate")
def deactivate_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("platform.manage_users")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    user.status = UserStatus.INACTIVE
    record_audit(db, actor_id=current_user.id, action="deactivated", entity_type="user", entity_id=user.id)
    db.commit()
    return {"message": "User deactivated successfully"}


@router.put("/{user_id}/activate")
def activate_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("platform.manage_users")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = UserStatus.ACTIVE
    db.add(Notification(user_id=user.id, title="Account reactivated", message="Your account access was restored by an administrator.", type=NotificationType.SYSTEM))
    record_audit(db, actor_id=current_user.id, action="reactivated", entity_type="user", entity_id=user.id)
    db.commit()
    return {"message": "User activated successfully"}


@router.delete("/{user_id}")
def permanently_delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("platform.manage_users")),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot permanently delete your own administrator account")

    detachable_links = {
        "ownedProjects": db.query(Project.id).filter(Project.owner_id == user.id).count(),
        "managedProjects": db.query(Project.id).filter(Project.project_manager_id == user.id).count(),
        "projectMemberships": db.query(ProjectMember.id).filter(ProjectMember.user_id == user.id).count(),
        "taskAssignments": db.query(task_assignees.c.task_id).filter(task_assignees.c.user_id == user.id).count(),
    }
    blockers = {
        "created tasks": db.query(Task.id).filter(Task.created_by_id == user.id).first(),
        "task comments": db.query(TaskComment.id).filter(TaskComment.author_id == user.id).first(),
        "issues": db.query(Issue.id).filter(or_(Issue.raised_by_id == user.id, Issue.assigned_to_id == user.id)).first(),
        "documents or media": db.query(Document.id).filter(Document.uploaded_by_id == user.id).first()
            or db.query(MediaAsset.id).filter(MediaAsset.uploaded_by_id == user.id).first(),
        "site reports": db.query(SiteReport.id).filter(SiteReport.submitted_by_id == user.id).first(),
        "design changes": db.query(DesignChange.id).filter(DesignChange.proposed_by_id == user.id).first(),
        "messages": db.query(Message.id).filter(or_(Message.sender_id == user.id, Message.receiver_id == user.id)).first(),
        "attachments": db.query(Attachment.id).filter(Attachment.uploaded_by_id == user.id).first(),
        "cost records": db.query(CostValidation.id).filter(CostValidation.requested_by_id == user.id).first(),
        "voice recordings": db.query(VoiceRecording.id).filter(VoiceRecording.recorded_by_id == user.id).first(),
    }
    active_blockers = [label for label, found in blockers.items() if found]
    if active_blockers:
        raise HTTPException(
            status_code=409,
            detail=(
                "This user is linked to project history and cannot be permanently deleted safely. "
                f"Deactivate the account instead. Linked data: {', '.join(active_blockers)}."
            ),
        )

    record_audit(
        db,
        actor_id=current_user.id,
        action="permanently_deleted",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email, "role": user.role.value, "detachedLinks": detachable_links},
    )
    db.delete(user)
    db.commit()
    return {"message": "User permanently deleted"}

@router.post("/{user_id}/reset-password")
def admin_reset_password(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("platform.manage_users")),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    temporary_password = generate_temporary_password()
    user.hashed_password = hash_password(temporary_password)
    user.must_change_password = True
    user.invitation_accepted = False
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: datetime.now(timezone.utc)}, synchronize_session=False)
    db.add(Notification(user_id=user.id, title="Password reset by administrator",
                        message="Use the temporary password provided by your administrator. You must change it after signing in.",
                        type=NotificationType.SYSTEM))
    record_audit(db, actor_id=current_user.id, action="password_reset", entity_type="user", entity_id=user.id)
    db.commit()
    return {"temporaryPassword": temporary_password, "mustChangePassword": True}
