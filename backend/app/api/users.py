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
from app.models.message import Conversation, Message
from app.models.attachment import Attachment
from app.models.cost_validation import CostValidation
from app.models.voice_recording import VoiceRecording
from app.models.field_submission import FieldSubmission
from app.models.ifc import IFCComparison, IFCModelGroup, IFCModelVersion
from app.models.ingestion import IngestedFile
from app.models.rag_job import RagIndexJob
from app.models.collaboration import OwnerRequest, SiteVisit
from app.models.voice_analysis import VoiceAnalysis
from app.models.voice_action import VoiceExecutionLog
from app.models.ai_governance import AIActionVersion
from app.models.enums import UserRole, UserStatus, EngineerDiscipline
from app.schemas.user import (
    UserOut,
    UserUpdate,
    UserAdminUpdate,
    ChangePasswordRequest,
    UserCreateByAdmin,
    UserCreateResponse,
)
from app.core.deps import get_current_user
from app.models.rbac import Discipline, Role
from app.services import rbac
from app.services.authorization import has_permission, require, require_permission
from app.core.permissions import is_engineer
from app.core.security import hash_password, verify_password
from app.services.user_service import create_provisioned_user, generate_temporary_password
from app.services.file_storage import save_upload
from app.services.audit_service import record_audit
from app.services.step_up_service import require_step_up
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
    # This search exists to staff projects, so it follows the permission that
    # staffs them. `project.manage_members` is project-scoped; asked without a
    # project it answers "could this person manage a team anywhere", which is
    # the right question for a directory lookup that precedes choosing one.
    if not (
        has_permission(db, current_user, "project.manage_members")
        or has_permission(db, current_user, "platform.manage_users")
    ):
        raise HTTPException(status_code=403, detail="Not authorized to search users")

    query = db.query(User).filter(
        User.status == UserStatus.ACTIVE,
        User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"),
    )
    if current_user.company_id:
        query = query.filter(User.company_id == current_user.company_id)
    if role:
        query = query.filter(User.role == role)
    else:
        # Everybody an office may staff onto a project, by the same predicate
        # the candidate list and the assignment endpoint use. It used to narrow
        # to two retired enum values, and only when the *searcher* happened to
        # be a PROJECT_MANAGER — so the same query returned different people
        # depending on a job title.
        query = query.filter(rbac.staffable_filter(db))

    return query.limit(20).all()


def _requested_org_role(db: Session, role_id: uuid.UUID) -> Role:
    """The office role this request names, or a 400 explaining why not.

    Three refusals, and each one is a rule the office cannot configure around:
    the role has to exist and be active, it has to belong to this office (or be
    a shared template), and it has to be one accounts may be created under at
    all — which excludes the archived field-staff role that retired worker
    accounts sit on. That last check is what keeps Worker unreachable through
    the new provisioning path as well as the old one.
    """
    office = rbac.ensure_tenant_organization(db)
    role = db.get(Role, role_id)
    if role is None or not role.is_active:
        raise HTTPException(status_code=400, detail="That office role does not exist")
    if role.organization_id is not None and role.organization_id != office.id:
        raise HTTPException(status_code=400, detail="That role belongs to another office")
    if not role.legacy_role:
        raise HTTPException(
            status_code=400,
            detail=f"Accounts cannot be created under the '{role.name_en}' role",
        )
    return role


