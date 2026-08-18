import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import accessible_project_ids, get_current_user, is_consultant_engineer, user_has_project_access
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
    # `user.role` is never literally CONSULTANT (a Consultant Engineer is
    # persisted as ENGINEER with `engineer_affiliation="external_consultant"`,
    # see app.schemas.user.UserCreateByAdmin), hence `is_consultant_engineer`.
    if proposal.discipline and is_consultant_engineer(user) and user.engineer_profile:
        if proposal.discipline != user.engineer_profile.discipline.value:
            raise HTTPException(status_code=403, detail="Consultants cannot act outside their assigned discipline")
    if proposal.action_type == "ISSUE":
        if user.role not in {UserRole.ENGINEER, UserRole.PROJECT_MANAGER}:
            raise HTTPException(status_code=403, detail="Your role cannot create Issues")
        return "/api/v1/issues"
    if proposal.action_type == "DESIGN_CHANGE":
        if user.role not in {UserRole.ENGINEER, UserRole.PROJECT_MANAGER}:
            raise HTTPException(status_code=403, detail="Your role cannot propose Design Changes")
        return "/api/v1/design-changes"
    if proposal.action_type == "SITE_REPORT":
        if user.role == UserRole.ENGINEER:
            assignment = db.query(ProjectMember).filter(ProjectMember.project_id == proposal.project_id,
                ProjectMember.user_id == user.id, ProjectMember.is_active == True,
                ProjectMember.is_site_engineer == True).first()
            if not assignment:
                raise HTTPException(status_code=403, detail="A project-specific Site Engineer assignment is required")
        elif user.role != UserRole.PROJECT_MANAGER:
            raise HTTPException(status_code=403, detail="Your role cannot submit Site Reports")
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
