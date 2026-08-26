"""Build the small, project-isolated context supplied to voice analysis."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.milestone import Milestone
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.voice_analysis_authorization import authorized_voice_tasks
from app.services.voice_capabilities import available_capabilities, render_catalogue
from app.services.voice_entity_resolution import authorized_issues


class VoiceContextBuilder:
    def build(
        self, db: Session, *, user: User, project_id, task_id=None, pending=None,
        pending_open_question: bool = False,
    ) -> dict:
        """Assemble one analysis's context.

        `pending` is the engineer's own unfinished request, when they have one.
        It is included so the model can read a two-word utterance as the answer
        to the question just asked — without it, "المهمة السادسة" is a fragment
        that classifies as nothing. It carries only what was asked for and what
        was already understood; never another user's work, and never anything
        `authorized_voice_tasks` did not already allow.
        """
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
        # What this speaker may actually ask for, and the issues they might be
        # talking about. Both are read from the platform rather than assumed:
        # the capability list is permission-filtered, so the model is never
        # shown an operation this person could not perform, and the issue list
        # is what makes "المشكلة تبعت المواد" resolvable at all.
        capabilities = available_capabilities(db, user=user, project_id=project_id)
        issues = [
            {
                "id": str(issue.id),
                "title": issue.title,
                "status": str(getattr(issue.status, "value", issue.status)),
                "severity": str(getattr(issue.severity, "value", issue.severity)),
            }
            for issue in authorized_issues(db, project_id=project_id, limit=15)
        ]
        pending_context = {}
        if pending is not None:
            from app.services.voice_conversation_service import pending_summary

            pending_context = pending_summary(
                pending, include_open_question=pending_open_question,
            )
        return {
            **({"pendingRequest": pending_context} if pending_context else {}),
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
            # Permission-filtered, so proposing something outside it is the
            # model contradicting its own instructions rather than the backend
            # having to refuse an engineer who was never eligible.
            "allowedActionHandlers": [item.action.value for item in capabilities],
            "capabilityCatalogue": render_catalogue(capabilities),
            "issues": issues,
            #: Today, so relative dates in the *prompt* ("الأسبوع الجاي") are
            #: understood as relative to the right day. The arithmetic itself
            #: is still done by `app.services.voice_dates`, never by the model.
            "today": date.today().isoformat(),
            "tasks": task_context,
            "milestones": [{
                "id": str(item.id),
                "code": item.milestone_code,
                "name": item.name,
                "actualDate": item.actual_date.isoformat() if item.actual_date else None,
            } for item in milestones],
            "candidateRecipients": recipients,
        }
