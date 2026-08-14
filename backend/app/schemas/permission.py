from uuid import UUID

from pydantic import Field

from app.schemas.user import CamelModel


class PermissionOut(CamelModel):
    code: str
    group: str
    label: str
    description: str
    default_roles: list[str]
    project_scoped: bool
    admin_locked: bool


class RolePermissionState(CamelModel):
    role: str
    permission_code: str
    #: What the catalogue says before any configuration.
    default_allowed: bool
    #: What is actually in force after the administrator's changes.
    effective_allowed: bool
    overridden: bool


class RolePermissionUpdate(CamelModel):
    role: str = Field(max_length=40)
    permission_code: str = Field(max_length=80)
    #: null clears the override and returns the role to its default.
    allowed: bool | None = None
    reason: str | None = Field(default=None, max_length=500)


class UserPermissionUpdate(CamelModel):
    permission_code: str = Field(max_length=80)
    allowed: bool | None = None
    project_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=500)


class UserPermissionOverrideOut(CamelModel):
    id: UUID
    user_id: UUID
    project_id: UUID | None = None
    permission_code: str
    allowed: bool
    reason: str | None = None


class UserPermissionSummary(CamelModel):
    user_id: UUID
    full_name: str
    email: str
    role: str
    status: str
    project_id: UUID | None = None
    effective_permissions: list[str]
    overrides: list[UserPermissionOverrideOut]


class ConsultantScopeUpdate(CamelModel):
    project_id: UUID
    consultant_user_id: UUID
    #: The complete set of engineers this consultant covers. An empty list
    #: removes the restriction entirely.
    engineer_user_ids: list[UUID] = Field(default_factory=list, max_length=200)


class ConsultantScopeOut(CamelModel):
    project_id: UUID
    consultant_user_id: UUID
    consultant_name: str
    approval_mode: str
    disciplines: list[str | None]
    engineer_user_ids: list[UUID]
