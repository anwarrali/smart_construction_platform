"""User provisioning for invite-only enterprise auth.

An account is created under one of the **office's own configured roles**, not
under a fixed enum. `org_role` is the input that matters: it decides the
permissions the account holds, whether the person is office staff, and — for
as long as `users.role` exists — which legacy value that column is written
with (`Role.legacy_role`, recorded on the role rather than guessed here).

The legacy `role` argument is still accepted, because the contract migration
has not run and several callers still speak that vocabulary. When both are
given the configured role wins; when only the legacy one is given the account
is created exactly as before and the pre-backfill fallback resolves it.
"""

import secrets
import string
import uuid
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.permissions import ROLE_LABELS
from app.models.enums import EngineerDiscipline, UserRole, UserStatus
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


def _resolve_engineer_discipline(role: UserRole, discipline: Optional[EngineerDiscipline]) -> EngineerDiscipline:
    if discipline:
        return discipline
    mapping = {UserRole.ENGINEER: EngineerDiscipline.CIVIL, UserRole.CONSULTANT: EngineerDiscipline.CIVIL}
    return mapping.get(role, EngineerDiscipline.CIVIL)


def legacy_role_for(org_role: Role) -> UserRole:
    """The retired enum value an account under this configured role is written with.

    Read from the role, never inferred from its permissions: an office that
    re-permissions a role must not thereby change what kind of account it
    creates.

    **Translation only.** This used to double as the archived-role provisioning
    guard, because the one template with no `legacy_role` was also the one
    nobody may be created under. That coincidence has been separated:
    `create_provisioned_user` refuses `Role.is_archived` before reaching here.
    The raise below remains as a defence for a role that is untranslatable for
    some other reason — it is no longer the rule, it is the backstop.
    """
    if not org_role.legacy_role:
        raise ValueError(
            f"Role '{org_role.code}' cannot be used to create accounts"
        )
    try:
        return UserRole[org_role.legacy_role]
    except KeyError as exc:  # pragma: no cover - guarded by a test
        raise ValueError(
            f"Role '{org_role.code}' records an unknown legacy role "
            f"'{org_role.legacy_role}'"
        ) from exc


def create_provisioned_user(
    db: Session,
    *,
    creator: User,
    email: str,
    full_name: str,
    role: Optional[UserRole] = None,
    org_role: Optional[Role] = None,
    discipline_ids: Optional[list[uuid.UUID]] = None,
    phone_number: Optional[str] = None,
    organization: Optional[str] = None,
    engineer_affiliation: Optional[str] = None,
    company_id: Optional[uuid.UUID] = None,
    engineer_discipline: Optional[EngineerDiscipline] = None,
    employee_id: Optional[str] = None,
    password: Optional[str] = None,
    send_email: bool = True,
) -> Tuple[User, str]:
    """Create a user with either an administrator-supplied or generated password.

    Pass `org_role` to create under one of the office's configured roles — the
    path the administrator UI uses. `role` alone is the legacy path, kept
    working until the contract migration.
    """
    # Provisioning authority is one question with one answer on both paths.
    # The legacy path used to ask `can_create_team_role(creator.role, role)`,
    # which read the retired enum on both sides and admitted nobody but an
    # ADMIN — so an office that granted `platform.manage_users` to a role of its
    # own still could not create accounts through it. Both paths now require the
    # permission the office can actually administer, which is what the
    # `org_role_id` path already required at the endpoint.
    require(db, creator, "platform.manage_users")

    if org_role is not None:
        # The configured role decides everything the legacy arguments used to.
        if org_role.is_archived:
            # The policy, stated against the flag that means it. This used to
            # fall out of `legacy_role_for` failing to translate a role with no
            # `legacy_role`, which was correct only for as long as that column
            # exists. Checked before translation so the refusal is about what
            # the role *is*, not about what could not be derived from it.
            raise ValueError(
                f"Role '{org_role.code}' cannot be used to create accounts"
            )
        role = legacy_role_for(org_role)
        engineer_affiliation = org_role.legacy_affiliation
    elif role is None:
        raise ValueError("An office role is required to create an account")
    elif role == UserRole.WORKER:
        # The other half of what `can_create_team_role` did. It refused WORKER
        # by leaving it out of a set, which is a rule nobody can see and which
        # disappears the moment the function does. Workers stopped being
        # platform users in the redesign; existing accounts were moved onto the
        # archived role above and no new one may be minted.
        #
        # Deliberately not a permission: an office must not be able to make this
        # provisionable by granting something, so it is an invariant rather than
        # a capability.
        raise ValueError("Worker accounts can no longer be created")

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

    # Every account gets a database role, including one created through the
    # legacy path. Without this, that path would mint accounts with
    # `org_role_id IS NULL` — which resolve through the pre-backfill fallback,
    # and which `RBAC_REQUIRE_DB_ROLES` turns into a hard failure. A creation
    # path that produces accounts the platform is about to refuse to serve is
    # not a fallback, it is a trap, so the legacy path resolves the seeded role
    # its enum maps to and assigns that.
    effective_role = org_role or rbac.template_role_for_legacy_user(db, user)
    if effective_role is not None:
        # `assign_org_role` sets `org_role_id` and `is_internal`, so the
        # account is resolved through the configured model from its first
        # request rather than through the pre-backfill fallback.
        rbac.assign_org_role(
            db, user=user, role=effective_role,
            organization_id=resolved_company_id or rbac.ensure_tenant_organization(db).id,
        )
        if discipline_ids:
            rbac.set_user_disciplines(
                db, user=user, discipline_ids=list(discipline_ids),
                primary_id=discipline_ids[0],
            )

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
