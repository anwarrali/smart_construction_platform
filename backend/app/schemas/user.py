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
            UserRole.WORKER,
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
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
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

class UserOut(UserBase):
    id: UUID
    status: UserStatus
    is_email_verified: bool
    is_superuser: bool
    last_login_at: Optional[str] = None
    engineer_profile: Optional[EngineerProfileOut] = None
    created_at: datetime
    updated_at: datetime

class ChangePasswordRequest(CamelModel):
    current_password: str
    new_password: str

class UserCreateByAdmin(CamelModel):
    email: EmailStr
    full_name: str
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole
    phone_number: Optional[str] = None
    organization: Optional[str] = None
    engineer_affiliation: Optional[str] = None
    engineer_profile: Optional[EngineerProfileCreate] = None

    @model_validator(mode='after')
    def validate_admin_create(self) -> 'UserCreateByAdmin':
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


class EngineerCreateRequest(CamelModel):
    full_name: str
    email: EmailStr
    phone_number: str
    discipline: EngineerDiscipline = EngineerDiscipline.CIVIL
    employee_id: Optional[str] = None


class OwnerCreateRequest(CamelModel):
    full_name: str
    email: EmailStr
    phone_number: str
    organization: Optional[str] = None


class UserCreateResponse(UserOut):
    temporary_password: Optional[str] = None
