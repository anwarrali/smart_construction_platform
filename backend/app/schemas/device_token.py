"""Wire shapes for push device registration.

The registration token is accepted but never returned. It is a delivery
address, and echoing it back would put it in browser devtools, in logs and in
any client-side error report for no benefit — the client already has it.
`DeviceTokenOut` therefore describes the device, not how to reach it.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.models.enums import DevicePlatform
from app.schemas.user import CamelModel


class DeviceTokenRegister(CamelModel):
    #: The FCM registration token. Bounded so a malformed client cannot push
    #: an arbitrarily large string into the column.
    token: str = Field(min_length=10, max_length=512)
    platform: DevicePlatform
    #: Stable per-installation id. Supplying it lets the server retire this
    #: installation's previous token when FCM rotates it, instead of leaving a
    #: dead row behind on every refresh.
    device_id: Optional[str] = Field(default=None, max_length=200)
    device_name: Optional[str] = Field(default=None, max_length=200)
    app_version: Optional[str] = Field(default=None, max_length=50)


class DeviceTokenOut(CamelModel):
    id: UUID
    platform: DevicePlatform
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    app_version: Optional[str] = None
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DeviceTokenUnregister(CamelModel):
    """Sign-out. Either identifier works; the token is preferred.

    `device_id` is the fallback for the case where the client has already
    thrown its token away (Firebase deleteToken succeeded, the API call then
    failed and is being retried).
    """

    token: Optional[str] = Field(default=None, max_length=512)
    device_id: Optional[str] = Field(default=None, max_length=200)
