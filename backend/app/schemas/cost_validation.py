from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.enums import CostRiskLevel, CostValidationStatus
from app.schemas.user import CamelModel, UserOut

class CostValidationBase(CamelModel):
    material_name: str
    quantity: float
    unit: Optional[str] = None
    location: Optional[str] = None
    requested_cost: float
    certified_amount: Optional[float] = None
    planned_amount: Optional[float] = None
    previously_paid: float = 0
    cost_variance_percentage: Optional[float] = None
    status: CostValidationStatus = CostValidationStatus.PENDING
    market_price_min: Optional[float] = None
    market_price_max: Optional[float] = None
    risk_level: Optional[CostRiskLevel] = None
    ai_suggestion: Optional[str] = None
    review_notes: Optional[str] = None

class CostValidationCreate(CamelModel):
    project_id: UUID
    material_name: str
    quantity: float
    unit: Optional[str] = None
    location: Optional[str] = None
    requested_cost: float

class CostValidationReview(CamelModel):
    status: CostValidationStatus
    review_notes: Optional[str] = None
    certified_amount: Optional[float] = None

class CostValidationOut(CostValidationBase):
    id: UUID
    project_id: UUID
    requested_by_id: UUID
    reviewed_by_id: Optional[UUID] = None
    requested_by: Optional[UserOut] = None
    reviewed_by: Optional[UserOut] = None
    created_at: datetime
    updated_at: datetime
