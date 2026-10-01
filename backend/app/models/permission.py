"""Administrator decisions about one person, and consultant review scopes.

What a *role* may do lives in `roles` / `role_permissions`, edited through the
organization API. These tables record decisions about individuals: a
permission granted or revoked for one person (everywhere, or on one project),
and which engineers a consultant reviews.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class UserPermissionOverride(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grant or revoke a permission for one person.

    `project_id` NULL means the decision applies everywhere; a project id
    narrows it to that project, which is how a consultant can be given review
    authority on one project without gaining it on the rest.
    """

    __tablename__ = "user_permission_overrides"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "permission_code", "project_id",
            name="uq_user_permission_override",
        ),
        Index("ix_user_permission_lookup", "user_id", "permission_code"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    permission_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class ConsultantEngineerScope(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Narrows a consultant's review authority to named engineers.

    The project already supports consultants scoped by discipline, or given
    project-wide authority. Some organisations divide the work by person
    instead: one consultant reviews these three engineers, another reviews the
    rest. When a consultant has no rows here they keep whatever authority their
    discipline assignment already gives them, so this is additive and existing
    projects are unaffected.
    """

    __tablename__ = "consultant_engineer_scopes"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "consultant_user_id", "engineer_user_id",
            name="uq_consultant_engineer_scope",
        ),
        Index("ix_consultant_scope_lookup", "project_id", "consultant_user_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consultant_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engineer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    consultant: Mapped["User"] = relationship(foreign_keys=[consultant_user_id])
    engineer: Mapped["User"] = relationship(foreign_keys=[engineer_user_id])
