"""Centralized project communication authorization and recipient resolution."""
from __future__ import annotations

import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import (
    is_consultant_engineer,
    is_main_contractor_engineer,
    is_worker,
    user_has_project_access,
)
from app.models.enums import ConversationType, UserRole, UserStatus
from app.models.issue import Issue
from app.models.message import Conversation, ConversationParticipant
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services.messaging_policy import (
    PROJECT_GROUPS,
    can_create_group,
    can_project_broadcast,
    worker_can_message,
)


def active_project_participant_ids(
    db: Session, project_id: uuid.UUID
) -> set[uuid.UUID]:
    project = db.get(Project, project_id)
    if not project:
        return set()
    ids = {value for value in (project.owner_id, project.project_manager_id) if value}
    ids.update(user_id for (user_id,) in db.query(ProjectMember.user_id).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.is_active == True,
    ).all())
    active_ids = {
        user_id for (user_id,) in db.query(User.id).filter(
            User.id.in_(ids), User.status == UserStatus.ACTIVE
        ).all()
    } if ids else set()
    return active_ids


def worker_recipient_ids(
    db: Session, worker: User, project_id: uuid.UUID
) -> set[uuid.UUID]:
    project = db.get(Project, project_id)
    result = {project.project_manager_id} if project and project.project_manager_id else set()
    tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.assignees.any(User.id == worker.id),
    ).all()
    for task in tasks:
        result.update(
            assignee.id for assignee in task.assignees
            if is_main_contractor_engineer(assignee)
        )
    return result


def can_message_user(
    db: Session, sender: User, project_id: uuid.UUID, recipient_id: uuid.UUID
) -> bool:
    if recipient_id == sender.id or not user_has_project_access(db, sender, project_id):
        return False
    if recipient_id not in active_project_participant_ids(db, project_id):
        return False
    if is_worker(sender):
        project = db.get(Project, project_id)
        return worker_can_message(
            target_is_project_manager=bool(project and project.project_manager_id == recipient_id),
            target_is_assigned_engineer=recipient_id in worker_recipient_ids(
                db, sender, project_id
            ),
        )
    return True


def can_create_project_group_conversation(user: User) -> bool:
    return can_create_group(user.role.value)


def can_send_project_announcement(user: User) -> bool:
    return can_project_broadcast(user.role.value)


def resolve_group_recipient_ids(
    db: Session, sender: User, project_id: uuid.UUID, group_code: str
) -> set[uuid.UUID]:
    code = group_code.strip().upper()
    if not can_create_project_group_conversation(sender):
        return set()
    project = db.get(Project, project_id)
    if not project or not user_has_project_access(db, sender, project_id):
        return set()
    active_ids = active_project_participant_ids(db, project_id)
    users = db.query(User).filter(User.id.in_(active_ids)).all() if active_ids else []
    memberships = {
        membership.user_id: membership
        for membership in db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.is_active == True,
        ).all()
    }
    if code == "ALL_PROJECT_MEMBERS":
        result = active_ids
    elif code == "ALL_ENGINEERS":
        result = {user.id for user in users if user.role == UserRole.ENGINEER}
    elif code == "WORKERS":
        result = {user.id for user in users if user.role == UserRole.WORKER}
    elif code == "PROJECT_MANAGERS":
        result = {
            user.id for user in users if user.role == UserRole.PROJECT_MANAGER
        }
        if project.project_manager_id:
            result.add(project.project_manager_id)
    elif code == "OWNERS":
        result = {project.owner_id} if project.owner_id in active_ids else set()
    elif code == "CONTRACTOR_TEAM":
        result = {
            user.id for user in users
            if user.role in {UserRole.PROJECT_MANAGER, UserRole.WORKER}
            or is_main_contractor_engineer(user)
        }
    elif code == "CONSULTANT_TEAM":
        result = {
            user.id for user in users
            if user.role == UserRole.CONSULTANT or is_consultant_engineer(user)
        }
    elif code.startswith("DISCIPLINE:"):
        discipline = code.split(":", 1)[1].strip().casefold()
        result = {
            user.id for user in users
            if (
                memberships.get(user.id)
                and (memberships[user.id].project_discipline or "").casefold() == discipline
            )
            or (
                user.engineer_profile
                and user.engineer_profile.discipline.value.casefold() == discipline
            )
        }
    else:
        result = set()
    result.discard(sender.id)
    return result


def can_access_context(
    db: Session, user: User, project_id: uuid.UUID,
    context_type: str, context_id: uuid.UUID,
) -> bool:
    if not user_has_project_access(db, user, project_id):
        return False
    normalized = context_type.upper()
    if normalized == "TASK":
        task = db.get(Task, context_id)
        if not task or task.project_id != project_id:
            return False
        if is_worker(user) or is_main_contractor_engineer(user):
            return any(assignee.id == user.id for assignee in task.assignees)
        return True
    if normalized == "ISSUE":
        issue = db.get(Issue, context_id)
        return bool(issue and issue.project_id == project_id and not is_worker(user))
    return False


def can_view_conversation(db: Session, user: User, conversation: Conversation) -> bool:
    if not user_has_project_access(db, user, conversation.project_id):
        return False
    is_participant = db.query(ConversationParticipant.id).filter(
        ConversationParticipant.conversation_id == conversation.id,
        ConversationParticipant.user_id == user.id,
    ).first() is not None
    if is_participant:
        return True
    return bool(
        conversation.type == ConversationType.CONTEXTUAL
        and conversation.context_type
        and conversation.context_id
        and can_access_context(
            db, user, conversation.project_id,
            conversation.context_type, conversation.context_id,
        )
    )


def can_send_to_conversation(db: Session, user: User, conversation: Conversation) -> bool:
    return can_view_conversation(db, user, conversation)


def available_group_codes(db: Session, user: User, project_id: uuid.UUID) -> list[str]:
    if not user_has_project_access(db, user, project_id):
        return []
    if can_create_project_group_conversation(user):
        disciplines = {
            value.casefold()
            for (value,) in db.query(ProjectMember.project_discipline).filter(
                ProjectMember.project_id == project_id,
                ProjectMember.is_active == True,
                ProjectMember.project_discipline.isnot(None),
            ).all()
            if value
        }
        return [*PROJECT_GROUPS, *(f"DISCIPLINE:{value.upper()}" for value in sorted(disciplines))]
    return []
