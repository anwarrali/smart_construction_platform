from pydantic import BaseModel, EmailStr, Field, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.enums import UserStatus, EngineerDiscipline

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
    telegram_chat_id: Optional[str] = None
    notify_by_email: bool = True
    notify_by_telegram: bool = False
    must_change_password: bool = False
    invitation_accepted: bool = False
    organization: Optional[str] = None

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
    status: Optional[UserStatus] = None
    organization: Optional[str] = None
    engineer_profile: Optional[EngineerProfileCreate] = None

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
    #: The office role: the source of every permission this person holds.
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

    `org_role_id` names a row in `roles`, which the office administrator
    maintains, and it decides everything about the account's authority: its
    permissions and whether the person is office staff. There is no other way
    to say what somebody is.

    `discipline_ids` are the specializations the person practises. They grant
    nothing; they narrow what their permissions apply to, and a person may hold
    several. `engineer_profile` records an engineering specialist's profile
    (discipline, licence, employee id) when there is one to record.
    """

    email: EmailStr
    full_name: str
    password: str = Field(..., min_length=8, max_length=128)
    org_role_id: UUID
    discipline_ids: list[UUID] = Field(default_factory=list)
    phone_number: Optional[str] = None
    organization: Optional[str] = None
    engineer_profile: Optional[EngineerProfileCreate] = None


# `EngineerCreateRequest` and `OwnerCreateRequest` stood here and are gone with
# the two endpoints that took them. Each described an account by one legacy
# identity; `UserCreateByAdmin` describes one by the office's own role and
# disciplines, which is the only shape that survives a configurable office.


class UserCreateResponse(UserOut):
    temporary_password: Optional[str] = None
