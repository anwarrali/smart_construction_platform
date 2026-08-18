from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.step_up import router as step_up_router
from app.api.users import router as users_router
from app.api.projects import router as projects_router
from app.api.tasks import router as tasks_router
from app.api.documents import router as documents_router
from app.api.design_changes import router as design_changes_router
from app.api.site_reports import router as site_reports_router
from app.api.issues import router as issues_router
from app.api.notifications import router as notifications_router
from app.api.dashboard import router as dashboard_router
from app.api.company import router as company_router
from app.api.scheduling import router as scheduling_router
from app.api.audit_logs import router as audit_logs_router
from app.api.attachments import router as attachments_router
from app.api.field_assistant import router as field_assistant_router
from app.api.milestones import router as milestones_router
from app.api.messages import router as messages_router
from app.api.consultant_reviews import router as consultant_reviews_router
from app.api.ai import router as ai_router
from app.api.field_submissions import router as field_submissions_router
from app.api.photo_archive import router as photo_archive_router
from app.api.voice import router as voice_router
from app.api.ifc import router as ifc_router
from app.api.ai_intelligence import router as ai_intelligence_router
from app.api.ai_actions import router as ai_actions_router
from app.api.collaboration import router as collaboration_router
from app.api.permissions import router as permissions_router
from app.api.cost_validations import router as cost_validations_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(step_up_router)
api_router.include_router(permissions_router)
api_router.include_router(users_router)
api_router.include_router(projects_router)
api_router.include_router(tasks_router)
api_router.include_router(documents_router)
api_router.include_router(design_changes_router)
api_router.include_router(site_reports_router)
api_router.include_router(issues_router)
api_router.include_router(notifications_router)
api_router.include_router(dashboard_router)
api_router.include_router(company_router)
api_router.include_router(scheduling_router, prefix="/scheduling")
api_router.include_router(audit_logs_router)
api_router.include_router(attachments_router)
api_router.include_router(field_assistant_router)
api_router.include_router(milestones_router)
api_router.include_router(messages_router)
api_router.include_router(consultant_reviews_router)
api_router.include_router(ai_router)
api_router.include_router(field_submissions_router)
api_router.include_router(photo_archive_router)
api_router.include_router(voice_router)
api_router.include_router(ifc_router)
api_router.include_router(ai_intelligence_router)
api_router.include_router(ai_actions_router)
api_router.include_router(collaboration_router)
# Fully implemented (list/create/review, project-scoped access checks) but
# never wired in — the frontend's `submit_cost_validation` /
# `review_cost_validation` permission actions (utils/permissions.ts) have had
# no reachable endpoint behind them. Every route in this module 404'd
# regardless of role, including Admin.
api_router.include_router(cost_validations_router)
