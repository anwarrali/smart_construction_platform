"""Build the small, project-isolated context supplied to voice analysis."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.milestone import Milestone
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.voice_analysis_authorization import authorized_voice_tasks
from app.services.voice_action_policy import RISK_BY_ACTION


class VoiceContextBuilder:
    def build(self, db: Session, *, user: User, project_id, task_id=None) -> dict:
        project = db.get(Project, project_id)
        tasks = authorized_voice_tasks(db, user, project_id)
        if task_id:
            tasks = [task for task in tasks if task.id == task_id]
        visible_ids = {task.id for task in tasks}
        task_context = []
        for task in tasks:
            task_context.append({
                "id": str(task.id),
                "taskCode": task.task_code,
                "title": task.name,
                "description": task.description,
                "discipline": task.discipline,
                "status": task.status.value,
                "progressPercentage": float(task.progress_percentage or 0),
                "reviewRequired": task.review_required,
                "milestoneId": str(task.milestone_id) if task.milestone_id else None,
                "dependencies": [
                    {
                        "taskId": str(edge.depends_on_task_id),
                        "taskCode": edge.depends_on_task.task_code,
                        "status": edge.depends_on_task.status.value,
                    }
                    for edge in task.dependencies
                    if edge.depends_on_task_id in visible_ids
                ],
            })
        members = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.is_active == True,
        ).all()
        recipients = [{
            "id": str(item.user_id),
            "name": item.user.full_name,
            "role": item.role_on_project.value,
            "discipline": item.project_discipline,
            "assignmentTitle": item.assignment_title,
        } for item in members if item.user_id != user.id]
        milestones = db.query(Milestone).filter(Milestone.project_id == project_id).all()
        return {
            "project": {
                "id": str(project.id),
                "name": project.name,
                "ownerId": str(project.owner_id) if project.owner_id else None,
                "consultantApprovalMode": project.consultant_approval_mode.value,
            },
            "actor": {
                "id": str(user.id),
                "role": user.role.value,
                "discipline": (
                    getattr(getattr(user, "engineer_profile", None), "discipline", None).value
                    if getattr(getattr(user, "engineer_profile", None), "discipline", None)
                    else None
                ),
            },
            "allowedActionHandlers": [item.value for item in RISK_BY_ACTION],
            "tasks": task_context,
            "milestones": [{
                "id": str(item.id),
                "code": item.milestone_code,
                "name": item.name,
                "actualDate": item.actual_date.isoformat() if item.actual_date else None,
            } for item in milestones],
            "candidateRecipients": recipients,
        }
