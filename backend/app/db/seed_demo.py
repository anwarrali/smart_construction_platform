"""Safely seed the staging database with an idempotent demonstration project."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - configure all SQLAlchemy relationships
from app.core.security import hash_password
from app.db.bootstrap_admin import _require_alembic_head
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.enums import (
    ConsultantApprovalMode,
    ConversationType,
    DependencyType,
    EngineerDiscipline,
    FieldSubmissionStatus,
    IssueSeverity,
    IssueStatus,
    ProjectStatus,
    TaskPriority,
    TaskStatus,
    UserRole,
    UserStatus,
)
from app.models.field_submission import FieldSubmission, PhotoCategory
from app.models.issue import Issue
from app.models.message import Conversation, ConversationParticipant, Message
from app.models.milestone import Milestone
from app.models.project import Project, ProjectConsultantReviewer, ProjectMember
from app.models.task import Task, TaskDependency, TaskReview
from app.models.user import EngineerProfile, User


SEED_NAMESPACE = uuid.UUID("57473ba3-2a91-5f5d-8dd9-4d115c38b07c")
PROJECT_NAME = "Al-Nour Residential Building"


def stable_id(key: str) -> uuid.UUID:
    """Return the permanent UUID assigned to one demo-owned record."""
    return uuid.uuid5(SEED_NAMESPACE, key)


@dataclass(frozen=True)
class DemoSeedConfig:
    password: str
    environment: str
    bootstrap_email: str | None = None


def _load_boolean(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    if value in {"", "false", "0", "no"}:
        return False
    if value in {"true", "1", "yes"}:
        return True
    raise ValueError(f"{name} must be true or false")


def load_config() -> DemoSeedConfig | None:
    """Load the deliberately strict staging-only seed configuration."""
    if not _load_boolean("ENABLE_DEMO_SEED"):
        return None

    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    if environment != "staging":
        raise ValueError(
            "ENVIRONMENT must be exactly 'staging' when ENABLE_DEMO_SEED=true"
        )

    password = os.getenv("DEMO_USER_PASSWORD", "")
    if not password:
        raise ValueError("DEMO_USER_PASSWORD is required when demo seeding is enabled")
    if password != password.strip():
        raise ValueError(
            "DEMO_USER_PASSWORD must not contain leading or trailing whitespace"
        )
    if not 12 <= len(password) <= 128 or not all(
        (
            any(character.islower() for character in password),
            any(character.isupper() for character in password),
            any(character.isdigit() for character in password),
        )
    ):
        raise ValueError(
            "DEMO_USER_PASSWORD must contain 12-128 characters, including "
            "uppercase, lowercase, and numeric characters"
        )

    bootstrap_email = (
        os.getenv("DEMO_SEED_ADMIN_EMAIL", "").strip().lower()
        or os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        or None
    )
    return DemoSeedConfig(
        password=password,
        environment=environment,
        bootstrap_email=bootstrap_email,
    )


def _conflict(message: str) -> RuntimeError:
    return RuntimeError(f"Demo seed ownership conflict: {message}")


def _find_admin(db: Session, configured_email: str | None) -> User:
    query = db.query(User).filter(
        User.role == UserRole.ADMIN,
        User.is_superuser.is_(True),
        User.status.in_([UserStatus.ACTIVE, UserStatus.PENDING]),
    )
    if configured_email:
        admin = query.filter(func.lower(User.email) == configured_email).one_or_none()
        if not admin:
            raise RuntimeError(
                "BOOTSTRAP_ADMIN_EMAIL does not identify an active/pending superuser Admin"
            )
        return admin

    admins = query.all()
    if len(admins) != 1:
        raise RuntimeError(
            "Set BOOTSTRAP_ADMIN_EMAIL or ensure exactly one active/pending "
            "superuser Admin exists before demo seeding"
        )
    return admins[0]


def _ensure_company(
    db: Session, key: str, name: str, description: str, address: str
) -> Company:
    record_id = stable_id(f"company:{key}")
    by_id = db.get(Company, record_id)
    by_name = db.query(Company).filter(Company.name == name).one_or_none()
    if by_name and by_name.id != record_id:
        raise _conflict(f"company name '{name}' belongs to a non-demo record")
    if by_id:
        if by_id.name != name:
            raise _conflict(f"company UUID {record_id} has an unexpected name")
        return by_id
    company = Company(
        id=record_id,
        name=name,
        description=description,
        address=address,
        is_active=True,
    )
    db.add(company)
    return company


def _ensure_user(
    db: Session,
    *,
    key: str,
    email: str,
    full_name: str,
    role: UserRole,
    company: Company,
    password: str,
    organization: str | None = None,
    affiliation: str | None = None,
    discipline: EngineerDiscipline | None = None,
    license_number: str | None = None,
) -> User:
    record_id = stable_id(f"user:{key}")
    by_id = db.get(User, record_id)
    by_email = (
        db.query(User).filter(func.lower(User.email) == email.lower()).one_or_none()
    )
    if by_email and by_email.id != record_id:
        raise _conflict(
            f"user email '{email}' belongs to an existing non-demo account; "
            "its password and role were not changed"
        )
    if by_id:
        if (
            by_id.email.lower() != email.lower()
            or by_id.role != role
            or by_id.company_id != company.id
        ):
            raise _conflict(f"demo user '{email}' has unexpected identity fields")
        user = by_id
    else:
        user = User(
            id=record_id,
            email=email.lower(),
            full_name=full_name,
            hashed_password=hash_password(password),
            role=role,
            status=UserStatus.ACTIVE,
            is_email_verified=True,
            is_superuser=False,
            must_change_password=False,
            invitation_accepted=True,
            company_id=company.id,
            organization=organization,
            engineer_affiliation=affiliation,
        )
        db.add(user)

    if discipline is not None:
        profile_id = stable_id(f"engineer-profile:{key}")
        profile = db.get(EngineerProfile, profile_id)
        profile_by_user = (
            db.query(EngineerProfile)
            .filter(EngineerProfile.user_id == record_id)
            .one_or_none()
        )
        if profile_by_user and profile_by_user.id != profile_id:
            raise _conflict(f"engineer profile for '{email}' is not demo-owned")
        if profile:
            if profile.user_id != record_id or profile.discipline != discipline:
                raise _conflict(f"engineer profile for '{email}' is inconsistent")
        else:
            db.add(
                EngineerProfile(
                    id=profile_id,
                    user_id=record_id,
                    discipline=discipline,
                    license_number=license_number,
                    years_of_experience=8,
                    employee_id=f"DEMO-{key.upper()[:20]}",
                    can_act_as_project_manager=discipline
                    in {EngineerDiscipline.ARCHITECTURAL, EngineerDiscipline.CIVIL},
                )
            )
    return user


def _ensure_project(
    db: Session,
    owner_company: Company,
    owner: User,
    project_manager: User,
    anchor: date,
) -> Project:
    record_id = stable_id("project:al-nour-residential")
    by_id = db.get(Project, record_id)
    by_name = db.query(Project).filter(Project.name == PROJECT_NAME).one_or_none()
    if by_name and by_name.id != record_id:
        raise _conflict(f"project name '{PROJECT_NAME}' belongs to a non-demo project")
    if by_id:
        if by_id.name != PROJECT_NAME:
            raise _conflict(f"project UUID {record_id} has an unexpected name")
        return by_id
    project = Project(
        id=record_id,
        name=PROJECT_NAME,
        description=(
            "Eight-storey residential building with underground parking and "
            "coordinated architectural, structural, and MEP packages."
        ),
        location="Ramallah, Palestine",
        project_type="residential",
        status=ProjectStatus.ACTIVE,
        start_date=anchor - timedelta(days=90),
        planned_end_date=anchor + timedelta(days=240),
        budget_total=4_850_000,
        budget_spent=1_720_000,
        completion_percentage=38,
        company_id=owner_company.id,
        owner_id=owner.id,
        project_manager_id=project_manager.id,
        consultant_approval_mode=ConsultantApprovalMode.DISCIPLINE_BASED_REVIEW,
        task_code_counter=13,
        milestone_code_counter=4,
    )
    db.add(project)
    return project


def _ensure_membership(
    db: Session,
    project: Project,
    user: User,
    role: UserRole,
    title: str,
    discipline: str | None,
    admin: User,
    *,
    site_engineer: bool = False,
) -> ProjectMember:
    record_id = stable_id(f"membership:{project.id}:{user.id}")
    existing_pair = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
        .one_or_none()
    )
    if existing_pair and existing_pair.id != record_id:
        raise _conflict(f"membership for '{user.email}' is not demo-owned")
    membership = db.get(ProjectMember, record_id)
    if membership:
        if membership.role_on_project != role:
            raise _conflict(f"membership role for '{user.email}' is unexpected")
        return membership
    membership = ProjectMember(
        id=record_id,
        project_id=project.id,
        user_id=user.id,
        role_on_project=role,
        is_active=True,
        assignment_title=title,
        project_discipline=discipline,
        is_site_engineer=site_engineer,
        assigned_by_id=admin.id,
        project_notes="Created by the guarded staging demo seed.",
    )
    db.add(membership)
    return membership


def _ensure_reviewer(
    db: Session, project: Project, user: User, discipline: str, admin: User
) -> None:
    record_id = stable_id(f"reviewer:{project.id}:{user.id}:{discipline}")
    existing_pair = (
        db.query(ProjectConsultantReviewer)
        .filter(
            ProjectConsultantReviewer.project_id == project.id,
            ProjectConsultantReviewer.user_id == user.id,
            ProjectConsultantReviewer.discipline == discipline,
        )
        .one_or_none()
    )
    if existing_pair and existing_pair.id != record_id:
        raise _conflict(
            f"consultant reviewer assignment for '{user.email}' is not demo-owned"
        )
    if not db.get(ProjectConsultantReviewer, record_id):
        db.add(
            ProjectConsultantReviewer(
                id=record_id,
                project_id=project.id,
                user_id=user.id,
                discipline=discipline,
                assigned_by_id=admin.id,
            )
        )


def _ensure_milestones(
    db: Session, project: Project, admin: User, anchor: date
) -> dict[str, Milestone]:
    specs = [
        ("structure", "M-001", "Structural Frame Complete", -10, -7),
        ("envelope", "M-002", "Building Envelope Complete", 70, None),
        ("mep", "M-003", "MEP First Fix Complete", 105, None),
        ("handover", "M-004", "Practical Completion", 230, None),
    ]
    result: dict[str, Milestone] = {}
    for key, code, name, planned_offset, actual_offset in specs:
        record_id = stable_id(f"milestone:{key}")
        collision = (
            db.query(Milestone)
            .filter(
                Milestone.project_id == project.id,
                Milestone.milestone_code == code,
            )
            .one_or_none()
        )
        if collision and collision.id != record_id:
            raise _conflict(f"milestone code '{code}' is already in use")
        milestone = db.get(Milestone, record_id)
        if not milestone:
            milestone = Milestone(
                id=record_id,
                project_id=project.id,
                milestone_code=code,
                name=name,
                description=f"Demonstration milestone: {name}.",
                planned_date=anchor + timedelta(days=planned_offset),
                actual_date=(
                    anchor + timedelta(days=actual_offset)
                    if actual_offset is not None
                    else None
                ),
                created_by_id=admin.id,
            )
            db.add(milestone)
        result[key] = milestone
    return result


def _ensure_tasks(
    db: Session,
    project: Project,
    admin: User,
    users: dict[str, User],
    milestones: dict[str, Milestone],
    anchor: date,
) -> dict[str, Task]:
    specs = [
        ("site", "ANR-001", "Site Preparation", "civil", -90, -82, TaskStatus.DONE, TaskPriority.HIGH, 100, False, "structure", ["civil", "worker1"]),
        ("excavation", "ANR-002", "Excavation", "civil", -81, -68, TaskStatus.DONE, TaskPriority.HIGH, 100, False, "structure", ["civil", "worker1"]),
        ("foundations", "ANR-003", "Foundations", "civil", -67, -46, TaskStatus.DONE, TaskPriority.CRITICAL, 100, False, "structure", ["civil", "worker1"]),
        ("reinforcement", "ANR-004", "Reinforcement Installation", "civil", -45, -25, TaskStatus.DONE, TaskPriority.CRITICAL, 100, False, "structure", ["civil", "worker1"]),
        ("slab", "ANR-005", "Ground Floor Concrete Slab", "civil", -24, -9, TaskStatus.IN_PROGRESS, TaskPriority.CRITICAL, 70, False, "structure", ["civil", "worker1"]),
        ("masonry", "ANR-006", "Masonry Works", "architectural", -8, 4, TaskStatus.UNDER_REVIEW, TaskPriority.HIGH, 90, True, "envelope", ["architect", "worker1"]),
        ("electrical", "ANR-007", "Electrical Rough-In", "electrical", 5, 55, TaskStatus.UNDER_REVIEW, TaskPriority.HIGH, 85, True, "mep", ["electrical", "worker2"]),
        ("plumbing", "ANR-008", "Plumbing Rough-In", "mechanical", 8, 58, TaskStatus.IN_PROGRESS, TaskPriority.HIGH, 55, False, "mep", ["mechanical", "worker2"]),
        ("hvac", "ANR-009", "HVAC Installation", "mechanical", 59, 105, TaskStatus.BLOCKED, TaskPriority.MEDIUM, 20, False, "mep", ["mechanical", "worker2"]),
        ("doors", "ANR-010", "Door Installation", "architectural", -20, -2, TaskStatus.DONE, TaskPriority.MEDIUM, 100, True, "envelope", ["architect", "worker3"]),
        ("windows", "ANR-011", "Window Installation", "architectural", -5, 38, TaskStatus.REWORK_REQUIRED, TaskPriority.HIGH, 80, True, "envelope", ["architect", "worker3"]),
        ("finishing", "ANR-012", "Internal Finishing", "architectural", 146, 220, TaskStatus.TODO, TaskPriority.MEDIUM, 0, True, "handover", ["architect", "worker3"]),
        ("fire_alarm", "ANR-013", "Fire Alarm Installation", "electrical", 92, 145, TaskStatus.BACKLOG, TaskPriority.HIGH, 0, True, "handover", ["electrical", "worker2"]),
    ]
    result: dict[str, Task] = {}
    for order, spec in enumerate(specs, start=1):
        (
            key,
            code,
            name,
            discipline,
            start_offset,
            end_offset,
            status,
            priority,
            progress,
            review_required,
            milestone_key,
            assignee_keys,
        ) = spec
        record_id = stable_id(f"task:{key}")
        collision = (
            db.query(Task)
            .filter(Task.project_id == project.id, Task.task_code == code)
            .one_or_none()
        )
        if collision and collision.id != record_id:
            raise _conflict(f"task code '{code}' is already in use")
        task = db.get(Task, record_id)
        if task:
            if task.project_id != project.id or task.task_code != code:
                raise _conflict(f"task '{code}' has unexpected identity fields")
        else:
            start = anchor + timedelta(days=start_offset)
            end = anchor + timedelta(days=end_offset)
            submitted = status in {
                TaskStatus.UNDER_REVIEW,
                TaskStatus.REWORK_REQUIRED,
                TaskStatus.DONE,
            } and review_required
            approved = status == TaskStatus.DONE and review_required
            rejected = status == TaskStatus.REWORK_REQUIRED
            task = Task(
                id=record_id,
                project_id=project.id,
                milestone_id=milestones[milestone_key].id,
                name=name,
                task_code=code,
                description=f"{name} for the Al-Nour demonstration project.",
                sort_order=order,
                discipline=discipline,
                status=status,
                priority=priority,
                created_by_id=admin.id,
                planned_start_date=start,
                planned_end_date=end,
                actual_start_date=start if status not in {TaskStatus.TODO, TaskStatus.BACKLOG} else None,
                actual_end_date=end if status == TaskStatus.DONE else None,
                duration_days=(end - start).days + 1,
                progress_percentage=progress,
                review_required=review_required,
                review_due_date=end + timedelta(days=3) if review_required else None,
                submitted_for_review_at=anchor - timedelta(days=2) if submitted else None,
                reviewed_at=anchor - timedelta(days=1) if approved or rejected else None,
                reviewed_by_id=(
                    users["arch_consultant"].id
                    if approved or rejected
                    else None
                ),
                consultant_comments=(
                    "Installation accepted against the approved architectural details."
                    if approved
                    else None
                ),
                rejection_reason=(
                    "Several frames are out of tolerance; realign and resubmit evidence."
                    if rejected
                    else None
                ),
                review_status=(
                    "approved"
                    if approved
                    else "rejected"
                    if rejected
                    else "pending"
                    if submitted
                    else None
                ),
                is_critical_path=key
                in {"excavation", "foundations", "reinforcement", "slab", "masonry", "finishing"},
                total_float_days=0 if key in {"excavation", "foundations", "reinforcement", "slab", "masonry", "finishing"} else 5,
            )
            task.assignees = [users[user_key] for user_key in assignee_keys]
            db.add(task)
        result[key] = task
    return result


def _ensure_dependencies(db: Session, tasks: dict[str, Task]) -> None:
    pairs = [
        ("excavation", "site"),
        ("foundations", "excavation"),
        ("reinforcement", "foundations"),
        ("slab", "reinforcement"),
        ("masonry", "slab"),
        ("electrical", "masonry"),
        ("plumbing", "masonry"),
        ("hvac", "plumbing"),
        ("finishing", "electrical"),
        ("finishing", "plumbing"),
        ("finishing", "hvac"),
        ("finishing", "doors"),
        ("finishing", "windows"),
        ("finishing", "fire_alarm"),
        ("fire_alarm", "electrical"),
    ]
    for successor_key, predecessor_key in pairs:
        successor = tasks[successor_key]
        predecessor = tasks[predecessor_key]
        record_id = stable_id(f"dependency:{successor_key}:{predecessor_key}")
        collision = (
            db.query(TaskDependency)
            .filter(
                TaskDependency.task_id == successor.id,
                TaskDependency.depends_on_task_id == predecessor.id,
            )
            .one_or_none()
        )
        if collision and collision.id != record_id:
            raise _conflict(
                f"dependency {successor.task_code} -> {predecessor.task_code} "
                "is not demo-owned"
            )
        if not db.get(TaskDependency, record_id):
            db.add(
                TaskDependency(
                    id=record_id,
                    task_id=successor.id,
                    depends_on_task_id=predecessor.id,
                    dependency_type=DependencyType.FINISH_TO_START,
                    lag_days=1,
                )
            )


def _ensure_task_reviews(
    db: Session, tasks: dict[str, Task], users: dict[str, User], anchor: date
) -> None:
    now = datetime.combine(anchor, datetime.min.time(), tzinfo=timezone.utc)
    specs = [
        ("doors", "architect", "arch_consultant", "approved", None),
        ("masonry", "architect", None, "pending", None),
        ("windows", "architect", "arch_consultant", "rejected", "Realign window frames and attach new level measurements."),
        ("electrical", "electrical", None, "pending", None),
    ]
    for task_key, submitter_key, reviewer_key, status, rejection in specs:
        record_id = stable_id(f"task-review:{task_key}:1")
        review = db.get(TaskReview, record_id)
        if review:
            if review.task_id != tasks[task_key].id:
                raise _conflict(f"task review for '{task_key}' is inconsistent")
            continue
        db.add(
            TaskReview(
                id=record_id,
                task_id=tasks[task_key].id,
                submitted_by_id=users[submitter_key].id,
                reviewed_by_id=users[reviewer_key].id if reviewer_key else None,
                submission_number=1,
                submitted_at=now - timedelta(days=2),
                reviewed_at=now - timedelta(days=1) if reviewer_key else None,
                status=status,
                comments=(
                    "Approved for the demonstration workflow."
                    if status == "approved"
                    else None
                ),
                rejection_reason=rejection,
                required_corrections=rejection,
                completion_note="Work package submitted with inspection checklist.",
            )
        )


def _ensure_field_submissions(
    db: Session,
    project: Project,
    tasks: dict[str, Task],
    users: dict[str, User],
    anchor: date,
) -> None:
    now = datetime.combine(anchor, datetime.min.time(), tzinfo=timezone.utc)
    specs = [
        (
            "reinforcement",
            "worker1",
            FieldSubmissionStatus.SUBMITTED,
            "Reinforcement for footing F3 completed and ready for Engineer inspection.",
            None,
            None,
        ),
        (
            "electrical",
            "worker2",
            FieldSubmissionStatus.VERIFIED,
            "Electrical conduit installation completed in the east corridor.",
            "electrical",
            "Conduit spacing and supports verified against the approved method statement.",
        ),
        (
            "windows",
            "worker3",
            FieldSubmissionStatus.REJECTED,
            "Window frames installed on the north elevation.",
            "architect",
            "Frames at grids N4-N6 are out of plumb. Correct alignment and resubmit.",
        ),
    ]
    for task_key, worker_key, status, description, reviewer_key, comment in specs:
        record_id = stable_id(f"field-submission:{task_key}:{worker_key}")
        submission = db.get(FieldSubmission, record_id)
        if submission:
            if (
                submission.project_id != project.id
                or submission.task_id != tasks[task_key].id
                or submission.worker_id != users[worker_key].id
            ):
                raise _conflict(f"field submission for '{task_key}' is inconsistent")
            continue
        db.add(
            FieldSubmission(
                id=record_id,
                project_id=project.id,
                task_id=tasks[task_key].id,
                worker_id=users[worker_key].id,
                description=description,
                status=status,
                reviewed_at=now - timedelta(hours=8) if reviewer_key else None,
                reviewed_by_id=users[reviewer_key].id if reviewer_key else None,
                review_comment=comment,
            )
        )


def _ensure_categories(db: Session, project: Project, admin: User) -> None:
    for code, name in [
        ("waterproofing", "Waterproofing"),
        ("facade", "Facade"),
        ("fire_alarm", "Fire Alarm"),
    ]:
        record_id = stable_id(f"photo-category:{code}")
        collision = (
            db.query(PhotoCategory)
            .filter(PhotoCategory.project_id == project.id, PhotoCategory.code == code)
            .one_or_none()
        )
        if collision and collision.id != record_id:
            raise _conflict(f"photo category code '{code}' is already in use")
        if not db.get(PhotoCategory, record_id):
            db.add(
                PhotoCategory(
                    id=record_id,
                    name=name,
                    code=code,
                    project_id=project.id,
                    is_system=False,
                    active=True,
                    created_by_id=admin.id,
                )
            )


def _ensure_issues(
    db: Session,
    project: Project,
    tasks: dict[str, Task],
    users: dict[str, User],
    anchor: date,
) -> None:
    now = datetime.combine(anchor, datetime.min.time(), tzinfo=timezone.utc)
    specs = [
        ("delivery", "Material delivery delay", "slab", IssueSeverity.HIGH, IssueStatus.OPEN, "pm", "civil", True, None),
        ("routing", "Electrical routing conflict", "electrical", IssueSeverity.CRITICAL, IssueStatus.IN_PROGRESS, "electrical", "electrical", True, None),
        ("concrete", "Minor concrete defect requiring inspection", "foundations", IssueSeverity.MEDIUM, IssueStatus.RESOLVED, "civil", "civil", False, "Honeycombing was repaired using the approved non-shrink repair mortar."),
    ]
    for key, title, task_key, severity, status, raised_key, assigned_key, affects, resolution in specs:
        record_id = stable_id(f"issue:{key}")
        issue = db.get(Issue, record_id)
        if issue:
            if issue.project_id != project.id or issue.title != title:
                raise _conflict(f"issue '{title}' is inconsistent")
            continue
        db.add(
            Issue(
                id=record_id,
                project_id=project.id,
                task_id=tasks[task_key].id,
                title=title,
                description=f"Coordination item for {tasks[task_key].name}.",
                category="schedule" if key == "delivery" else "coordination" if key == "routing" else "quality",
                due_date=anchor + timedelta(days=7),
                affects_schedule=affects,
                severity=severity,
                status=status,
                raised_by_id=users[raised_key].id,
                assigned_to_id=users[assigned_key].id,
                resolution_notes=resolution,
                resolved_at=now - timedelta(days=1) if status == IssueStatus.RESOLVED else None,
            )
        )


def _ensure_conversation(
    db: Session,
    *,
    key: str,
    project: Project,
    conversation_type: ConversationType,
    title: str,
    creator: User,
    participants: list[User],
    messages: list[tuple[str, User]],
    anchor: date,
    context_type: str | None = None,
    context_id: uuid.UUID | None = None,
    recipient_group: str | None = None,
) -> None:
    conversation_id = stable_id(f"conversation:{key}")
    conversation = db.get(Conversation, conversation_id)
    now = datetime.combine(anchor, datetime.min.time(), tzinfo=timezone.utc)
    if conversation:
        if conversation.project_id != project.id or conversation.title != title:
            raise _conflict(f"conversation '{title}' is inconsistent")
    else:
        conversation = Conversation(
            id=conversation_id,
            project_id=project.id,
            type=conversation_type,
            title=title,
            created_by_id=creator.id,
            context_type=context_type,
            context_id=context_id,
            recipient_group=recipient_group,
            last_activity_at=now,
        )
        db.add(conversation)

    for user in participants:
        participant_id = stable_id(f"participant:{key}:{user.id}")
        collision = (
            db.query(ConversationParticipant)
            .filter(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user.id,
            )
            .one_or_none()
        )
        if collision and collision.id != participant_id:
            raise _conflict(
                f"participant '{user.email}' in conversation '{title}' is not demo-owned"
            )
        if not db.get(ConversationParticipant, participant_id):
            db.add(
                ConversationParticipant(
                    id=participant_id,
                    conversation_id=conversation_id,
                    user_id=user.id,
                    joined_at=now - timedelta(days=3),
                    last_read_at=now - timedelta(hours=1),
                )
            )

    for index, (content, sender) in enumerate(messages, start=1):
        message_id = stable_id(f"message:{key}:{index}")
        message = db.get(Message, message_id)
        if message:
            if message.conversation_id != conversation_id or message.sender_id != sender.id:
                raise _conflict(f"message {index} in conversation '{title}' is inconsistent")
            continue
        db.add(
            Message(
                id=message_id,
                conversation_id=conversation_id,
                sender_id=sender.id,
                content=content,
                created_at=now - timedelta(hours=len(messages) - index),
                updated_at=now - timedelta(hours=len(messages) - index),
            )
        )


def _ensure_messaging(
    db: Session,
    project: Project,
    tasks: dict[str, Task],
    users: dict[str, User],
    anchor: date,
) -> None:
    engineers = [
        users["pm"],
        users["architect"],
        users["civil"],
        users["electrical"],
        users["mechanical"],
        users["arch_consultant"],
        users["mep_consultant"],
    ]
    _ensure_conversation(
        db,
        key="coordination",
        project=project,
        conversation_type=ConversationType.GROUP,
        title="Weekly Coordination Updates",
        creator=users["pm"],
        participants=engineers,
        messages=[
            ("Please submit progress updates before the coordination meeting.", users["pm"]),
            ("Structural and masonry progress has been updated.", users["civil"]),
        ],
        anchor=anchor,
        recipient_group="project_engineers",
    )
    _ensure_conversation(
        db,
        key="electrical-task",
        project=project,
        conversation_type=ConversationType.CONTEXTUAL,
        title="Electrical Rough-In — Zone B Coordination",
        creator=users["electrical"],
        participants=[users["pm"], users["electrical"], users["mep_consultant"]],
        messages=[
            ("Electrical conduit route conflicts with ceiling layout in Zone B.", users["electrical"]),
            ("Use drawing revision E-12 and update the task evidence.", users["mep_consultant"]),
        ],
        anchor=anchor,
        context_type="task",
        context_id=tasks["electrical"].id,
    )
    _ensure_conversation(
        db,
        key="announcement",
        project=project,
        conversation_type=ConversationType.PROJECT_CHANNEL,
        title="Project Announcements",
        creator=users["pm"],
        participants=list(users.values()),
        messages=[
            ("Concrete pour moved to Sunday morning.", users["pm"]),
        ],
        anchor=anchor,
        recipient_group="all_project_members",
    )


def seed_demo(db: Session, config: DemoSeedConfig) -> str:
    """Create all demo-owned records in one transaction."""
    # Serialize simultaneous staging container starts without holding a lock
    # beyond this transaction. The seed remains safe with more than one replica.
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 5747330291})
    migration = _require_alembic_head(db)
    admin = _find_admin(db, config.bootstrap_email)
    anchor = date.today()

    owner_company = _ensure_company(
        db,
        "developer",
        "Al-Nour Developments",
        "Residential property owner and development company.",
        "Ramallah, Palestine",
    )
    contractor_company = _ensure_company(
        db,
        "contractor",
        "Al-Nour General Contracting",
        "Main contractor for the Al-Nour residential development.",
        "Al-Bireh, Palestine",
    )
    consultant_company = _ensure_company(
        db,
        "consultant",
        "Horizon Design Consultants",
        "Architectural and MEP design review consultancy.",
        "Ramallah, Palestine",
    )

    user_specs = [
        ("owner", "owner.demo@smartconstruction-demo.com", "Lina Al-Khatib", UserRole.OWNER, owner_company, None, None, None, None),
        ("pm", "pm.demo@smartconstruction-demo.com", "Omar Nasser", UserRole.PROJECT_MANAGER, owner_company, None, None, None, None),
        ("architect", "architect.contractor.demo@smartconstruction-demo.com", "Rana Haddad", UserRole.ENGINEER, contractor_company, contractor_company.name, "main_contractor", EngineerDiscipline.ARCHITECTURAL, "ARCH-DEMO-101"),
        ("civil", "civil.engineer.demo@smartconstruction-demo.com", "Yousef Khalil", UserRole.ENGINEER, contractor_company, contractor_company.name, "main_contractor", EngineerDiscipline.CIVIL, "CIV-DEMO-102"),
        ("electrical", "electrical.engineer.demo@smartconstruction-demo.com", "Maya Saleh", UserRole.ENGINEER, contractor_company, contractor_company.name, "main_contractor", EngineerDiscipline.ELECTRICAL, "ELEC-DEMO-103"),
        ("mechanical", "mechanical.engineer.demo@smartconstruction-demo.com", "Sami Darwish", UserRole.ENGINEER, contractor_company, contractor_company.name, "main_contractor", EngineerDiscipline.MECHANICAL, "MECH-DEMO-104"),
        ("arch_consultant", "architectural.consultant.demo@smartconstruction-demo.com", "Nour Mansour", UserRole.ENGINEER, consultant_company, consultant_company.name, "external_consultant", EngineerDiscipline.ARCHITECTURAL, "ARCH-CONS-DEMO-201"),
        ("mep_consultant", "mep.consultant.demo@smartconstruction-demo.com", "Tariq Odeh", UserRole.ENGINEER, consultant_company, consultant_company.name, "external_consultant", EngineerDiscipline.ELECTRICAL, "MEP-CONS-DEMO-202"),
        ("worker1", "worker.one.demo@smartconstruction-demo.com", "Ahmad Barakat", UserRole.WORKER, contractor_company, contractor_company.name, None, None, None),
        ("worker2", "worker.two.demo@smartconstruction-demo.com", "Bilal Hamdan", UserRole.WORKER, contractor_company, contractor_company.name, None, None, None),
        ("worker3", "worker.three.demo@smartconstruction-demo.com", "Kareem Zaid", UserRole.WORKER, contractor_company, contractor_company.name, None, None, None),
    ]
    users: dict[str, User] = {}
    for key, email, name, role, company, organization, affiliation, discipline, license_number in user_specs:
        users[key] = _ensure_user(
            db,
            key=key,
            email=email,
            full_name=name,
            role=role,
            company=company,
            password=config.password,
            organization=organization,
            affiliation=affiliation,
            discipline=discipline,
            license_number=license_number,
        )

    project = _ensure_project(db, owner_company, users["owner"], users["pm"], anchor)
    memberships = [
        ("owner", UserRole.OWNER, "Project Owner", None, False),
        ("pm", UserRole.PROJECT_MANAGER, "Project Manager", None, False),
        ("architect", UserRole.ENGINEER, "Architectural Contractor Engineer", "architectural", True),
        ("civil", UserRole.ENGINEER, "Civil Site Engineer", "civil", True),
        ("electrical", UserRole.ENGINEER, "Electrical Site Engineer", "electrical", True),
        ("mechanical", UserRole.ENGINEER, "Mechanical Site Engineer", "mechanical", True),
        ("arch_consultant", UserRole.CONSULTANT, "Architectural Consultant Reviewer", "architectural", False),
        ("mep_consultant", UserRole.CONSULTANT, "Electrical / MEP Consultant Reviewer", "electrical", False),
        ("worker1", UserRole.WORKER, "Civil Works Crew", "civil", False),
        ("worker2", UserRole.WORKER, "MEP Installation Crew", "electrical", False),
        ("worker3", UserRole.WORKER, "Architectural Finishes Crew", "architectural", False),
    ]
    for key, role, title, discipline, site_engineer in memberships:
        _ensure_membership(
            db,
            project,
            users[key],
            role,
            title,
            discipline,
            admin,
            site_engineer=site_engineer,
        )
    _ensure_reviewer(db, project, users["arch_consultant"], "architectural", admin)
    _ensure_reviewer(db, project, users["mep_consultant"], "electrical", admin)

    milestones = _ensure_milestones(db, project, admin, anchor)
    tasks = _ensure_tasks(db, project, admin, users, milestones, anchor)
    _ensure_dependencies(db, tasks)
    _ensure_task_reviews(db, tasks, users, anchor)
    _ensure_field_submissions(db, project, tasks, users, anchor)
    _ensure_categories(db, project, admin)
    _ensure_issues(db, project, tasks, users, anchor)
    _ensure_messaging(db, project, tasks, users, anchor)

    # AuditLog deliberately has no Project relationship, so establish all
    # referenced rows before inserting the immutable seed audit event.
    db.flush()
    audit_id = stable_id("audit:demo-seed-created")
    if not db.get(AuditLog, audit_id):
        db.add(
            AuditLog(
                id=audit_id,
                actor_id=admin.id,
                project_id=project.id,
                entity_type="project",
                entity_id=project.id,
                action="staging_demo_seed_created",
                details=json.dumps(
                    {
                        "seed": "app.db.seed_demo",
                        "namespace": str(SEED_NAMESPACE),
                        "environment": config.environment,
                    },
                    sort_keys=True,
                ),
            )
        )

    db.commit()
    return (
        f"Staging demo seed complete (project={PROJECT_NAME}, "
        f"project_id={project.id}, migration={migration}, demo_users={len(users)}). "
        "No password was logged."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--if-enabled",
        action="store_true",
        help="Exit successfully when ENABLE_DEMO_SEED is false or absent.",
    )
    parser.parse_args()

    try:
        config = load_config()
        if config is None:
            print("Staging demo seed skipped: ENABLE_DEMO_SEED is not true.")
            return 0
        with SessionLocal() as db:
            print(seed_demo(db, config))
        return 0
    except Exception as exc:
        print(f"Staging demo seed failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
