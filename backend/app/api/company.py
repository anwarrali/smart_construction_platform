"""Company settings API.

Both endpoints were gated by `require_admin`, which asked
`can_manage_all_users(user.role)` — a decision made from the retired `UserRole`
enum. They now require `org.manage_settings`, which is the catalogue code the
permission table already describes as covering exactly this surface ("Change
office details, branding and report templates"), and which an office can
actually administer.

The swap was measured, not assumed: across every account in the database the
two answers are identical, so no one gains or loses access here.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.services.authorization import require_permission
from app.db.database import get_db
from app.models.company import Company
from app.models.user import User
from app.schemas.company import CompanyOut, CompanyUpdate

router = APIRouter(prefix="/company", tags=["Company"])


@router.get("/settings", response_model=CompanyOut)
def get_company_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.manage_settings")),
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
    current_user: User = Depends(require_permission("org.manage_settings")),
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
