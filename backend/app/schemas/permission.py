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
    #: Another condition the server checks before this permission does anything.
    prerequisite: str | None = None
    #: Set for project-scoped codes: they apply only where the person reaches the project.
    scope_note: str | None = None


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


class PermissionDecisionOut(CamelModel):
    """Why one permission is or is not held — see `authorization.explain_permissions`."""

    code: str
    #: Membership of the effective set; the server's answer, not a recomputation.
    held: bool
    reason: str
    #: Whether the governing office or project role confers it.
    role_grants: bool
    #: The explicit decision at this scope; None means it inherits.
    override: bool | None = None


class UserPermissionSummary(CamelModel):
    user_id: UUID
    full_name: str
    email: str
    #: The person's office role.
    role_code: str | None = None
    role_name: str | None = None
    #: The role whose permissions apply: the office's copy when the account
    #: still points at a template the office has edited.
    governing_role_id: UUID | None = None
    governing_role_name: str | None = None
    governed_by_office_copy: bool = False
    status: str
    project_id: UUID | None = None
    effective_permissions: list[str]
    overrides: list[UserPermissionOverrideOut]
    decisions: list[PermissionDecisionOut] = Field(default_factory=list)


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
