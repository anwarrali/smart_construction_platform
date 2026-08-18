"""Role-based access control helpers for enterprise auth."""

from app.models.enums import UserRole

# Primary enterprise roles requested by the product spec
PRIMARY_ROLES = {
    UserRole.ADMIN,
    UserRole.PROJECT_MANAGER,
    UserRole.ENGINEER,
    UserRole.CONSULTANT,
    UserRole.OWNER,
    UserRole.WORKER,
}

ENGINEER_ROLES = {UserRole.ENGINEER}

ROLE_LABELS = {
    UserRole.ADMIN: "Company Administrator",
    UserRole.PROJECT_MANAGER: "Project Manager",
    UserRole.ENGINEER: "Engineer",
    UserRole.CONSULTANT: "Consultant",
    UserRole.OWNER: "Owner",
    UserRole.WORKER: "Construction Worker",
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
            UserRole.WORKER,
        }
    return False


def normalize_engineer_role(role: UserRole) -> UserRole:
    return role
