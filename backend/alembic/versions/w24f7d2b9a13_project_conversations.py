"""normalized project conversations and per-user read state

Revision ID: w24f7d2b9a13
Revises: v23e6c1a8f02
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "w24f7d2b9a13"
down_revision = "v23e6c1a8f02"
branch_labels = None
depends_on = None

NAMESPACE = uuid.UUID("bb7414a5-a0b4-4f3e-88be-50aa3338d471")


def upgrade() -> None:
    conversation_type = postgresql.ENUM(
        "DIRECT", "GROUP", "PROJECT_CHANNEL", "CONTEXTUAL",
        name="conversation_type", create_type=False,
    )
    conversation_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "conversations",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", conversation_type, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("context_type", sa.String(length=40), nullable=True),
        sa.Column("context_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_group", sa.String(length=80), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])
    op.create_index("ix_conversations_type", "conversations", ["type"])
    op.create_index("ix_conversations_last_activity_at", "conversations", ["last_activity_at"])
    op.create_index(
        "ix_conversations_project_activity",
        "conversations", ["project_id", "last_activity_at"],
    )
    op.create_index(
        "ix_conversations_context",
        "conversations", ["project_id", "context_type", "context_id"],
    )

    op.add_column(
        "messages",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("messages", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("messages", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_messages_conversation_id", "messages", "conversations",
        ["conversation_id"], ["id"], ondelete="CASCADE",
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT id, project_id, sender_id, receiver_id, content, is_read, read_at,
               created_at, updated_at
        FROM messages
        ORDER BY created_at, id
    """)).mappings().all()
    grouped = {}
    for row in rows:
        pair = tuple(sorted((str(row["sender_id"]), str(row["receiver_id"]))))
        grouped.setdefault((str(row["project_id"]), pair), []).append(row)

    for (project_id, pair), messages in grouped.items():
        conversation_id = uuid.uuid5(
            NAMESPACE, f"legacy:{project_id}:{pair[0]}:{pair[1]}"
        )
        bind.execute(sa.text("""
            INSERT INTO conversations
                (id, project_id, type, created_by_id, last_activity_at, created_at, updated_at)
            VALUES
                (:id, :project_id, 'DIRECT', :created_by_id, :last_activity_at,
                 :created_at, :updated_at)
        """), {
            "id": conversation_id,
            "project_id": project_id,
            "created_by_id": messages[0]["sender_id"],
            "last_activity_at": messages[-1]["created_at"],
            "created_at": messages[0]["created_at"],
            "updated_at": messages[-1]["updated_at"],
        })
        bind.execute(sa.text("""
            UPDATE messages SET conversation_id = :conversation_id
            WHERE id = ANY(:message_ids)
        """), {
            "conversation_id": conversation_id,
            "message_ids": [row["id"] for row in messages],
        })

    op.alter_column("messages", "conversation_id", nullable=False)
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index(
        "ix_messages_conversation_created",
        "messages", ["conversation_id", "created_at"],
    )

    op.create_table(
        "conversation_participants",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_read_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_read_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant"),
    )
    op.create_index(
        "ix_conversation_participants_conversation_id",
        "conversation_participants", ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_participants_user_id",
        "conversation_participants", ["user_id"],
    )
    op.create_index(
        "ix_conversation_participants_user_conversation",
        "conversation_participants", ["user_id", "conversation_id"],
    )

    for (project_id, pair), messages in grouped.items():
        conversation_id = uuid.uuid5(
            NAMESPACE, f"legacy:{project_id}:{pair[0]}:{pair[1]}"
        )
        for user_id in pair:
            received_and_read = [
                row for row in messages
                if str(row["receiver_id"]) == user_id and row["is_read"]
            ]
            latest = received_and_read[-1] if received_and_read else None
            bind.execute(sa.text("""
                INSERT INTO conversation_participants
                    (id, conversation_id, user_id, joined_at,
                     last_read_message_id, last_read_at)
                VALUES
                    (:id, :conversation_id, :user_id, :joined_at,
                     :last_read_message_id, :last_read_at)
            """), {
                "id": uuid.uuid4(),
                "conversation_id": conversation_id,
                "user_id": user_id,
                "joined_at": messages[0]["created_at"],
                "last_read_message_id": latest["id"] if latest else None,
                "last_read_at": (
                    (latest["read_at"] or latest["created_at"]) if latest else None
                ),
            })

    op.drop_index("ix_messages_conversation", table_name="messages")
    op.drop_index("ix_messages_project_id", table_name="messages")
    op.drop_index("ix_messages_receiver_id", table_name="messages")
    op.drop_index("ix_messages_is_read", table_name="messages")
    op.drop_constraint("ck_messages_not_self", "messages", type_="check")
    op.drop_column("messages", "read_at")
    op.drop_column("messages", "is_read")
    op.drop_column("messages", "receiver_id")
    op.drop_column("messages", "project_id")


def downgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("receiver_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("is_read", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "messages",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "messages_project_id_fkey", "messages", "projects",
        ["project_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "messages_receiver_id_fkey", "messages", "users",
        ["receiver_id"], ["id"], ondelete="RESTRICT",
    )
    op.execute("""
        UPDATE messages m
        SET project_id = c.project_id,
            receiver_id = recipient.user_id,
            is_read = (
                recipient.last_read_at IS NOT NULL
                AND recipient.last_read_at >= m.created_at
            ),
            read_at = CASE
                WHEN recipient.last_read_at >= m.created_at THEN recipient.last_read_at
                ELSE NULL
            END
        FROM conversations c,
        LATERAL (
            SELECT cp.user_id, cp.last_read_at
            FROM conversation_participants cp
            WHERE cp.conversation_id = c.id AND cp.user_id <> m.sender_id
            ORDER BY cp.joined_at, cp.id
            LIMIT 1
        ) recipient
        WHERE c.id = m.conversation_id
    """)
    op.alter_column("messages", "project_id", nullable=False)
    op.alter_column("messages", "receiver_id", nullable=False)
    op.create_index("ix_messages_project_id", "messages", ["project_id"])
    op.create_index("ix_messages_receiver_id", "messages", ["receiver_id"])
    op.create_index("ix_messages_is_read", "messages", ["is_read"])
    op.create_index(
        "ix_messages_conversation",
        "messages", ["project_id", "sender_id", "receiver_id", "created_at"],
    )
    op.create_check_constraint(
        "ck_messages_not_self", "messages", "sender_id <> receiver_id"
    )

    op.drop_index(
        "ix_conversation_participants_user_conversation",
        table_name="conversation_participants",
    )
    op.drop_index(
        "ix_conversation_participants_user_id",
        table_name="conversation_participants",
    )
    op.drop_index(
        "ix_conversation_participants_conversation_id",
        table_name="conversation_participants",
    )
    op.drop_table("conversation_participants")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_constraint("fk_messages_conversation_id", "messages", type_="foreignkey")
    op.drop_column("messages", "deleted_at")
    op.drop_column("messages", "edited_at")
    op.drop_column("messages", "conversation_id")
    op.drop_index("ix_conversations_context", table_name="conversations")
    op.drop_index("ix_conversations_project_activity", table_name="conversations")
    op.drop_index("ix_conversations_last_activity_at", table_name="conversations")
    op.drop_index("ix_conversations_type", table_name="conversations")
    op.drop_index("ix_conversations_project_id", table_name="conversations")
    op.drop_table("conversations")
    postgresql.ENUM(name="conversation_type").drop(op.get_bind(), checkfirst=True)
