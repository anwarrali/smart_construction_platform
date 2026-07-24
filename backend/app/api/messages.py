from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user, is_worker, user_has_project_access
from app.db.database import get_db
from app.models.enums import ConversationType, NotificationType, UserStatus
from app.models.issue import Issue
from app.models.message import Conversation, ConversationParticipant, Message
from app.models.notification import Notification
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.message import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationPage,
    DirectMessageCreate,
    MessageOut,
    MessageSend,
    ProjectAnnouncementCreate,
    RecipientOptionsOut,
)
from app.schemas.user import UserOut
from app.services.audit_service import record_audit
from app.services.messaging_authorization import (
    active_project_participant_ids,
    available_group_codes,
    can_access_context,
    can_message_user,
    can_send_project_announcement,
    can_send_to_conversation,
    can_view_conversation,
    resolve_group_recipient_ids,
    worker_recipient_ids,
)


router = APIRouter(prefix="/messages", tags=["Project Communication"])


GROUP_LABELS = {
    "ALL_PROJECT_MEMBERS": "All Project Members",
    "ALL_ENGINEERS": "All Engineers",
    "CONTRACTOR_TEAM": "Contractor Team",
    "CONSULTANT_TEAM": "Consultant Team",
    "WORKERS": "Workers",
    "PROJECT_MANAGERS": "Project Managers",
    "OWNERS": "Owners",
}


def _conversation_or_404(db: Session, conversation_id: uuid.UUID) -> Conversation:
    value = db.get(Conversation, conversation_id)
    if not value:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return value


def _ensure_participant(
    db: Session, conversation: Conversation, user_id: uuid.UUID
) -> ConversationParticipant:
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation.id,
        ConversationParticipant.user_id == user_id,
    ).first()
    if not participant:
        participant = ConversationParticipant(
            conversation_id=conversation.id, user_id=user_id
        )
        db.add(participant)
        db.flush()
    return participant


def _message_payload(message: Message) -> dict:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "content": message.content,
        "sender": message.sender,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
        "edited_at": message.edited_at,
        "deleted_at": message.deleted_at,
    }


def _conversation_payload(
    db: Session, conversation: Conversation, current_user: User,
    *, include_messages: bool = False,
) -> dict:
    participants = db.query(ConversationParticipant).options(
        joinedload(ConversationParticipant.user)
    ).filter(
        ConversationParticipant.conversation_id == conversation.id
    ).order_by(ConversationParticipant.joined_at).all()
    current_participant = next(
        (item for item in participants if item.user_id == current_user.id), None
    )
    message_query = db.query(Message).options(joinedload(Message.sender)).filter(
        Message.conversation_id == conversation.id,
        Message.deleted_at.is_(None),
    )
    last_message = message_query.order_by(Message.created_at.desc()).first()
    unread_query = message_query.filter(Message.sender_id != current_user.id)
    if current_participant and current_participant.last_read_at:
        unread_query = unread_query.filter(
            Message.created_at > current_participant.last_read_at
        )
    unread = unread_query.count() if current_participant else 0
    payload = {
        "id": conversation.id,
        "project_id": conversation.project_id,
        "type": conversation.type,
        "title": conversation.title,
        "created_by_id": conversation.created_by_id,
        "context_type": conversation.context_type,
        "context_id": conversation.context_id,
        "recipient_group": conversation.recipient_group,
        "last_activity_at": conversation.last_activity_at,
        "participants": participants,
        "last_message": _message_payload(last_message) if last_message else None,
        "unread_count": unread,
        "created_at": conversation.created_at,
    }
    if include_messages:
        payload["messages"] = [
            _message_payload(message)
            for message in message_query.order_by(Message.created_at.asc()).limit(500).all()
        ]
    return payload


def _notify_message_recipients(
    db: Session, conversation: Conversation, message: Message, sender: User
) -> None:
    participant_ids = {
        user_id for (user_id,) in db.query(ConversationParticipant.user_id).filter(
            ConversationParticipant.conversation_id == conversation.id,
            ConversationParticipant.user_id != sender.id,
        ).all()
    }
    if conversation.type == ConversationType.PROJECT_CHANNEL:
        title = conversation.title or "New project announcement"
    elif conversation.type == ConversationType.CONTEXTUAL:
        title = f"New {conversation.context_type.lower()} discussion message"
    elif conversation.type == ConversationType.GROUP:
        title = conversation.title or "New group message"
    else:
        title = f"New message from {sender.full_name}"
    for user_id in participant_ids:
        db.add(Notification(
            user_id=user_id,
            project_id=conversation.project_id,
            task_id=conversation.context_id if conversation.context_type == "TASK" else None,
            title=title,
            message=message.content[:240],
            type=NotificationType.MESSAGE,
            related_entity_type="CONVERSATION",
            related_entity_id=conversation.id,
        ))


