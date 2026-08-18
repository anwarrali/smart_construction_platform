from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user, is_worker, user_has_project_access
from app.db.database import get_db
from app.models.design_change import DesignChange
from app.models.document import Document
from app.models.enums import ConversationType, NotificationType, UserStatus
from app.models.issue import Issue
from app.models.message import Conversation, ConversationParticipant, Message
from app.models.collaboration import MessageRecipientState
from app.models.notification import Notification
from app.models.project import Project
from app.models.site_report import SiteReport
from app.models.task import Task
from app.models.user import User
from app.schemas.message import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationPage,
    DirectMessageCreate,
    ForwardMessageCreate,
    MessageOut,
    MessageSend,
    ProjectAnnouncementCreate,
    RecipientOptionsOut,
    ShareEntityCreate,
)
from app.schemas.user import UserOut
from app.services.audit_service import record_audit
from app.services.notification_service import (
    CATEGORY_DIRECT, CATEGORY_WORKFLOW, PRIORITY_NORMAL, notify,
)
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
    origin = message.forward_origin
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "content": message.content,
        "priority": message.priority,
        "requires_acknowledgement": message.requires_acknowledgement,
        "requires_response": message.requires_response,
        "response_due_at": message.response_due_at,
        "responded_to_message_id": message.responded_to_message_id,
        "sender": message.sender,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
        "edited_at": message.edited_at,
        "deleted_at": message.deleted_at,
        "forwarded_from_message_id": message.forwarded_from_message_id,
        # Never the immediate forwarded-from message — always the first,
        # non-forwarded message in the chain, so the recipient sees who
        # actually wrote it even after several hops (2.3 / 2.9 "multiple
        # forwarding" — the chain must resolve to the true original sender).
        "forward_origin": {
            "message_id": origin.id,
            "conversation_id": origin.conversation_id,
            "sender": origin.sender,
            "content": origin.content,
            "created_at": origin.created_at,
        } if origin else None,
        "shared_entity_type": message.shared_entity_type,
        "shared_entity_id": message.shared_entity_id,
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
    if message.forwarded_from_message_id:
        # 2.6: a forwarded message must not read like an ordinary new message —
        # the notification says up front that this is forwarded content, and
        # names who it originally came from when that is still known. The
        # forwarder's own note (`message.content`) and the original content
        # (`origin.content`) are different pieces of information — quoting
        # the note back as if it were "originally from" the other person
        # would misattribute it, so both are shown, each labelled.
        origin = message.forward_origin
        title = f"{sender.full_name} forwarded you a message"
        if origin and origin.sender:
            notify_body = (
                f"{message.content[:150]} "
                f"(forwarded from {origin.sender.full_name}: {origin.content[:150]})"
            )
        else:
            notify_body = message.content[:240]
    elif message.shared_entity_type:
        # A shared entity gets its own wording so the recipient can tell, from
        # the notification alone, that someone sent them an Issue/Task/etc.
        # rather than an ordinary message.
        label = SHARED_ENTITY_LABELS.get(
            message.shared_entity_type,
            message.shared_entity_type.replace("_", " ").lower(),
        ).lower()
        article = "an" if label[:1] in "aeiou" else "a"
        title = f"{sender.full_name} shared {article} {label} with you"
        notify_body = message.content[:240]
    elif conversation.type == ConversationType.PROJECT_CHANNEL:
        title = conversation.title or "New project announcement"
        notify_body = message.content[:240]
    elif conversation.type == ConversationType.CONTEXTUAL:
        title = f"New {conversation.context_type.lower()} discussion message"
        notify_body = message.content[:240]
    elif conversation.type == ConversationType.GROUP:
        title = conversation.title or "New group message"
        notify_body = message.content[:240]
    else:
        title = f"New message from {sender.full_name}"
        notify_body = message.content[:240]
    # A share explicitly asks the recipient to look at something, so it is
    # workflow rather than a passing message; everything else here happened
    # directly to the user.
    is_share = bool(message.shared_entity_type)
    for user_id in participant_ids:
        notify(
            db,
            user_id=user_id,
            project_id=conversation.project_id,
            task_id=conversation.context_id if conversation.context_type == "TASK" else None,
            title=title,
            message=notify_body,
            notification_type=NotificationType.MESSAGE,
            category=CATEGORY_WORKFLOW if is_share else CATEGORY_DIRECT,
            priority=PRIORITY_NORMAL,
            requires_action=is_share or message.requires_response,
            entity_type="CONVERSATION",
            entity_id=conversation.id,
        )


