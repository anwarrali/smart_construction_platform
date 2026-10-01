from uuid import UUID

from pydantic import Field

from app.schemas.user import CamelModel


class PermissionOut(CamelModel):
    code: str
    group: str
    label: str
    description: str
    project_scoped: bool
    admin_locked: bool
    #: No external role inherits it; an administrator may still delegate it
    #: to one named outside person on one project.
    office_only: bool = False
    #: Never held by an external participant, whatever is configured.
    never_external: bool = False


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
    #: The person's office role.
    role_code: str | None = None
    role_name: str | None = None
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
