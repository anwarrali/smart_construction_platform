import json
from app.models.audit_log import AuditLog

def record_audit(db, *, actor_id, action: str, entity_type: str, entity_id=None, project_id=None, details=None):
    db.add(AuditLog(actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id,
                    project_id=project_id, details=json.dumps(details, default=str) if details else None))
