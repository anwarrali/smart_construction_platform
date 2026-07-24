from datetime import datetime
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

class RevokedToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "revoked_tokens"
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
