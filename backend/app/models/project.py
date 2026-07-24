
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConsultantApprovalMode, ProjectStatus, UserRole


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_type: Mapped[str | None] = mapped_column(String(100), nullable=True)  # residential, commercial...

    status: Mapped[ProjectStatus] = mapped_column(
        PG_ENUM(ProjectStatus, name="project_status", create_type=True),
        nullable=False,
        default=ProjectStatus.PLANNING,
        server_default=ProjectStatus.PLANNING.name,
        index=True,
    )

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    budget_total: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    budget_spent: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, default=0)

    completion_percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    consultant_approval_mode: Mapped[ConsultantApprovalMode] = mapped_column(
        PG_ENUM(ConsultantApprovalMode, name="consultant_approval_mode", create_type=True),
        nullable=False,
        default=ConsultantApprovalMode.DISCIPLINE_BASED_REVIEW,
        server_default=ConsultantApprovalMode.DISCIPLINE_BASED_REVIEW.name,
    )

    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    task_code_counter: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    milestone_code_counter: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")

    company: Mapped["Company | None"] = relationship(back_populates="projects")
    owner: Mapped["User | None"] = relationship(back_populates="owned_projects", foreign_keys=[owner_id])
    project_manager: Mapped["User | None"] = relationship(foreign_keys=[project_manager_id])

    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    consultant_reviewer_assignments: Mapped[list["ProjectConsultantReviewer"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    cost_validations: Mapped[list["CostValidation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    design_changes: Mapped[list["DesignChange"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    issues: Mapped[list["Issue"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    reports: Mapped[list["SiteReport"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    photo_categories: Mapped[list["PhotoCategory"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name} status={self.status}>"


class ProjectMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Links a User to a Project with a role-on-project (team assignment)."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_on_project: Mapped[UserRole] = mapped_column(
        PG_ENUM(UserRole, name="user_role", create_type=False),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    assignment_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    project_discipline: Mapped[str | None] = mapped_column(String(30), nullable=True)
    project_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_site_engineer: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False, index=True
    )
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="project_memberships", foreign_keys=[user_id])
    assigned_by: Mapped["User | None"] = relationship(foreign_keys=[assigned_by_id])


class ProjectConsultantReviewer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Project-scoped consultant authority; NULL discipline denotes centralized authority."""

    __tablename__ = "project_consultant_reviewers"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_id", "discipline",
            name="uq_project_consultant_reviewer_assignment",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    discipline: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped["Project"] = relationship(back_populates="consultant_reviewer_assignments")
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    assigned_by: Mapped["User | None"] = relationship(foreign_keys=[assigned_by_id])
