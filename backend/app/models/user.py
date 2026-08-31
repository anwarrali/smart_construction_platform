"""
User model for the five supported global roles. Engineering discipline and
company affiliation are separate from authorization roles.

Role-specific extra data lives in separate profile tables
(EngineerProfile, ContractorProfile) to keep this table lean and normalized.
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    #from app.models.company import Company
    from app.models.password_reset import PasswordResetToken
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EngineerDiscipline, UserRole, UserStatus


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        PG_ENUM(UserRole, name="user_role", create_type=True),
        nullable=False,
        index=True,
    )
    status: Mapped[UserStatus] = mapped_column(
        PG_ENUM(UserStatus, name="user_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=UserStatus.PENDING.value,
    )

    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invitation_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    organization: Mapped[str | None] = mapped_column(String(200), nullable=True)
    engineer_affiliation: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True
    )

    # --- Configurable RBAC ---------------------------------------------------
    # `role` above is the retired enum. It is still written and still read by
    # the legacy authorization path, which the equivalence gate compares
    # against, and it is dropped only in the final contract migration. Until
    # then `org_role_id` is the authority whenever it is set.

    #: The office role this person holds. NULL only before the backfill has
    #: run, or for an external participant who has no office membership.
    org_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    #: Consulting-office staff, as opposed to somebody from a contractor,
    #: subcontractor or the client. Replaces every read of
    #: `engineer_affiliation`. Denormalized from organization membership
    #: because it is checked on nearly every request.
    is_internal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True,
    )

    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notify_by_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_by_telegram: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    #: Read-only companions to `org_role_id` / `user_disciplines`, so a
    #: response schema can render the configured model without every endpoint
    #: assembling it by hand. Neither is a write path: roles are assigned
    #: through `rbac.assign_org_role` and disciplines through
    #: `rbac.set_user_disciplines`, which keep `is_internal` and the
    #: organization membership in step.
    org_role: Mapped["Role | None"] = relationship(
        "Role", foreign_keys=[org_role_id], lazy="joined", viewonly=True,
    )
    disciplines: Mapped[list["Discipline"]] = relationship(
        "Discipline",
        secondary="user_disciplines",
        primaryjoin="User.id == UserDiscipline.user_id",
        secondaryjoin="UserDiscipline.discipline_id == Discipline.id",
        order_by="Discipline.rank",
        viewonly=True,
    )

    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    engineer_profile: Mapped["EngineerProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    owned_projects: Mapped[list["Project"]] = relationship(
        back_populates="owner", foreign_keys="Project.owner_id"
    )
    # `project_members.user_id` is NOT NULL with `ondelete="CASCADE"` at the
    # database level. Without `passive_deletes=True`, SQLAlchemy's
    # unit-of-work does not trust that constraint: on `db.delete(user)` it
    # loads this collection itself and tries to *nullify* `user_id` on each
    # row first (the default ORM behaviour for a collection with no delete
    # cascade), which fails with a NOT NULL violation before the DB's own
    # CASCADE ever gets a chance to run. `passive_deletes=True` defers
    # entirely to the database, which already does the right thing.
    project_memberships: Mapped[list["ProjectMember"]] = relationship(
        back_populates="user", foreign_keys="ProjectMember.user_id", passive_deletes=True
    )
    assigned_tasks: Mapped[list["Task"]] = relationship(
        secondary="task_assignees", back_populates="assignees"
    )
    company: Mapped["Company | None"] = relationship(back_populates="users")
    # Push delivery addresses. `passive_deletes` for the same reason as
    # `project_memberships`: the FK already cascades in the database.
    device_tokens: Mapped[list["DeviceToken"]] = relationship(
        back_populates="user", passive_deletes=True
    )


    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


class EngineerProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Extra fields specific to engineer-role users (any discipline)."""

    __tablename__ = "engineer_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    discipline: Mapped[EngineerDiscipline] = mapped_column(
        PG_ENUM(EngineerDiscipline, name="engineer_discipline", create_type=True),
        nullable=False,
        index=True,
    )
    license_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    years_of_experience: Mapped[int | None] = mapped_column(nullable=True)
    employee_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    can_act_as_project_manager: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # only architect/civil normally true

    user: Mapped["User"] = relationship(back_populates="engineer_profile")


