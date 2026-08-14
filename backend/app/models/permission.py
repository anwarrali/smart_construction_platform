"""Administrator-configured deviations from the default role permissions.

Nothing here grants anything on its own. The catalogue in
`app.core.permission_catalogue` states what each role can do out of the box;
these tables record the specific decisions an administrator has made on top of
it, so an organisation with an unusual structure can be supported without
forking the role model.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import UserRole
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class RolePermissionOverride(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grant or revoke a permission for a whole role, platform-wide."""

    __tablename__ = "role_permission_overrides"
    __table_args__ = (
        UniqueConstraint("role", "permission_code", name="uq_role_permission_override"),
    )

    role: Mapped[UserRole] = mapped_column(
        PG_ENUM(UserRole, name="user_role", create_type=False), nullable=False, index=True
    )
    permission_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    #: True grants, False revokes. There is no third state: absence of a row
    #: means "fall back to the role default".
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


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
