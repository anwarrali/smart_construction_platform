from pydantic import EmailStr
from typing import Optional
from uuid import UUID
from datetime import datetime

from app.schemas.user import CamelModel


class CompanyOut(CamelModel):
    id: UUID
    name: str
    description: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CompanyUpdate(CamelModel):
    name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
