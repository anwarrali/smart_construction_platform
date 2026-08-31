import re
from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator
from pydantic.alias_generators import to_camel
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.enums import UserRole, UserStatus, EngineerDiscipline

class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )

class EngineerProfileBase(CamelModel):
    discipline: EngineerDiscipline
    license_number: Optional[str] = None
    years_of_experience: Optional[int] = None
    employee_id: Optional[str] = None
    can_act_as_project_manager: bool = False

class EngineerProfileCreate(EngineerProfileBase):
    pass

class EngineerProfileOut(EngineerProfileBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

class UserBase(CamelModel):
    email: EmailStr
    full_name: str
    phone_number: Optional[str] = None
    avatar_url: Optional[str] = None
    role: UserRole
    telegram_chat_id: Optional[str] = None
    notify_by_email: bool = True
    notify_by_telegram: bool = False
    must_change_password: bool = False
    invitation_accepted: bool = False
    organization: Optional[str] = None
    engineer_affiliation: Optional[str] = None

PHONE_REGEX = re.compile(r'^\+?[\d\s\-()]{7,20}$')

class UserCreate(CamelModel):
    email: EmailStr
    full_name: str
    password: str = Field(..., min_length=8)
    role: UserRole
    phone_number: str
    engineer_profile: Optional[EngineerProfileCreate] = None

    @model_validator(mode='after')
    def validate_role_and_profiles(self) -> 'UserCreate':
        # 1. Validate phone number format
        if not self.phone_number or not PHONE_REGEX.match(self.phone_number):
            raise ValueError("Invalid phone number format. Must be 7-20 digits and can include +, -, spaces, or parentheses.")

        # Public registration is disabled at the route level. Keep this model
        # aligned with the supported company roles for internal callers/tests.
        allowed_registration_roles = {
            UserRole.OWNER,
            UserRole.PROJECT_MANAGER,
            UserRole.ENGINEER,
            UserRole.CONSULTANT,
        }
        if self.role not in allowed_registration_roles:
            raise ValueError(f"Registration is not allowed for role: {self.role.value}")

        # 3. Validate role-specific profiles
        if self.role in {UserRole.ENGINEER, UserRole.CONSULTANT}:
            if not self.engineer_profile:
                raise ValueError(f"{self.role.value} users require a specialization profile.")
        
        else:
            self.engineer_profile = None

        return self

class UserUpdate(CamelModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    avatar_url: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    notify_by_email: Optional[bool] = None
    notify_by_telegram: Optional[bool] = None
    engineer_profile: Optional[EngineerProfileCreate] = None


class UserAdminUpdate(CamelModel):
    """Edit an account, in the same vocabulary it was created in.

    `org_role_id` and `discipline_ids` are the configurable model. Without them
    an administrator could create somebody as a Surveyor covering Mechanical
    and Electrical and then never change either — the office role and the
    disciplines were write-once, which is not a model an office can run on.

    Both are optional and `None` means "leave alone", so a client sending only
    `full_name` does not silently clear somebody's disciplines. Sending an
    empty *list* does clear them, which is the difference between omitting a
    field and setting it to nothing.
    """

    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    org_role_id: Optional[UUID] = None
    discipline_ids: Optional[list[UUID]] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    organization: Optional[str] = None
    engineer_affiliation: Optional[str] = None
    engineer_profile: Optional[EngineerProfileCreate] = None

    @model_validator(mode='after')
    def validate_admin_update(self) -> 'UserAdminUpdate':
        if self.role and self.role not in {UserRole.ENGINEER, UserRole.CONSULTANT}:
            self.engineer_profile = None
        return self

class OrgRoleOut(CamelModel):
    """The office role an account holds, as the interface should show it."""

    id: UUID
    code: str
    name_en: str
    name_ar: Optional[str] = None
    is_internal_only: bool


class UserDisciplineOut(CamelModel):
    id: UUID
    code: str
    name_en: str
    name_ar: Optional[str] = None


class UserOut(UserBase):
    id: UUID
    status: UserStatus
    is_email_verified: bool
    is_superuser: bool
    last_login_at: Optional[str] = None
    engineer_profile: Optional[EngineerProfileOut] = None
    #: The configurable model. `org_role` is the authority; `role` on
    #: `UserBase` is the retired column, still emitted so a client that has not
    #: been updated keeps rendering, and dropped with the contract migration.
    org_role: Optional[OrgRoleOut] = None
    disciplines: list[UserDisciplineOut] = Field(default_factory=list)
    is_internal: Optional[bool] = None
    created_at: datetime
    updated_at: datetime

class ChangePasswordRequest(CamelModel):
    current_password: str
    new_password: str

class UserCreateByAdmin(CamelModel):
    """Create an account under one of the office's own configured roles.

    `org_role_id` is the field that matters. It names a row in `roles`, which
    the office administrator maintains, and it decides the account's
    permissions, whether the person is office staff, and — while `users.role`
    still exists — which legacy value that column is written with.

    `discipline_ids` are the specializations the person practises. They grant
    nothing; they narrow what their permissions apply to, and a person may hold
    several, which is how an office that combines Mechanical and Electrical is
    represented without a role called "MEP".

    The legacy `role` / `engineer_affiliation` / `engineer_profile` fields are
    still accepted so a client that has not been updated keeps working. They
    are ignored whenever `org_role_id` is supplied, and every validation below
    is skipped in that case — validating the retired vocabulary against a
    request that did not use it would reject perfectly good input.
    """

    email: EmailStr
    full_name: str
    password: str = Field(..., min_length=8, max_length=128)
    #: The office role. Optional only because the legacy path still exists;
    #: the administrator UI always sends it.
    org_role_id: Optional[UUID] = None
    discipline_ids: list[UUID] = Field(default_factory=list)
    role: Optional[UserRole] = None
    phone_number: Optional[str] = None
    organization: Optional[str] = None
    engineer_affiliation: Optional[str] = None
    engineer_profile: Optional[EngineerProfileCreate] = None

    @model_validator(mode='after')
    def validate_admin_create(self) -> 'UserCreateByAdmin':
        if self.org_role_id is not None:
            # The configured role answers everything below. What it may do is
            # checked against the database in the endpoint, not here.
            return self
        if self.role is None:
            raise ValueError("An office role is required to create an account")
        if self.role in {UserRole.ENGINEER, UserRole.CONSULTANT} and not self.engineer_profile:
            raise ValueError(f"{self.role.value} users require a specialization.")
        # Accept the legacy Consultant form value, but persist the unified
        # Engineer role with organization side = external_consultant.
        if self.role == UserRole.CONSULTANT:
            self.role = UserRole.ENGINEER
            self.engineer_affiliation = "external_consultant"
        if self.role == UserRole.ENGINEER:
            self.engineer_affiliation = self.engineer_affiliation or "internal_engineer"
            if self.engineer_affiliation not in {"internal_engineer", "main_contractor", "external_consultant"}:
                raise ValueError("Engineer type must be Internal Engineer, Main Contractor, or External Consultant")
            if self.engineer_affiliation == "external_consultant" and (not self.organization or not self.organization.strip()):
                raise ValueError("External consultant company/organization is required")
        else:
            self.engineer_affiliation = None
        if self.role != UserRole.ENGINEER:
            self.engineer_profile = None
        return self


# `EngineerCreateRequest` and `OwnerCreateRequest` stood here and are gone with
# the two endpoints that took them. Each described an account by one legacy
# identity; `UserCreateByAdmin` describes one by the office's own role and
# disciplines, which is the only shape that survives a configurable office.


class UserCreateResponse(UserOut):
    temporary_password: Optional[str] = None
