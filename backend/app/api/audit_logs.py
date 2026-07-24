import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.deps import get_current_user, user_has_project_access
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])

@router.get("")
def list_audit_logs(project_id: uuid.UUID | None = None, limit: int = 100,
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.ADMIN:
        if not project_id or not user_has_project_access(db, current_user, project_id):
            raise HTTPException(status_code=403, detail="Project access is required")
    query = db.query(AuditLog)
    if project_id:
        query = query.filter(AuditLog.project_id == project_id)
    return query.order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500)).all()
