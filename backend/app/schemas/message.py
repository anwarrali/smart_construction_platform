from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field, model_validator

from app.models.enums import ConversationType
from app.schemas.user import CamelModel, UserOut


class ConversationCreate(CamelModel):
    project_id: UUID
    recipient_ids: list[UUID] = Field(default_factory=list, max_length=100)
    group_code: Optional[str] = Field(default=None, max_length=80)
    title: Optional[str] = Field(default=None, max_length=200)
    context_type: Optional[str] = Field(default=None, max_length=40)
    context_id: Optional[UUID] = None
    content: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_target(self):
        if bool(self.context_type) != bool(self.context_id):
            raise ValueError("contextType and contextId must be supplied together")
        if not self.recipient_ids and not self.group_code and not self.context_type:
            raise ValueError("Select recipients, a project group, or a context")
        return self


class DirectMessageCreate(CamelModel):
    project_id: UUID
    receiver_id: UUID
    content: str = Field(min_length=1, max_length=4000)


class ProjectAnnouncementCreate(CamelModel):
    project_id: UUID
    content: str = Field(min_length=1, max_length=4000)
    title: Optional[str] = Field(default=None, max_length=200)
    group_code: str = Field(default="ALL_PROJECT_MEMBERS", max_length=80)


class MessageSend(CamelModel):
    content: str = Field(min_length=1, max_length=4000)
    priority: str = Field(default="NORMAL", max_length=20)
    requires_acknowledgement: bool = False
    requires_response: bool = False
    response_due_at: Optional[datetime] = None
    responded_to_message_id: Optional[UUID] = None


class ForwardMessageCreate(CamelModel):
    """Forward an existing message into a (new or existing) conversation.

    Reuses the same recipient shapes `ConversationCreate` already supports —
    an explicit list, or a project group — so a forward is authorized through
    the exact same `can_message_user` / `resolve_group_recipient_ids` checks
    as composing a new conversation, not a parallel set of rules.
    """
    recipient_ids: list[UUID] = Field(default_factory=list, max_length=100)
    group_code: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = Field(default=None, max_length=4000)
    title: Optional[str] = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_target(self):
        if not self.recipient_ids and not self.group_code:
            raise ValueError("Select at least one recipient or a project group")
        return self


class ForwardOriginOut(CamelModel):
    """The original, non-forwarded message a forward ultimately traces back to."""
    message_id: UUID
    conversation_id: UUID
    sender: UserOut
    content: str
    created_at: datetime


class ShareEntityCreate(CamelModel):
    """Share a project entity (Issue, Task, Site Report, Design Change,
    Document, …) as a message — "Forward" or "Ask for Opinion" from that
    entity's own page, without leaving it.

    Recipient shapes match `ForwardMessageCreate` for the same reason: this
    goes through the exact same `_create_conversation` authorization, not a
    parallel set of rules.
    """
    entity_type: str = Field(max_length=40)
    entity_id: UUID
    recipient_ids: list[UUID] = Field(default_factory=list, max_length=100)
    group_code: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = Field(default=None, max_length=4000)
    title: Optional[str] = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_target(self):
        if not self.recipient_ids and not self.group_code:
            raise ValueError("Select at least one recipient or a project group")
        return self


class MessageOut(CamelModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    content: str
    priority: str = "NORMAL"
    requires_acknowledgement: bool = False
    requires_response: bool = False
    response_due_at: Optional[datetime] = None
    responded_to_message_id: Optional[UUID] = None
    sender: UserOut
    created_at: datetime
    updated_at: datetime
    edited_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    forwarded_from_message_id: Optional[UUID] = None
    forward_origin: Optional[ForwardOriginOut] = None
    shared_entity_type: Optional[str] = None
    shared_entity_id: Optional[UUID] = None


class ConversationParticipantOut(CamelModel):
    user_id: UUID
    user: UserOut
    joined_at: datetime
    last_read_at: Optional[datetime] = None


class ConversationOut(CamelModel):
    id: UUID
    project_id: UUID
    type: ConversationType
    title: Optional[str] = None
    created_by_id: UUID
    context_type: Optional[str] = None
    context_id: Optional[UUID] = None
    recipient_group: Optional[str] = None
    last_activity_at: datetime
    participants: list[ConversationParticipantOut]
    last_message: Optional[MessageOut] = None
    unread_count: int = 0
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationPage(CamelModel):
    items: list[ConversationOut]
    total: int
    page: int
    page_size: int


class RecipientGroupOut(CamelModel):
    code: str
    label: str
    recipient_count: int


class RecipientOptionsOut(CamelModel):
    users: list[UserOut]
    groups: list[RecipientGroupOut]