def _requested_disciplines(db: Session, discipline_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Validate the disciplines a request asks for, preserving their order.

    Order matters only because the first is recorded as primary — the one
    shown when a single discipline has to be named. It carries no authority.
    """
    if not discipline_ids:
        return []
    office = rbac.ensure_tenant_organization(db)
    found = {
        row.id for row in db.query(Discipline).filter(
            Discipline.id.in_(discipline_ids),
            Discipline.is_active.is_(True),
            or_(
                Discipline.organization_id.is_(None),
                Discipline.organization_id == office.id,
            ),
        ).all()
    }
    missing = [str(item) for item in discipline_ids if item not in found]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or inactive discipline: {', '.join(missing)}",
        )
    return list(discipline_ids)


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreateByAdmin,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an active account under one of the office's configured roles.

    Two paths, and the difference is what the request names. With `orgRoleId`,
    the account is created under a role the office maintains. Without it, the
    retired `role` enum path still works for a client that has not been updated.

    **Both are now gated by the same permission.** The legacy path used to ask
    `can_create_team_role(current_user.role, user_data.role)`, which resolved
    from the retired enum and admitted nobody but an ADMIN — so the two branches
    of one endpoint answered to two different authorities, and an office that
    granted `platform.manage_users` to a role of its own found it worked on one
    and not the other. The check is hoisted above the branch to make that
    single answer visible rather than repeated.

    What the retired function *also* did — refuse `WORKER` by omitting it from a
    set — is not an authorization question and did not move here. It is an
    invariant in `create_provisioned_user`, which is where it cannot be granted
    around.
    """
    require(db, current_user, "platform.manage_users")

    org_role = None
    discipline_ids: list[uuid.UUID] = []
    if user_data.org_role_id is not None:
        org_role = _requested_org_role(db, user_data.org_role_id)
        discipline_ids = _requested_disciplines(db, user_data.discipline_ids)

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
            org_role=org_role,
            discipline_ids=discipline_ids,
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
                 details={"role": user.role.value, "org_role": org_role.code if org_role else None,
                          "disciplines": [str(item) for item in discipline_ids],
                          "engineer_affiliation": user.engineer_affiliation, "direct_account": True})
    db.commit()
    return response