def _send_message(
    db: Session, conversation: Conversation, sender: User, content: str,
    *, priority: str = "NORMAL", requires_acknowledgement: bool = False,
    requires_response: bool = False, response_due_at=None,
    responded_to_message_id=None, forward_source: Message | None = None,
    entity_share: tuple[str, uuid.UUID] | None = None,
) -> Message:
    if not can_send_to_conversation(db, sender, conversation):
        raise HTTPException(status_code=403, detail="You cannot send to this conversation")
    _ensure_participant(db, conversation, sender.id)
    message = Message(
        conversation_id=conversation.id,
        sender_id=sender.id,
        content=content.strip(),
        priority=priority.upper(),
        requires_acknowledgement=requires_acknowledgement,
        requires_response=requires_response,
        response_due_at=response_due_at,
        responded_to_message_id=responded_to_message_id,
        forwarded_from_message_id=forward_source.id if forward_source else None,
        # Inherit the root of the chain when the source was itself already a
        # forward, rather than pointing at it again — see the module-level
        # note on `Message.forward_origin_message_id`.
        forward_origin_message_id=(
            (forward_source.forward_origin_message_id or forward_source.id)
            if forward_source else None
        ),
        shared_entity_type=entity_share[0] if entity_share else None,
        shared_entity_id=entity_share[1] if entity_share else None,
    )
    db.add(message)
    db.flush()
    now = datetime.now(timezone.utc)
    recipient_ids = db.query(ConversationParticipant.user_id).filter(
        ConversationParticipant.conversation_id == conversation.id,
        ConversationParticipant.user_id != sender.id,
    ).all()
    for (recipient_id,) in recipient_ids:
        db.add(MessageRecipientState(
            message_id=message.id, user_id=recipient_id, delivered_at=now,
            response_status="NEEDS_RESPONSE" if requires_response else "UNREAD",
        ))
    if responded_to_message_id:
        receipt = db.query(MessageRecipientState).filter(
            MessageRecipientState.message_id == responded_to_message_id,
            MessageRecipientState.user_id == sender.id,
        ).first()
        if receipt:
            receipt.responded_at = now
            receipt.response_status = "RESPONDED"
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


# --- Entity sharing (Forward / Ask for Opinion from an entity's own page) --
#
# One generic pipeline for every supported entity, rather than a bespoke
# forward endpoint per entity: resolve the entity and its project, format a
# plain-text summary (matching what the recipient would see if they opened
# the entity themselves), and hand off to the exact same `_create_conversation`
# / `_send_message` machinery a plain compose or a message-forward already
# uses. Sharing never writes to the entity's own row — it only ever creates a
# Message — so ownership, status and approval state are structurally
# untouched, not just "not touched by convention".

SHARED_ENTITY_LABELS = {
    "ISSUE": "Issue",
    "TASK": "Task",
    "SITE_REPORT": "Site Report",
    "DESIGN_CHANGE": "Design Change",
    "DOCUMENT": "Document",
}


def _resolve_shared_entity(db: Session, entity_type: str, entity_id: uuid.UUID):
    """The entity and the project it belongs to, or (None, None) if unknown."""
    model = {
        "ISSUE": Issue, "TASK": Task, "SITE_REPORT": SiteReport,
        "DESIGN_CHANGE": DesignChange, "DOCUMENT": Document,
    }.get(entity_type)
    if not model:
        return None, None
    entity = db.get(model, entity_id)
    return (entity, entity.project_id) if entity else (None, None)


