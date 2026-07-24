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


class MessageOut(CamelModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    content: str
    sender: UserOut
    created_at: datetime
    updated_at: datetime
    edited_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


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