# `POST /users/engineers` and `POST /users/owners` stood here and are gone.
#
# Each hardcoded one legacy identity — `UserRole.ENGINEER`, `UserRole.OWNER` —
# as the whole of what an account could be, which is exactly the shape a
# configurable office cannot use: there is no endpoint to add for "Surveyor"
# or "BIM Engineer" without adding one per job title forever. `POST /users`
# takes `orgRoleId` and `disciplineIds` and covers all of them, including roles
# an office invents after this release.
#
# Removed rather than deprecated because nothing called them: neither the web
# client nor the Flutter app references either path, so there is no build in
# the field that breaks. A deprecated alias would have been compatibility for
# a caller that does not exist.


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

    # Knowing the current password proves the session is not merely open; a
    # code sent out-of-band proves the account's inbox is still controlled by
    # its owner. A stolen session satisfies the first and not the second.
    #
    # The forced first-login change is exempt: the user has not signed in
    # normally yet, may be acting on a temporary password from that same
    # inbox, and blocking them here would lock them out of the platform
    # entirely. `must_change_password` is already gated to this one endpoint
    # by `get_current_user`.
    # Captured before the flag is cleared below, so the audit records which
    # path actually ran rather than always reporting the post-change state.
    forced_first_change = current_user.must_change_password
    if not forced_first_change:
        require_step_up(db, current_user, "security.change_password")

    current_user.hashed_password = hash_password(data.new_password)
    current_user.must_change_password = False
    if not current_user.invitation_accepted:
        current_user.invitation_accepted = True
    if current_user.status == UserStatus.PENDING:
        current_user.status = UserStatus.ACTIVE
    # A password change had no audit record at all before this — one of the
    # gaps the security audit turned up.
    record_audit(db, actor_id=current_user.id, action="password_changed",
                 entity_type="user", entity_id=current_user.id,
                 details={"stepUp": not forced_first_change,
                          "forcedFirstChange": forced_first_change})
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
    # Was `can_manage_all_users(current_user.role)`. `platform.manage_users`
    # is the catalogue code for administering other people's accounts, and
    # resolves identically for every account in the database.
    if not has_permission(db, current_user, "platform.manage_users") and current_user.id != user_id:
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

        # --- the configurable model ----------------------------------------
        # Changing somebody's office role changes what they may do, so it is
        # the same class of act as changing the retired enum below and takes
        # the same step-up challenge. `assign_org_role` moves `is_internal`
        # with it, which is what keeps an account from being reclassified
        # internal/external by half.
        if update_data.org_role_id is not None and update_data.org_role_id != user.org_role_id:
            org_role = _requested_org_role(db, update_data.org_role_id)
            require_step_up(db, current_user, "admin.change_user_role")
            if user.id == current_user.id and not org_role.undeletable:
                raise HTTPException(
                    status_code=400,
                    detail="You cannot move yourself off the administrator role",
                )
            rbac.assign_org_role(
                db, user=user, role=org_role,
                organization_id=user.company_id or rbac.ensure_tenant_organization(db).id,
            )
        if update_data.discipline_ids is not None:
            # An empty list clears them; omitting the field leaves them alone.
            wanted = _requested_disciplines(db, update_data.discipline_ids)
            rbac.set_user_disciplines(
                db, user=user, discipline_ids=wanted,
                primary_id=wanted[0] if wanted else None,
            )

        if update_data.role is not None:
            if user.id == current_user.id and update_data.role != UserRole.ADMIN:
                raise HTTPException(status_code=400, detail="You cannot remove your own administrator role")
            # Only an actual change of role demands step-up: re-saving a
            # profile form that happens to echo the current role should not
            # pester the administrator for a code.
            resolved_role = UserRole.ENGINEER if update_data.role == UserRole.CONSULTANT else update_data.role
            if resolved_role != user.role:
                require_step_up(db, current_user, "admin.change_user_role")
            user.role = resolved_role

        # The retired columns, kept truthful without being asked for.
        #
        # What stood here validated `engineer_affiliation` against three magic
        # strings, demanded an organization for an "external consultant", and
        # required a single-valued `EngineerProfile.discipline`. All three are
        # the retired model: the office side is `is_internal` (moved by
        # `assign_org_role` above), and disciplines are many-to-many on
        # `user_disciplines`.
        #
        # `engineer_affiliation` is still written because `users.role` is still
        # NOT NULL and the pre-backfill bridges read it during the migration
        # window. It is derived from the role the account holds, never supplied.
        if user.org_role is not None:
            user.engineer_affiliation = user.org_role.legacy_affiliation or (
                "internal_engineer" if user.role == UserRole.ENGINEER else None
            )
        elif user.role != UserRole.ENGINEER:
            user.engineer_affiliation = None

        # `EngineerProfile` is likewise legacy. It is updated when a client
        # still sends one, and never demanded.
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
    # Locking someone out of the platform is high-impact and irreversible from
    # their side, so it needs proof the administrator's session is genuinely
    # theirs — not just that it is open.
    require_step_up(db, current_user, "admin.deactivate_user")
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
    # The most destructive operation the platform exposes, and unrecoverable.
    require_step_up(db, current_user, "admin.delete_user")

    detachable_links = {
        "ownedProjects": db.query(Project.id).filter(Project.owner_id == user.id).count(),
        "managedProjects": db.query(Project.id).filter(Project.project_manager_id == user.id).count(),
        "projectMemberships": db.query(ProjectMember.id).filter(ProjectMember.user_id == user.id).count(),
        "taskAssignments": db.query(task_assignees.c.task_id).filter(task_assignees.c.user_id == user.id).count(),
    }
    # Every one of these mirrors a real `ondelete="RESTRICT"` foreign key onto
    # `users.id` — i.e. a row the database itself will never let this DELETE
    # silently orphan or cascade away, because it is project history that has
    # to survive the person who made it. This dict must stay a complete
    # mirror of that set or `db.delete(user)` below throws a raw
    # `IntegrityError` (or, before this fix, an unrelated `AttributeError` —
    # `Message.receiver_id` doesn't exist on the current conversation-based
    # messaging schema; only `sender_id` does) instead of the clean 409 this
    # endpoint exists to give. `test_permanently_delete_user.py::
    # test_every_restrict_foreign_key_to_users_has_a_blocker_check` pins
    # completeness against the live schema so a new RESTRICT column added
    # later fails a test instead of a delete request.
    #
    # Deliberately NOT checked here (each is `ondelete="SET NULL"` or
    # `"CASCADE"` on `users.id`, so the database itself lets the delete
    # through and either preserves the row with the actor blanked — audit_logs
    # chief among them: the new "permanently_deleted" entry below is written
    # before the delete and is never itself deleted, only older rows that
    # named this user as actor lose that attribution — or removes a pure
    # membership/association row that carries no content of its own):
    # notifications, project_members, task_assignees, conversation_participants,
    # engineer_profiles, user_permission_overrides, audit_logs.actor_id,
    # projects.owner_id/project_manager_id, issues.assigned_to_id, and every
    # other reviewed_by/approved_by/assigned_by attribution column.
    blockers = {
        "created tasks": db.query(Task.id).filter(Task.created_by_id == user.id).first(),
        "task comments": db.query(TaskComment.id).filter(TaskComment.author_id == user.id).first(),
        "issues": db.query(Issue.id).filter(or_(Issue.raised_by_id == user.id, Issue.assigned_to_id == user.id)).first(),
        "documents or media": db.query(Document.id).filter(Document.uploaded_by_id == user.id).first()
            or db.query(MediaAsset.id).filter(MediaAsset.uploaded_by_id == user.id).first(),
        "site reports": db.query(SiteReport.id).filter(SiteReport.submitted_by_id == user.id).first(),
        "design changes": db.query(DesignChange.id).filter(DesignChange.proposed_by_id == user.id).first(),
        "messages": db.query(Message.id).filter(Message.sender_id == user.id).first(),
        "conversations created": db.query(Conversation.id).filter(Conversation.created_by_id == user.id).first(),
        "attachments": db.query(Attachment.id).filter(Attachment.uploaded_by_id == user.id).first(),
        "cost records": db.query(CostValidation.id).filter(CostValidation.requested_by_id == user.id).first(),
        "voice recordings": db.query(VoiceRecording.id).filter(VoiceRecording.recorded_by_id == user.id).first(),
        "field submissions": db.query(FieldSubmission.id).filter(FieldSubmission.submitted_by_id == user.id).first(),
        "IFC model groups": db.query(IFCModelGroup.id).filter(IFCModelGroup.created_by_id == user.id).first(),
        "IFC model versions": db.query(IFCModelVersion.id).filter(IFCModelVersion.uploaded_by_id == user.id).first(),
        "IFC comparisons": db.query(IFCComparison.id).filter(IFCComparison.created_by_id == user.id).first(),
        "client requests": db.query(OwnerRequest.id).filter(OwnerRequest.created_by_id == user.id).first(),
        "site visits": db.query(SiteVisit.id).filter(
            or_(SiteVisit.created_by_id == user.id, SiteVisit.engineer_id == user.id)
        ).first(),
        "voice analyses": db.query(VoiceAnalysis.id).filter(VoiceAnalysis.user_id == user.id).first(),
        "voice execution logs": db.query(VoiceExecutionLog.id).filter(VoiceExecutionLog.actor_user_id == user.id).first(),
        "AI action history": db.query(AIActionVersion.id).filter(AIActionVersion.actor_user_id == user.id).first(),
        # `ingested_files.uploaded_by_id` is RESTRICT for the same reason every
        # other uploader column is: a file with no author is evidence nobody
        # can account for. Note this covers package *members* too — they carry
        # the uploader of the package they came out of.
        "ingested files": db.query(IngestedFile.id).filter(IngestedFile.uploaded_by_id == user.id).first(),
        # `rag_index_jobs.requested_by_id` is RESTRICT for the same reason every
        # other actor column is: a re-index run with no requester is a record
        # nobody can account for.
        "RAG re-index runs": db.query(RagIndexJob.id).filter(RagIndexJob.requested_by_id == user.id).first(),
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
    # Resetting someone else's password hands over their account, so it is
    # gated on the administrator re-proving control of their own.
    require_step_up(db, current_user, "admin.reset_user_password")
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
