from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: UUID
    role: str

class TokenData(BaseModel):
    user_id: Optional[UUID] = None
    email: Optional[str] = None
