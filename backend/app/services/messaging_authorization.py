"""Centralized project communication authorization and recipient resolution."""
from __future__ import annotations

import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import user_has_project_access
from app.services.authorization import has_permission
from app.models.enums import ConversationType, UserRole, UserStatus
from app.models.issue import Issue
from app.models.design_change import DesignChange
from app.models.document import Document
from app.models.site_report import SiteReport
from app.models.field_submission import FieldSubmission
from app.models.ifc import IFCElement, IFCSpatialNode
from app.models.collaboration import OwnerRequest, SiteVisit
from app.models.message import Conversation, ConversationParticipant
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services.messaging_policy import (
    PROJECT_GROUPS,
    can_create_group,
    can_project_broadcast,
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


def can_message_user(
    db: Session, sender: User, project_id: uuid.UUID, recipient_id: uuid.UUID
) -> bool:
    if recipient_id == sender.id or not user_has_project_access(db, sender, project_id):
        return False
    if recipient_id not in active_project_participant_ids(db, project_id):
        return False
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
        # Everybody doing technical work on the project: the office's own
        # people, minus the ones who are only here to read. Was
        # `role == ENGINEER`, which missed every role an office created.
        result = {
            user.id for user in users
            if user.is_internal and has_permission(db, user, "task.update_progress", project_id)
        }
    elif code == "PROJECT_MANAGERS":
        # Whoever runs this project — the assigned manager, and anybody the
        # office gave team authority to.
        result = {
            user.id for user in users
            if has_permission(db, user, "project.manage_members", project_id)
        }
        if project.project_manager_id:
            result.add(project.project_manager_id)
    elif code == "OWNERS":
        result = {project.owner_id} if project.owner_id in active_ids else set()
    elif code == "CONTRACTOR_TEAM":
        # Everybody on the project for an outside contractor. Was "project
        # managers, workers and main-contractor engineers" — three role names
        # for one idea, and the idea is now recorded on the membership.
        result = {
            member.user_id for member in memberships.values()
            if member.party_id is not None and member.user_id in active_ids
        }
    elif code == "CONSULTANT_TEAM":
        # The office's own reviewers on this project.
        result = {
            user.id for user in users
            if has_permission(db, user, "task.review", project_id) and user.is_internal
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
        from app.services import work_scope

        return work_scope.can_see_task(db, user, task)
    if normalized == "ISSUE":
        issue = db.get(Issue, context_id)
        return bool(issue and issue.project_id == project_id)
    model_map = {
        "DESIGN_CHANGE": DesignChange, "DOCUMENT": Document, "SITE_REPORT": SiteReport,
        "FIELD_SUBMISSION": FieldSubmission, "OWNER_REQUEST": OwnerRequest, "SITE_VISIT": SiteVisit,
        "IFC_ELEMENT": IFCElement, "ROOM": IFCSpatialNode, "FLOOR": IFCSpatialNode,
    }
    if normalized == "PROJECT":
        return context_id == project_id
    model = model_map.get(normalized)
    if model:
        entity = db.get(model, context_id)
        entity_project_id = getattr(entity, "project_id", None) if entity else None
        if entity and normalized in {"IFC_ELEMENT", "ROOM", "FLOOR"}:
            entity_project_id = entity.version.project_id
        if not entity or entity_project_id != project_id:
            return False
        if normalized == "DOCUMENT":
            # Documents have per-document access, so "is on the project" is not
            # enough here. Before the redesign the only thing standing between a
            # Worker and a project document in this branch was a role check;
            # with external participants on projects that would have become a
            # way to forward a drawing nobody had shared. Ask the one helper
            # that decides document access instead.
            from app.services.document_access import readable_documents_query
            from app.models.document import Document as DocumentModel

            return readable_documents_query(db, user, project_id).filter(
                DocumentModel.id == context_id
            ).first() is not None
        return True
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
