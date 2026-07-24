"""User provisioning for invite-only enterprise auth."""

import secrets
import string
import uuid
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.permissions import ROLE_LABELS, can_create_team_role
from app.models.enums import EngineerDiscipline, UserRole, UserStatus
from app.models.project import ProjectMember
from app.models.user import EngineerProfile, User
from app.core.security import hash_password
from app.services.email_service import send_invitation_email


def generate_temporary_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
        ):
            return password


def _resolve_engineer_discipline(role: UserRole, discipline: Optional[EngineerDiscipline]) -> EngineerDiscipline:
    if discipline:
        return discipline
    mapping = {UserRole.ENGINEER: EngineerDiscipline.CIVIL, UserRole.CONSULTANT: EngineerDiscipline.CIVIL}
    return mapping.get(role, EngineerDiscipline.CIVIL)


def create_provisioned_user(
    db: Session,
    *,
    creator: User,
    email: str,
    full_name: str,
    role: UserRole,
    phone_number: Optional[str] = None,
    organization: Optional[str] = None,
    engineer_affiliation: Optional[str] = None,
    company_id: Optional[uuid.UUID] = None,
    engineer_discipline: Optional[EngineerDiscipline] = None,
    employee_id: Optional[str] = None,
    password: Optional[str] = None,
    send_email: bool = True,
) -> Tuple[User, str]:
    """Create a user with either an administrator-supplied or generated password."""
    if not can_create_team_role(creator.role, role):
        raise ValueError(f"Role '{role.value}' cannot be created by {creator.role.value}")

    if role == UserRole.CONSULTANT:
        role = UserRole.ENGINEER
        engineer_affiliation = "external_consultant"

    existing = db.query(User).filter(User.email == email.lower().strip()).first()
    if existing:
        raise ValueError("A user with this email already exists")

    account_password = password or generate_temporary_password()
    direct_account = password is not None
    resolved_company_id = company_id or creator.company_id

    user = User(
        full_name=full_name.strip(),
        email=email.lower().strip(),
        hashed_password=hash_password(account_password),
        role=role,
        phone_number=phone_number,
        organization=organization,
        engineer_affiliation=(engineer_affiliation or "internal_engineer") if role == UserRole.ENGINEER else None,
        company_id=resolved_company_id,
        status=UserStatus.ACTIVE if direct_account else UserStatus.PENDING,
        must_change_password=not direct_account,
        invitation_accepted=direct_account,
        is_email_verified=direct_account,
    )
    db.add(user)
    db.flush()

    if role == UserRole.ENGINEER:
        discipline = _resolve_engineer_discipline(role, engineer_discipline)
        db.add(
            EngineerProfile(
                user_id=user.id,
                discipline=discipline,
                employee_id=employee_id,
                can_act_as_project_manager=False,
            )
        )

    db.commit()
    db.refresh(user)

    if send_email and not direct_account:
        send_invitation_email(
            to_email=user.email,
            full_name=user.full_name,
            temporary_password=account_password,
            role_label=ROLE_LABELS.get(role, role.value),
            invited_by=creator.full_name,
        )

    return user, account_password


def add_user_to_project(
    db: Session,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    role_on_project: UserRole,
) -> ProjectMember:
    existing = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        .first()
    )
    if existing:
        existing.is_active = True
        existing.role_on_project = role_on_project
        db.commit()
        db.refresh(existing)
        return existing

    member = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role_on_project=role_on_project,
        is_active=True,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member
