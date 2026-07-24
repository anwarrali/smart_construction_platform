from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from app.db.database import get_db
from app.models.user import User
from app.models.cost_validation import CostValidation
from app.models.project import Project
from app.schemas.cost_validation import CostValidationOut, CostValidationCreate, CostValidationReview
from app.core.deps import get_current_user, user_has_project_access, accessible_project_ids
from app.models.enums import CostValidationStatus, UserRole

router = APIRouter(prefix="/cost-validations", tags=["Cost Validations"])

@router.get("", response_model=List[CostValidationOut])
def list_cost_validations(
    project_id: Optional[uuid.UUID] = None,
    status: Optional[CostValidationStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CostValidation)
    if current_user.role != UserRole.ADMIN:
        accessible_ids = accessible_project_ids(db, current_user) or []
        query = query.filter(CostValidation.project_id.in_(accessible_ids))
    if project_id:
        query = query.filter(CostValidation.project_id == project_id)
    if status:
        query = query.filter(CostValidation.status == status)
    return query.all()

@router.get("/project/{project_id}", response_model=List[CostValidationOut])
def get_cost_validations_by_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    return db.query(CostValidation).filter(CostValidation.project_id == project_id).all()

@router.get("/{validation_id}", response_model=CostValidationOut)
def get_cost_validation_by_id(
    validation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    val = db.query(CostValidation).filter(CostValidation.id == validation_id).first()
    if not val:
        raise HTTPException(status_code=404, detail="Cost validation request not found")
    return val

@router.post("", response_model=CostValidationOut)
def create_cost_validation(
    val_data: CostValidationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.PROJECT_MANAGER:
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can submit payment claims")
    # Check if project exists
    project = db.query(Project).filter(Project.id == val_data.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if not user_has_project_access(db, current_user, val_data.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
        
    new_val = CostValidation(
        project_id=val_data.project_id,
        requested_by_id=current_user.id,
        material_name=val_data.material_name,
        quantity=val_data.quantity,
        unit=val_data.unit,
        location=val_data.location,
        requested_cost=val_data.requested_cost,
        market_price_min=None,
        market_price_max=None,
        risk_level=None,
        ai_suggestion=None,
        status=CostValidationStatus.PENDING
    )
    
    db.add(new_val)
    db.commit()
    db.refresh(new_val)
    return new_val

@router.post("/{validation_id}/review", response_model=CostValidationOut)
def review_cost_validation(
    validation_id: uuid.UUID,
    review_data: CostValidationReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    val = db.query(CostValidation).filter(CostValidation.id == validation_id).first()
    if not val:
        raise HTTPException(status_code=404, detail="Cost validation request not found")
        
    if current_user.role != UserRole.CONSULTANT or not user_has_project_access(db, current_user, val.project_id):
        raise HTTPException(status_code=403, detail="Only an assigned consultant can certify payment claims")
    if review_data.status == CostValidationStatus.APPROVED and review_data.certified_amount is None:
        raise HTTPException(status_code=400, detail="certifiedAmount is required when approving a claim")
    val.status = review_data.status
    val.review_notes = review_data.review_notes
    val.reviewed_by_id = current_user.id
    val.certified_amount = review_data.certified_amount
    if val.planned_amount:
        val.cost_variance_percentage = ((float(val.certified_amount or 0) - float(val.planned_amount)) / float(val.planned_amount)) * 100
    
    # If approved, add to project spent budget
    if review_data.status == CostValidationStatus.APPROVED:
        project = db.query(Project).filter(Project.id == val.project_id).first()
        if project:
            current_spent = float(project.budget_spent or 0)
            project.budget_spent = current_spent + float(val.certified_amount or 0)
            
    db.commit()
    db.refresh(val)
    return val

@router.delete("/{validation_id}")
def delete_cost_validation(validation_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    val = db.get(CostValidation, validation_id)
    if not val:
        raise HTTPException(status_code=404, detail="Cost validation request not found")
    if val.requested_by_id != current_user.id or val.status not in {CostValidationStatus.PENDING, CostValidationStatus.REJECTED}:
        raise HTTPException(status_code=403, detail="Only the requester can delete a pending or rejected claim")
    db.delete(val); db.commit()
    return {"message": "Cost claim deleted"}