def _format_shared_entity(
    entity_type: str, entity, project: Project, sender: User, note: str | None,
) -> str:
    """A plain-text summary block, matching what the recipient would see on
    the entity's own page — not just a bare link, so the message is useful
    even before they click through."""
    label = SHARED_ENTITY_LABELS.get(entity_type, entity_type.replace("_", " ").title())
    fields: list[tuple[str, str]] = [("Project", project.name)]
    body: str | None = None

    if entity_type == "ISSUE":
        fields += [
            ("Issue", entity.title),
            ("Status", entity.status.value.replace("_", " ").title()),
            ("Severity", entity.severity.value.title()),
            ("Original owner", entity.raised_by.full_name if entity.raised_by else "—"),
        ]
        body = entity.description
    elif entity_type == "TASK":
        assignees = ", ".join(person.full_name for person in entity.assignees) or "Unassigned"
        fields += [
            ("Task", f"{entity.task_code} — {entity.name}"),
            ("Status", entity.status.value.replace("_", " ").title()),
            ("Assigned to", assignees),
        ]
        body = entity.description
    elif entity_type == "SITE_REPORT":
        fields += [
            ("Report date", str(entity.report_date)),
            ("Submitted by", entity.submitted_by.full_name if entity.submitted_by else "—"),
            ("Status", entity.review_status.replace("_", " ").title()),
        ]
        body = entity.summary_text
    elif entity_type == "DESIGN_CHANGE":
        fields += [
            ("Design Change", entity.title),
            ("Discipline", entity.source_discipline.title()),
            ("Status", entity.status.value.replace("_", " ").title()),
            ("Proposed by", entity.proposed_by.full_name if entity.proposed_by else "—"),
        ]
        body = entity.description
    elif entity_type == "DOCUMENT":
        fields += [
            ("Document", entity.title),
            ("Type", entity.document_type.value.title()),
            ("Uploaded by", entity.uploaded_by.full_name if entity.uploaded_by else "—"),
        ]

    lines = [f"Shared {label}", ""]
    lines += [f"{key}: {value}" for key, value in fields]
    if body and body.strip():
        lines += ["", "Description:", body.strip()]
    lines += ["", f"Shared by: {sender.full_name}"]
    if note and note.strip():
        lines += ["", "Note:", f'"{note.strip()}"']
    return "\n".join(lines)