def _send_message(
    db: Session, conversation: Conversation, sender: User, content: str
) -> Message:
    if not can_send_to_conversation(db, sender, conversation):
        raise HTTPException(status_code=403, detail="You cannot send to this conversation")
    _ensure_participant(db, conversation, sender.id)
    message = Message(
        conversation_id=conversation.id,
        sender_id=sender.id,
        content=content.strip(),
    )
    db.add(message)
    db.flush()
    conversation.last_activity_at = message.created_at or datetime.now(timezone.utc)
    _notify_message_recipients(db, conversation, message, sender)
    return message


def _direct_conversation(
    db: Session, project_id: uuid.UUID, first_id: uuid.UUID, second_id: uuid.UUID
) -> Conversation | None:
    candidates = db.query(Conversation).filter(
        Conversation.project_id == project_id,
        Conversation.type == ConversationType.DIRECT,
        Conversation.participants.any(
            ConversationParticipant.user_id == first_id
        ),
    ).all()
    target = {first_id, second_id}
    for conversation in candidates:
        ids = {
            user_id for (user_id,) in db.query(ConversationParticipant.user_id).filter(
                ConversationParticipant.conversation_id == conversation.id
            ).all()
        }
        if ids == target:
            return conversation
    return None


def _context_default_recipients(
    db: Session, project: Project, context_type: str, context_id: uuid.UUID
) -> set[uuid.UUID]:
    if context_type == "TASK":
        task = db.get(Task, context_id)
        result = {assignee.id for assignee in task.assignees} if task else set()
    else:
        issue = db.get(Issue, context_id)
        result = {issue.raised_by_id} if issue else set()
        if issue and issue.assigned_to_id:
            result.add(issue.assigned_to_id)
    if project.project_manager_id:
        result.add(project.project_manager_id)
    return {value for value in result if value}


