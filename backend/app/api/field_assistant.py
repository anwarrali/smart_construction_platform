import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import accessible_project_ids, get_current_user, user_has_project_access
from app.services import work_scope
from app.services.authorization import require
from app.db.database import get_db
from app.models.enums import UserRole
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.field_assistant import ActionProposal, ActionProposalValidationOut

router = APIRouter(prefix="/field", tags=["Field & Future AI Foundation"])


@router.get("/context")
def get_mobile_field_context(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project_ids = accessible_project_ids(db, current_user) or []
    projects = db.query(Project).filter(Project.id.in_(project_ids)).all()
    assignments = db.query(ProjectMember).filter(ProjectMember.user_id == current_user.id,
        ProjectMember.project_id.in_(project_ids), ProjectMember.is_active == True).all()
    by_project = {item.project_id: item for item in assignments}
    return {"userId": current_user.id, "role": current_user.role.value,
            "discipline": current_user.engineer_profile.discipline.value if current_user.engineer_profile else None,
            "projects": [{"id": project.id, "name": project.name,
                "assignmentTitle": by_project.get(project.id).assignment_title if by_project.get(project.id) else None,
                "isSiteEngineer": by_project.get(project.id).is_site_engineer if by_project.get(project.id) else False}
                for project in projects]}


def _validate_proposal(db: Session, user: User, proposal: ActionProposal) -> str | None:
    if not user_has_project_access(db, user, proposal.project_id):
        raise HTTPException(status_code=403, detail="The authenticated user is not assigned to this project")
    # Nobody acts outside the disciplines they were assigned. Somebody who is
    # not narrowed (an administrator, a project manager, an office engineer with
    # `project.view_all_disciplines`) is unaffected.
    if proposal.discipline:
        scoped = work_scope.scoped_discipline_codes(db, user, proposal.project_id)
        if scoped is not None and proposal.discipline not in scoped:
            raise HTTPException(
                status_code=403, detail="You cannot act outside your assigned disciplines",
            )
    # Each proposal routes to the endpoint that will execute it, so the
    # capability asked for here is the one that endpoint checks. Was three
    # role-name comparisons, which meant an office that granted `issue.create`
    # to a role it created still had the assistant refuse.
    if proposal.action_type == "ISSUE":
        require(db, user, "issue.create", proposal.project_id)
        return "/api/v1/issues"
    if proposal.action_type == "DESIGN_CHANGE":
        require(db, user, "design_change.propose", proposal.project_id)
        return "/api/v1/design-changes"
    if proposal.action_type == "SITE_REPORT":
        require(db, user, "site_report.submit", proposal.project_id)
        # And the same site-responsibility narrowing the endpoint applies, so
        # the assistant cannot route somebody past it.
        if not work_scope.sees_all_tasks(db, user, proposal.project_id) and not work_scope.is_site_engineer(
            db, user, proposal.project_id
        ):
            raise HTTPException(
                status_code=403,
                detail="Site responsibility on this project is required to file a report",
            )
        return "/api/v1/site-reports/submit"
    if proposal.action_type == "PROJECT_STATUS_QUESTION":
        return None
    return None


@router.post("/action-proposals/validate", response_model=ActionProposalValidationOut)
def validate_action_proposal(proposal: ActionProposal, db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    endpoint = _validate_proposal(db, current_user, proposal)
    return ActionProposalValidationOut(proposal_id=uuid.uuid4(), status="needs_confirmation",
        proposal=proposal, allowed_submission_endpoint=endpoint,
        warnings=["Review and confirm the structured fields before submitting to the domain endpoint."])


@router.post("/action-proposals/confirm", response_model=ActionProposalValidationOut)
def confirm_action_proposal(proposal: ActionProposal, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    endpoint = _validate_proposal(db, current_user, proposal)
    return ActionProposalValidationOut(proposal_id=uuid.uuid4(), status="ready_for_submission",
        proposal=proposal, allowed_submission_endpoint=endpoint)