def _create_conversation(
    db: Session, data: ConversationCreate, current_user: User,
    *, force_announcement: bool = False, forward_source: Message | None = None,
    entity_share: tuple[str, uuid.UUID] | None = None,
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
                _send_message(db, existing, current_user, data.content,
                              forward_source=forward_source, entity_share=entity_share)
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
                _send_message(db, existing, current_user, data.content,
                              forward_source=forward_source, entity_share=entity_share)
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
        _send_message(db, conversation, current_user, data.content,
                      forward_source=forward_source, entity_share=entity_share)
    record_audit(
        db, actor_id=current_user.id,
        action="project_announcement_created" if force_announcement else (
            "message_forwarded" if forward_source else
            "entity_shared" if entity_share else "conversation_created"
        ),
        entity_type="conversation", entity_id=conversation.id,
        project_id=project.id,
        details={
            "type": conversation.type.value,
            "recipient_count": len(recipient_ids),
            "context_type": context_type,
            "context_id": data.context_id,
            **({"forwarded_message_id": str(forward_source.id)} if forward_source else {}),
            **({"shared_entity_type": entity_share[0], "shared_entity_id": str(entity_share[1])} if entity_share else {}),
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


@router.post("/{message_id}/forward", response_model=ConversationDetail, status_code=201)
def forward_message(
    message_id: uuid.UUID,
    data: ForwardMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forward a message as its own new message, into a (new or existing)
    conversation with the chosen recipients.

    This is communication, not a task/issue/report handoff: it creates a
    Message, nothing else. The original message is untouched, its
    conversation is untouched, and nothing about who owns or is responsible
    for any entity the message happened to reference ever changes here — see
    the module docstring on `Message.forward_origin_message_id` for how the
    chain itself is tracked.
    """
    source = db.query(Message).filter(Message.id == message_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Message not found")
    if source.deleted_at:
        raise HTTPException(status_code=409, detail="A deleted message cannot be forwarded")
    source_conversation = _conversation_or_404(db, source.conversation_id)
    # Reading the source is its own check, independent of who the forward is
    # going to: `_create_conversation` below authorizes each recipient, but
    # nothing else re-confirms the forwarder was ever allowed to see this
    # message in the first place.
    if not can_view_conversation(db, current_user, source_conversation):
        raise HTTPException(status_code=403, detail="You cannot forward a message you do not have access to")

    note = (data.note or "").strip() or f"{current_user.full_name} forwarded a message."
    # `_create_conversation` performs every recipient/group authorization
    # check a normal compose does (`can_message_user`, `resolve_group_recipient_ids`),
    # scoped to the source message's own project — so a forward can never
    # reach a recipient outside that project, and never a recipient the
    # forwarder could not otherwise message on it (2.7 / project isolation).
    target = _create_conversation(
        db,
        ConversationCreate(
            project_id=source_conversation.project_id,
            recipient_ids=data.recipient_ids,
            group_code=data.group_code,
            title=data.title,
            content=note,
        ),
        current_user,
        forward_source=source,
    )
    db.commit()
    db.refresh(target)
    return _conversation_payload(db, target, current_user, include_messages=True)


@router.post("/share", response_model=ConversationDetail, status_code=201)
def share_entity(
    data: ShareEntityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Share a project entity as a message — the "Forward" / "Ask for Opinion"
    action offered from an Issue, Task, Site Report, Design Change or Document.

    Consultation, not handoff: this only ever creates a Message. It does not
    write to the shared entity, so ownership, assignee, status, verification
    and approval state are all untouched by construction, and no duplicate
    entity is ever created.
    """
    entity_type = data.entity_type.upper()
    if entity_type not in SHARED_ENTITY_LABELS:
        raise HTTPException(status_code=422, detail="This entity type cannot be shared")
    entity, project_id = _resolve_shared_entity(db, entity_type, data.entity_id)
    if not entity or not project_id:
        raise HTTPException(status_code=404, detail="The item you are sharing was not found")

    # Three independent checks, none of which the others imply:
    #   1. the sender may see this project at all;
    #   2. the sender may see *this specific entity* — `can_access_context`
    #      applies the same per-entity rules the entity's own discussion uses
    #      (e.g. Workers are excluded from Issues, Engineers only reach tasks
    #      assigned to them), so sharing cannot become a way to read out an
    #      entity you could not otherwise open;
    #   3. every recipient is authorized — enforced inside `_create_conversation`.
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    if not can_access_context(db, current_user, project_id, entity_type, data.entity_id):
        raise HTTPException(status_code=403, detail="You cannot share an item you do not have access to")

    # Resolve any group code here rather than leaving it to
    # `_create_conversation`, so every eventual recipient can be checked for
    # entity access *before* the content is written into a message. Sharing
    # sends a summary of the entity, so a recipient who could not open the
    # entity themselves must not receive it — this is what stops sharing from
    # becoming a way to leak a restricted Document (or Issue) to someone the
    # entity's own permissions exclude. `_create_conversation` still re-checks
    # project-level messaging permission for each id it is handed.
    recipient_ids = set(data.recipient_ids)
    if data.group_code:
        resolved = resolve_group_recipient_ids(db, current_user, project_id, data.group_code)
        if not resolved:
            raise HTTPException(status_code=403, detail="This recipient group is unavailable or empty")
        recipient_ids.update(resolved)
    recipient_ids.discard(current_user.id)
    if not recipient_ids:
        raise HTTPException(status_code=422, detail="At least one authorized recipient is required")
    recipients = db.query(User).filter(User.id.in_(recipient_ids)).all()
    if len(recipients) != len(recipient_ids):
        raise HTTPException(status_code=404, detail="One or more recipients were not found")
    blocked = [
        person.full_name for person in recipients
        if not can_access_context(db, person, project_id, entity_type, data.entity_id)
    ]
    if blocked:
        raise HTTPException(
            status_code=403,
            detail=f"These recipients cannot access this item: {', '.join(sorted(blocked))}",
        )

    project = db.get(Project, project_id)
    content = _format_shared_entity(entity_type, entity, project, current_user, data.note)
    target = _create_conversation(
        db,
        ConversationCreate(
            project_id=project_id,
            recipient_ids=sorted(recipient_ids),
            title=data.title,
            content=content,
        ),
        current_user,
        entity_share=(entity_type, data.entity_id),
    )
    db.commit()
    db.refresh(target)
    return _conversation_payload(db, target, current_user, include_messages=True)


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
    message = _send_message(
        db, conversation, current_user, data.content,
        priority=data.priority, requires_acknowledgement=data.requires_acknowledgement,
        requires_response=data.requires_response, response_due_at=data.response_due_at,
        responded_to_message_id=data.responded_to_message_id,
    )
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
    unread_receipts = db.query(MessageRecipientState).join(
        Message, Message.id == MessageRecipientState.message_id
    ).filter(
        MessageRecipientState.user_id == current_user.id,
        Message.conversation_id == conversation.id,
        MessageRecipientState.read_at.is_(None),
    ).all()
    for receipt in unread_receipts:
        receipt.read_at = participant.last_read_at
        # Opening a message is not the same as handling it. Preserve the
        # actionable state until an explicit acknowledgement or response.
        if receipt.message.requires_response:
            receipt.response_status = "NEEDS_RESPONSE"
        else:
            receipt.response_status = "READ"
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
