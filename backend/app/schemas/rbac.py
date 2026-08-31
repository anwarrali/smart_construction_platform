"""Request and response shapes for configurable roles, disciplines and parties."""

from uuid import UUID

from pydantic import Field, field_validator

from app.core.role_templates import PARTY_KINDS
from app.schemas.user import CamelModel

SCOPES = {"ORG", "PROJECT", "BOTH"}


class RoleOut(CamelModel):
    id: UUID
    code: str
    name_en: str
    name_ar: str | None = None
    description: str | None = None
    scope: str
    is_internal_only: bool
    is_system: bool
    undeletable: bool
    rank: int
    is_active: bool
    #: Permission codes the role grants. Present on the detail endpoint.
    permissions: list[str] = Field(default_factory=list)
    #: How many people hold it, so an administrator can see what a change costs
    #: before making it.
    member_count: int = 0


class RoleCreate(CamelModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z][a-z0-9_]*$")
    name_en: str = Field(min_length=1, max_length=120)
    name_ar: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    scope: str = "BOTH"
    is_internal_only: bool = True
    rank: int = 100
    permissions: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("scope")
    @classmethod
    def _known_scope(cls, value: str) -> str:
        if value not in SCOPES:
            raise ValueError(f"scope must be one of {', '.join(sorted(SCOPES))}")
        return value


class RoleUpdate(CamelModel):
    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    name_ar: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    scope: str | None = None
    is_internal_only: bool | None = None
    rank: int | None = None
    is_active: bool | None = None

    @field_validator("scope")
    @classmethod
    def _known_scope(cls, value: str | None) -> str | None:
        if value is not None and value not in SCOPES:
            raise ValueError(f"scope must be one of {', '.join(sorted(SCOPES))}")
        return value


class RolePermissionsUpdate(CamelModel):
    """The complete set of permissions the role should hold.

    A full replacement rather than a patch, because an administrator editing a
    role is looking at a checklist and expects what they see to be what is
    saved. A patch API would make an unticked box ambiguous between "leave it"
    and "remove it".
    """

    permissions: list[str] = Field(default_factory=list, max_length=200)


class DisciplineOut(CamelModel):
    id: UUID
    code: str
    name_en: str
    name_ar: str | None = None
    ifc_disciplines: list[str] = Field(default_factory=list)
    rank: int
    is_active: bool


class DisciplineCreate(CamelModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z][a-z0-9_]*$")
    name_en: str = Field(min_length=1, max_length=120)
    name_ar: str | None = Field(default=None, max_length=120)
    #: IFC classification names this discipline covers, so coordination
    #: findings route to the right people.
    ifc_disciplines: list[str] = Field(default_factory=list, max_length=40)
    rank: int = 100


class DisciplineUpdate(CamelModel):
    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    name_ar: str | None = Field(default=None, max_length=120)
    ifc_disciplines: list[str] | None = Field(default=None, max_length=40)
    rank: int | None = None
    is_active: bool | None = None


class ProjectPartyOut(CamelModel):
    id: UUID
    project_id: UUID
    kind: str
    display_name: str
    parent_party_id: UUID | None = None
    is_primary: bool
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None
    is_active: bool
    #: People from this party who have access to the project.
    member_count: int = 0


class ProjectPartyCreate(CamelModel):
    kind: str
    display_name: str = Field(min_length=1, max_length=200)
    parent_party_id: UUID | None = None
    is_primary: bool = False
    contact_name: str | None = Field(default=None, max_length=150)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in PARTY_KINDS:
            raise ValueError(f"kind must be one of {', '.join(PARTY_KINDS)}")
        return value


class ProjectPartyUpdate(CamelModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_party_id: UUID | None = None
    is_primary: bool | None = None
    contact_name: str | None = Field(default=None, max_length=150)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class DocumentShareCreate(CamelModel):
    party_id: UUID
    note: str | None = Field(default=None, max_length=500)


class DocumentShareOut(CamelModel):
    id: UUID
    document_id: UUID
    party_id: UUID
    party_name: str
    note: str | None = None


class UserDisciplinesUpdate(CamelModel):
    discipline_ids: list[UUID] = Field(default_factory=list, max_length=30)
    primary_discipline_id: UUID | None = None


class OrgRoleAssignment(CamelModel):
    role_id: UUID
    job_title: str | None = Field(default=None, max_length=120)
