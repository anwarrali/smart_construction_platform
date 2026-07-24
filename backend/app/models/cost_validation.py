"""
Cost Validation feature (Owner role): submit a material/cost request,
get a market price range + AI-suggested risk level back.
"""
import uuid

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CostRiskLevel, CostValidationStatus


class CostValidation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cost_validations"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Form inputs
    material_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)  # e.g. ton, m3, unit
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    certified_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    planned_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    previously_paid: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    cost_variance_percentage: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    # Result
    market_price_min: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    market_price_max: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    risk_level: Mapped[CostRiskLevel | None] = mapped_column(
        PG_ENUM(CostRiskLevel, name="cost_risk_level", create_type=True),
        nullable=True,
    )
    ai_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[CostValidationStatus] = mapped_column(
        PG_ENUM(CostValidationStatus, name="cost_validation_status", create_type=True),
        nullable=False,
        default=CostValidationStatus.PENDING,
        server_default=CostValidationStatus.PENDING.name,
        index=True,
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="cost_validations")
    requested_by: Mapped["User"] = relationship(foreign_keys=[requested_by_id])
    reviewed_by: Mapped["User"] = relationship(foreign_keys=[reviewed_by_id])

    def __repr__(self) -> str:
        return f"<CostValidation id={self.id} material={self.material_name} risk={self.risk_level}>"
