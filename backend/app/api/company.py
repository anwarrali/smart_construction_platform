"""Company settings API for company administrators."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.database import get_db
from app.models.company import Company
from app.models.user import User
from app.schemas.company import CompanyOut, CompanyUpdate

router = APIRouter(prefix="/company", tags=["Company"])


@router.get("/settings", response_model=CompanyOut)
def get_company_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not current_user.company_id:
        raise HTTPException(status_code=404, detail="No company associated with this administrator")

    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.put("/settings", response_model=CompanyOut)
def update_company_settings(
    data: CompanyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not current_user.company_id:
        raise HTTPException(status_code=404, detail="No company associated with this administrator")

    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if data.name is not None:
        company.name = data.name
    if data.description is not None:
        company.description = data.description
    if data.address is not None:
        company.address = data.address
    if data.phone is not None:
        company.phone = data.phone
    if data.email is not None:
        company.email = data.email

    db.commit()
    db.refresh(company)
    return company