def _create_conversation(
    db: Session, data: ConversationCreate, current_user: User,
    *, force_announcement: bool = False,
) -> Conversation:
    project = db.get(Project, data.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not user_has_project_access(db, current_user, project.id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    context_type = data.context_type.upper() if data.context_type else None
    if context_type and (
        not data.context_id
        or not can_access_context(db, current_user, project.id, context_type, data.context_id)
    ):
        raise HTTPException(status_code=403, detail="You cannot access this message context")
    recipient_ids = set(data.recipient_ids)
    if data.group_code:
        resolved = resolve_group_recipient_ids(
            db, current_user, project.id, data.group_code
        )
        if not resolved:
            raise HTTPException(status_code=403, detail="This recipient group is unavailable or empty")
        recipient_ids.update(resolved)
    if context_type and not recipient_ids:
        recipient_ids.update(
            _context_default_recipients(db, project, context_type, data.context_id)
        )
        if is_worker(current_user):
            recipient_ids.intersection_update(
                worker_recipient_ids(db, current_user, project.id)
            )
    recipient_ids.discard(current_user.id)
    if not recipient_ids:
        raise HTTPException(status_code=422, detail="At least one authorized recipient is required")
    invalid = [
        recipient_id for recipient_id in recipient_ids
        if not can_message_user(db, current_user, project.id, recipient_id)
    ]
    if invalid:
        raise HTTPException(status_code=403, detail="One or more recipients are outside your authorized project contacts")

    if force_announcement:
        conversation_type = ConversationType.PROJECT_CHANNEL
    elif context_type:
        conversation_type = ConversationType.CONTEXTUAL
    elif len(recipient_ids) == 1:
        conversation_type = ConversationType.DIRECT
    else:
        conversation_type = ConversationType.GROUP

    if conversation_type == ConversationType.DIRECT:
        existing = _direct_conversation(
            db, project.id, current_user.id, next(iter(recipient_ids))
        )
        if existing:
            if data.content:
                _send_message(db, existing, current_user, data.content)
            return existing
    if conversation_type == ConversationType.CONTEXTUAL:
        existing = db.query(Conversation).filter(
            Conversation.project_id == project.id,
            Conversation.type == ConversationType.CONTEXTUAL,
            Conversation.context_type == context_type,
            Conversation.context_id == data.context_id,
        ).first()
        if existing:
            for recipient_id in recipient_ids:
                _ensure_participant(db, existing, recipient_id)
            _ensure_participant(db, existing, current_user.id)
            if data.content:
                _send_message(db, existing, current_user, data.content)
            return existing

    conversation = Conversation(
        project_id=project.id,
        type=conversation_type,
        title=(data.title or "").strip() or None,
        created_by_id=current_user.id,
        context_type=context_type,
        context_id=data.context_id,
        recipient_group=data.group_code.upper() if data.group_code else None,
    )
    db.add(conversation)
    db.flush()
    for user_id in {current_user.id, *recipient_ids}:
        _ensure_participant(db, conversation, user_id)
    if data.content:
        _send_message(db, conversation, current_user, data.content)
    record_audit(
        db, actor_id=current_user.id,
        action="project_announcement_created" if force_announcement else "conversation_created",
        entity_type="conversation", entity_id=conversation.id,
        project_id=project.id,
        details={
            "type": conversation.type.value,
            "recipient_count": len(recipient_ids),
            "context_type": context_type,
            "context_id": data.context_id,
        },
    )
    return conversation


@router.get("/recipient-options", response_model=RecipientOptionsOut)
def recipient_options(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    ids = (
        worker_recipient_ids(db, current_user, project_id)
        if is_worker(current_user)
        else active_project_participant_ids(db, project_id) - {current_user.id}
    )
    users = db.query(User).filter(
        User.id.in_(ids), User.status == UserStatus.ACTIVE
    ).order_by(User.full_name).all() if ids else []
    groups = []
    for code in available_group_codes(db, current_user, project_id):
        count = len(resolve_group_recipient_ids(db, current_user, project_id, code))
        if count:
            groups.append({
                "code": code,
                "label": (
                    f"{code.split(':', 1)[1].title()} Team"
                    if code.startswith("DISCIPLINE:")
                    else GROUP_LABELS.get(code, code.replace("_", " ").title())
                ),
                "recipient_count": count,
            })
    return {"users": users, "groups": groups}


@router.get("/participants", response_model=list[UserOut])
def legacy_participants(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return recipient_options(project_id, db, current_user)["users"]


@router.get("/conversations", response_model=ConversationPage)
def list_conversations(
    project_id: uuid.UUID,
    conversation_type: ConversationType | None = None,
    unread_only: bool = False,
    participant_id: uuid.UUID | None = None,
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = db.query(Conversation).join(ConversationParticipant).filter(
        Conversation.project_id == project_id,
        ConversationParticipant.user_id == current_user.id,
    )
    if conversation_type:
        query = query.filter(Conversation.type == conversation_type)
    if participant_id:
        query = query.filter(Conversation.participants.any(
            ConversationParticipant.user_id == participant_id
        ))
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            Conversation.title.ilike(term),
            Conversation.messages.any(Message.content.ilike(term)),
            Conversation.participants.any(
                ConversationParticipant.user.has(User.full_name.ilike(term))
            ),
        ))
    total = query.count()
    conversations = query.order_by(
        Conversation.last_activity_at.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    items = [
        _conversation_payload(db, conversation, current_user)
        for conversation in conversations
    ]
    if unread_only:
        items = [item for item in items if item["unread_count"] > 0]
        total = len(items)
    return {
        "items": items, "total": total, "page": page, "page_size": page_size
    }


@router.get("/search", response_model=ConversationPage)
def search_messages(
    project_id: uuid.UUID,
    query: str = Query(min_length=1, max_length=120),
    participant_id: uuid.UUID | None = None,
    context_type: str | None = None,
    context_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = list_conversations(
        project_id, None, False, participant_id, query,
        page, page_size, db, current_user,
    )
    if context_type:
        result["items"] = [
            item for item in result["items"]
            if item["context_type"] == context_type.upper()
            and (context_id is None or item["context_id"] == context_id)
        ]
        result["total"] = len(result["items"])
    return result


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = _create_conversation(db, data, current_user)
    db.commit()
    db.refresh(conversation)
    return _conversation_payload(db, conversation, current_user)


@router.post("/announcements", response_model=ConversationOut, status_code=201)
def create_project_announcement(
    data: ProjectAnnouncementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_send_project_announcement(current_user):
        raise HTTPException(status_code=403, detail="Only Project Managers or Admins can announce")
    conversation = _create_conversation(
        db,
        ConversationCreate(
            project_id=data.project_id,
            group_code=data.group_code,
            title=data.title or "Project Announcement",
            content=data.content,
        ),
        current_user,
        force_announcement=True,
    )
    db.commit()
    db.refresh(conversation)
    return _conversation_payload(db, conversation, current_user)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = _conversation_or_404(db, conversation_id)
    if not can_view_conversation(db, current_user, conversation):
        raise HTTPException(status_code=403, detail="You cannot view this conversation")
    _ensure_participant(db, conversation, current_user.id)
    db.commit()
    return _conversation_payload(db, conversation, current_user, include_messages=True)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=201,
)
def send_conversation_message(
    conversation_id: uuid.UUID,
    data: MessageSend,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = _conversation_or_404(db, conversation_id)
    message = _send_message(db, conversation, current_user, data.content)
    db.commit()
    return db.query(Message).options(joinedload(Message.sender)).filter(
        Message.id == message.id
    ).first()


@router.put("/conversations/{conversation_id}/read", response_model=ConversationOut)
def mark_conversation_read(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = _conversation_or_404(db, conversation_id)
    if not can_view_conversation(db, current_user, conversation):
        raise HTTPException(status_code=403, detail="You cannot view this conversation")
    participant = _ensure_participant(db, conversation, current_user.id)
    last_message = db.query(Message).filter(
        Message.conversation_id == conversation.id,
        Message.deleted_at.is_(None),
    ).order_by(Message.created_at.desc()).first()
    participant.last_read_message_id = last_message.id if last_message else None
    participant.last_read_at = datetime.now(timezone.utc)
    db.commit()
    return _conversation_payload(db, conversation, current_user)


@router.get("/unread-count")
def unread_message_count(
    project_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(ConversationParticipant).join(Conversation).filter(
        ConversationParticipant.user_id == current_user.id
    )
    if project_id:
        if not user_has_project_access(db, current_user, project_id):
            raise HTTPException(status_code=403, detail="You do not have access to this project")
        query = query.filter(Conversation.project_id == project_id)
    count = 0
    for participant in query.all():
        messages = db.query(Message).filter(
            Message.conversation_id == participant.conversation_id,
            Message.sender_id != current_user.id,
            Message.deleted_at.is_(None),
        )
        if participant.last_read_at:
            messages = messages.filter(Message.created_at > participant.last_read_at)
        count += messages.count()
    return {"count": count}


@router.get(
    "/context/{context_type}/{context_id}",
    response_model=ConversationDetail | None,
)
def get_context_conversation(
    context_type: str,
    context_id: uuid.UUID,
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    normalized = context_type.upper()
    if not can_access_context(db, current_user, project_id, normalized, context_id):
        raise HTTPException(status_code=403, detail="You cannot access this message context")
    conversation = db.query(Conversation).filter(
        Conversation.project_id == project_id,
        Conversation.type == ConversationType.CONTEXTUAL,
        Conversation.context_type == normalized,
        Conversation.context_id == context_id,
    ).first()
    if not conversation:
        return None
    _ensure_participant(db, conversation, current_user.id)
    db.commit()
    return _conversation_payload(db, conversation, current_user, include_messages=True)


@router.post(
    "/context/{context_type}/{context_id}",
    response_model=ConversationOut,
    status_code=201,
)
def create_context_conversation(
    context_type: str,
    context_id: uuid.UUID,
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data.context_type = context_type.upper()
    data.context_id = context_id
    conversation = _create_conversation(db, data, current_user)
    db.commit()
    db.refresh(conversation)
    return _conversation_payload(db, conversation, current_user)


@router.post("", response_model=MessageOut)
def legacy_send_direct_message(
    data: DirectMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = _create_conversation(
        db,
        ConversationCreate(
            project_id=data.project_id,
            recipient_ids=[data.receiver_id],
            content=data.content,
        ),
        current_user,
    )
    db.commit()
    return db.query(Message).options(joinedload(Message.sender)).filter(
        Message.conversation_id == conversation.id,
        Message.sender_id == current_user.id,
    ).order_by(Message.created_at.desc()).first()


@router.put("/{message_id}/read", response_model=ConversationOut)
def legacy_mark_message_read(
    message_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return mark_conversation_read(message.conversation_id, db, current_user)
