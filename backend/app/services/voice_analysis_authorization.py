from sqlalchemy.orm import Session

from app.core.deps import user_has_project_access
from app.models.task import Task
from app.models.user import User
from app.services import rbac
from app.services.authorization import has_permission
from app.services.field_submission_authorization import can_review_field_submission


def can_create_voice_analysis(
    db: Session, user: User, project_id, task: Task | None
) -> bool:
    """Whether this person may start a spoken command on this project.

    Deliberately permissive, and the reason matters: speaking is not doing.
    Everything a voice analysis eventually proposes is re-checked by
    `VoiceRulesEngine` against the same permissions the web UI uses, so the
    only thing a narrow gate here would achieve is refusing to *listen* to
    somebody who is allowed to ask questions about their own project.

    So: project access, plus — when the sentence is about one task — the
    ability to see that task. Somebody with no permission to change anything
    can still dictate a question, which is the behaviour the assistant should
    have.
    """
    if not user_has_project_access(db, user, project_id):
        return False
    if task and task.project_id != project_id:
        return False
    if not has_permission(db, user, "task.view", project_id):
        return False
    if task is not None and not user.is_internal:
        # An external participant speaks about their own work only.
        return any(assignee.id == user.id for assignee in task.assignees)
    return True


def authorized_voice_tasks(db: Session, user: User, project_id) -> list[Task]:
    if not user_has_project_access(db, user, project_id):
        return []
    if not has_permission(db, user, "task.view", project_id):
        return []
    query = db.query(Task).filter(Task.project_id == project_id)
    if not has_permission(db, user, "task.review", project_id) and not has_permission(
        db, user, "task.edit", project_id
    ):
        # Somebody who neither reviews nor edits the project's work sees the
        # work they were given. This replaces "is a worker or a contractor
        # engineer" with the property that rule was reaching for.
        query = query.filter(Task.assignees.any(User.id == user.id))
    return query.order_by(Task.task_code).all()


def authorized_site_reports(db: Session, user: User, project_id, *, limit: int = 5):
    """Site reports this person may read, newest first.

    Mirrors `app.api.site_reports.list_site_reports` rather than inventing a
    second rule: an Owner sees only what has been submitted or approved, and a
    Consultant Engineer sees project-wide reports plus the ones filed against
    their own discipline's tasks. Voice must never widen what a screen shows.
    """
    from app.models.site_report import SiteReport

    if not user_has_project_access(db, user, project_id):
        return []
    query = db.query(SiteReport).filter(SiteReport.project_id == project_id)

    context = rbac.membership_context(db, user.id, project_id)
    if context.is_external or not user.is_internal:
        # Outside the office: filed and approved reports only, which is the
        # rule the client already had and the one that should govern a
        # contractor too.
        query = query.filter(SiteReport.review_status.in_(["submitted", "approved"]))

    if not has_permission(db, user, "project.view_all_disciplines", project_id):
        # Office staff who are narrowed by discipline are narrowed here too:
        # a report is about work, and the same specialization decides which
        # work they are looking at.
        codes = rbac.discipline_codes(
            rbac.disciplines_for_member(db, user.id, project_id)
        )
        if codes:
            discipline_task_ids = db.query(Task.id).filter(
                Task.project_id == project_id,
                Task.discipline.in_(codes),
            )
            query = query.filter(
                (SiteReport.task_id.is_(None))
                | SiteReport.task_id.in_(discipline_task_ids)
            )
    return query.order_by(
        SiteReport.report_date.desc(), SiteReport.created_at.desc()
    ).limit(max(1, limit)).all()


def can_view_voice_analysis(db: Session, user: User, analysis) -> bool:
    if analysis.user_id == user.id:
        return True
    if analysis.field_submission_id:
        from app.models.field_submission import FieldSubmission
        submission = db.get(FieldSubmission, analysis.field_submission_id)
        return bool(
            submission
            and can_review_field_submission(db, user, submission)
        )
    return False
