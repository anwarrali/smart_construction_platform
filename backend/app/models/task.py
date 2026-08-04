"""
Task management: Task, TaskDependency (for Gantt/critical path),
and TaskRescheduleLog (auto-reschedule audit trail).
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Table, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DependencyType, RescheduleReason, TaskPriority, TaskStatus


task_assignees = Table(
    "task_assignees",
    Base.metadata,
    Column("task_id", UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("task_id", "user_id", name="uq_task_assignee_pair"),
)


class Task(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("duration_days IS NULL OR duration_days >= 1", name="ck_tasks_duration_days_positive"),
        UniqueConstraint("project_id", "task_code", name="uq_tasks_project_task_code"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    task_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0, index=True)

    discipline: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # e.g. structural, architectural, electrical, mechanical, civil, plumbing

    status: Mapped[TaskStatus] = mapped_column(
        PG_ENUM(TaskStatus, name="task_status", create_type=True),
        nullable=False,
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.name,
        index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        PG_ENUM(TaskPriority, name="task_priority", create_type=True),
        nullable=False,
        default=TaskPriority.MEDIUM,
        server_default=TaskPriority.MEDIUM.name,
        index=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    planned_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    duration_days: Mapped[int | None] = mapped_column(nullable=True)
    progress_percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)

    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    review_due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    voice_evidence_requirements: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    submitted_for_review_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    reviewed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    consultant_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str | None] = mapped_column(String(30), nullable=True)

    is_critical_path: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_milestone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Free float / total float, in days, used for critical path + auto reschedule calculations
    total_float_days: Mapped[int | None] = mapped_column(nullable=True)

    project: Mapped["Project"] = relationship(back_populates="tasks")
    milestone: Mapped["Milestone | None"] = relationship(back_populates="tasks")
    assignees: Mapped[list["User"]] = relationship(
        secondary=task_assignees,
        back_populates="assigned_tasks",
        order_by="User.full_name",
    )
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])

    # Dependencies where this task is the "downstream/successor" task
    dependencies: Mapped[list["TaskDependency"]] = relationship(
        back_populates="task",
        foreign_keys="TaskDependency.task_id",
        cascade="all, delete-orphan",
    )
    # Dependencies where this task is the "upstream/predecessor" task
    dependents: Mapped[list["TaskDependency"]] = relationship(
        back_populates="depends_on_task",
        foreign_keys="TaskDependency.depends_on_task_id",
    )

    reschedule_logs: Mapped[list["TaskRescheduleLog"]] = relationship(
        back_populates="task",
        foreign_keys="[TaskRescheduleLog.task_id]",
        cascade="all, delete-orphan"
    )
    site_reports: Mapped[list["SiteReport"]] = relationship(back_populates="task")
    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="task")

    @property
    def assignee_ids(self) -> list[uuid.UUID]:
        return [assignee.id for assignee in self.assignees]

    def __repr__(self) -> str:
        return f"<Task id={self.id} name={self.name} status={self.status}>"


class TaskDependency(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Edge in the task dependency graph: `task_id` depends on `depends_on_task_id`.
    Powers critical-path identification and automatic rescheduling.
    """

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependency_pair"),
        CheckConstraint("task_id != depends_on_task_id", name="ck_task_dependency_not_self"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dependency_type: Mapped[DependencyType] = mapped_column(
        PG_ENUM(DependencyType, name="dependency_type", create_type=True),
        nullable=False,
        default=DependencyType.FINISH_TO_START,
        server_default=DependencyType.FINISH_TO_START.name,
    )
    lag_days: Mapped[int] = mapped_column(nullable=False, default=0)

    task: Mapped["Task"] = relationship(back_populates="dependencies", foreign_keys=[task_id])
    depends_on_task: Mapped["Task"] = relationship(
        back_populates="dependents", foreign_keys=[depends_on_task_id]
    )

    @property
    def depends_on_task_code(self) -> str | None:
        return self.depends_on_task.task_code if self.depends_on_task else None

    @property
    def depends_on_task_name(self) -> str | None:
        return self.depends_on_task.name if self.depends_on_task else None

    @property
    def depends_on_task_status(self) -> TaskStatus | None:
        return self.depends_on_task.status if self.depends_on_task else None


class TaskRescheduleLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Audit trail every time a task's dates are shifted automatically
    (or manually) due to an upstream delay.
    """

    __tablename__ = "task_reschedule_logs"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_by_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    reason: Mapped[RescheduleReason] = mapped_column(
        PG_ENUM(RescheduleReason, name="reschedule_reason", create_type=True),
        nullable=False,
        default=RescheduleReason.MANUAL,
        server_default=RescheduleReason.MANUAL.name,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    previous_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    new_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    new_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shift_days: Mapped[int] = mapped_column(nullable=False, default=0)

    is_automatic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    task: Mapped["Task"] = relationship(back_populates="reschedule_logs", foreign_keys=[task_id])
    triggered_by_task: Mapped["Task"] = relationship(foreign_keys=[triggered_by_task_id])
    triggered_by_user: Mapped["User"] = relationship(foreign_keys=[triggered_by_user_id])


class TaskComment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "task_comments"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    task: Mapped["Task"] = relationship()
    author: Mapped["User"] = relationship(foreign_keys=[author_id])


class TaskReview(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "task_reviews"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submission_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_corrections: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarification_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarification_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarification_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clarification_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    resubmission_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_reviews.id", ondelete="SET NULL"), nullable=True
    )

    task: Mapped["Task"] = relationship()
    submitted_by: Mapped["User | None"] = relationship(foreign_keys=[submitted_by_id])
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])
    resubmission_of: Mapped["TaskReview | None"] = relationship(remote_side="TaskReview.id", foreign_keys=[resubmission_of_id])
