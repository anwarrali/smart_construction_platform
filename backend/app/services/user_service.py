"""User provisioning for invite-only enterprise auth.

An account is created under one of the **office's own configured roles**.
`org_role` decides everything about the account's authority: the permissions
it holds and whether the person is office staff. There is no other way to say
what somebody is — the retired six-value role enum is gone.
"""

import secrets
import string
import uuid
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.enums import EngineerDiscipline, UserStatus
from app.models.project import ProjectMember
from app.models.rbac import Role
from app.models.user import EngineerProfile, User
from app.core.security import hash_password
from app.services import rbac
from app.services.authorization import require
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


def create_provisioned_user(
    db: Session,
    *,
    creator: User,
    email: str,
    full_name: str,
    org_role: Role,
    discipline_ids: Optional[list[uuid.UUID]] = None,
    phone_number: Optional[str] = None,
    organization: Optional[str] = None,
    company_id: Optional[uuid.UUID] = None,
    engineer_discipline: Optional[EngineerDiscipline] = None,
    employee_id: Optional[str] = None,
    password: Optional[str] = None,
    send_email: bool = True,
) -> Tuple[User, str]:
    """Create an account under `org_role`, with an administrator-supplied or generated password.

    Refuses an archived role: those exist only to keep history attributable,
    and no account may be minted on one. That is an invariant, not a
    permission — an office cannot make it provisionable by granting something.
    """
    require(db, creator, "platform.manage_users")

    if org_role is None:
        raise ValueError("An office role is required to create an account")
    if org_role.is_archived:
        raise ValueError(f"Role '{org_role.code}' cannot be used to create accounts")

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
        phone_number=phone_number,
        organization=organization,
        company_id=resolved_company_id,
        status=UserStatus.ACTIVE if direct_account else UserStatus.PENDING,
        must_change_password=not direct_account,
        invitation_accepted=direct_account,
        is_email_verified=direct_account,
    )
    # The role goes on before the row is written: `users.org_role_id` is NOT
    # NULL, and `apply_org_role` moves `is_internal` with it.
    rbac.apply_org_role(user, org_role)
    db.add(user)
    db.flush()

    # The membership behind the role needs the account's id.
    rbac.assign_org_role(
        db, user=user, role=org_role,
        organization_id=resolved_company_id or rbac.ensure_tenant_organization(db).id,
    )
    if discipline_ids:
        rbac.set_user_disciplines(
            db, user=user, discipline_ids=list(discipline_ids),
            primary_id=discipline_ids[0],
        )

    # An engineering profile is recorded when the request describes one. It
    # used to be created for every account whose legacy role was ENGINEER,
    # defaulting the discipline to CIVIL when none was given — a value nobody
    # had chosen.
    if engineer_discipline is not None:
        db.add(
            EngineerProfile(
                user_id=user.id,
                discipline=engineer_discipline,
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
            role_label=org_role.name_en,
            invited_by=creator.full_name,
        )

    return user, account_password


def add_user_to_project(
    db: Session,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ProjectMember:
    """Make this person an active member of the project.

    The membership states only that they are on the project. What they may do
    there is their office role, plus the project role and party set on the
    membership by the caller.
    """
    existing = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        .first()
    )
    if existing:
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    member = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        is_active=True,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member
