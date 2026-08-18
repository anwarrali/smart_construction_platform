"""Normalized project conversations, participants, read state, and messages."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConversationType


class Conversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_project_activity", "project_id", "last_activity_at"),
        Index("ix_conversations_context", "project_id", "context_type", "context_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    type: Mapped[ConversationType] = mapped_column(
        PG_ENUM(ConversationType, name="conversation_type", create_type=True),
        nullable=False, index=True,
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    context_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    context_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    recipient_group: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    project: Mapped["Project"] = relationship(back_populates="conversations")
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    participants: Mapped[list["ConversationParticipant"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class ConversationParticipant(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "conversation_participants"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant"),
        Index("ix_conversation_participants_user_conversation", "user_id", "conversation_id"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_read_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="participants")
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    last_read_message: Mapped["Message | None"] = relationship(
        foreign_keys=[last_read_message_id], post_update=True
    )


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("length(btrim(content)) > 0", name="ck_messages_content_not_blank"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="NORMAL", server_default="NORMAL", index=True)
    requires_acknowledgement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    requires_response: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    responded_to_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Forwarding: `content` on a forward is the forwarder's own note (or a
    # short default when they added none) — it never overwrites or duplicates
    # the original. `forwarded_from_message_id` is the message the forwarder
    # actually selected (which may itself be a forward); `forward_origin_message_id`
    # is resolved once at forward time to the first, non-forwarded message in
    # the chain, so a message forwarded several times still shows its true
    # original sender without a recursive walk on every read.
    forwarded_from_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    forward_origin_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Entity sharing (Issues, Tasks, Site Reports, Design Changes, Documents,
    # …): mirrors `Conversation.context_type`/`context_id` — same shape,
    # deliberately not a foreign key, since it points across whichever table
    # `shared_entity_type` names. This is a property of this one message
    # (which project entity prompted it), not of the whole conversation, so it
    # cannot simply reuse the conversation's own context fields: one DIRECT
    # thread can carry shares of several different entities over time, and
    # sharing must never enroll the recipient in the entity's own contextual
    # discussion (that would silently change who can see/post there — a
    # bigger side effect than "send this person a message").
    shared_entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    shared_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sender: Mapped["User"] = relationship(foreign_keys=[sender_id])
    forwarded_from: Mapped["Message | None"] = relationship(
        remote_side="Message.id", foreign_keys=[forwarded_from_message_id]
    )
    forward_origin: Mapped["Message | None"] = relationship(
        remote_side="Message.id", foreign_keys=[forward_origin_message_id]
    )
