"""Role-based access control helpers for enterprise auth.

Legacy. The office configures its own roles now (`app.services.rbac`), and
`app.services.authorization` is the only module that decides what somebody may
do. What is left here backs account *provisioning* — which legacy enum value a
new account is created with — and nothing else. It goes with the rest of the
legacy path in the contract migration; see docs/RBAC.md.

`UserRole.WORKER` is absent from every set below on purpose: workers are not
platform users, so no new account can be provisioned as one. Existing worker
rows keep their enum value so their field evidence stays attributable, and the
backfill parks them on the permissionless `archived_field_staff` role.
"""

from app.models.enums import UserRole

# Primary enterprise roles requested by the product spec
PRIMARY_ROLES = {
    UserRole.ADMIN,
    UserRole.PROJECT_MANAGER,
    UserRole.ENGINEER,
    UserRole.CONSULTANT,
    UserRole.OWNER,
}

ENGINEER_ROLES = {UserRole.ENGINEER}

ROLE_LABELS = {
    UserRole.ADMIN: "Company Administrator",
    UserRole.PROJECT_MANAGER: "Project Manager",
    UserRole.ENGINEER: "Engineer",
    UserRole.CONSULTANT: "Consultant",
    UserRole.OWNER: "Owner",
}


def is_admin(role: UserRole) -> bool:
    return role == UserRole.ADMIN


def is_project_manager(role: UserRole) -> bool:
    return role == UserRole.PROJECT_MANAGER


def is_engineer(role: UserRole) -> bool:
    return role in ENGINEER_ROLES


def is_owner(role: UserRole) -> bool:
    return role == UserRole.OWNER


def can_manage_all_users(role: UserRole) -> bool:
    return role == UserRole.ADMIN


def can_create_project_manager(role: UserRole) -> bool:
    return role == UserRole.ADMIN


def can_create_project(role: UserRole) -> bool:
    return role == UserRole.ADMIN


def can_manage_project_members(role: UserRole) -> bool:
    return role in {UserRole.ADMIN, UserRole.PROJECT_MANAGER}


def can_create_team_role(creator_role: UserRole, target_role: UserRole) -> bool:
    """Who may provision which account types."""
    if creator_role == UserRole.ADMIN:
        return target_role in {
            UserRole.ADMIN,
            UserRole.PROJECT_MANAGER,
            UserRole.ENGINEER,
            UserRole.CONSULTANT,
            UserRole.OWNER,
        }
    return False


def normalize_engineer_role(role: UserRole) -> UserRole:
    return role
