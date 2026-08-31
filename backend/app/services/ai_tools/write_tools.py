"""Write handlers. None of them writes.

Every one builds a proposal and returns it for a human to confirm. That is not
timidity, it is the architecture the platform already has: a voice instruction
becomes a draft, the draft is confirmed by the person who gave it, and only
then does `VoiceRulesEngine` re-check everything and execute through the same
service the web UI calls. An agent tool that wrote directly would have skipped
the confirmation *and* the re-check, which is precisely the bypass Phase 5
forbids.

So these tools reuse the registry that already decides who may do what
(`voice_capabilities.CAPABILITIES`) and refuse early, in words, when the caller
could not perform the operation anyway. A proposal that reaches a human is one
the backend has already agreed it would accept — and the backend will still
check again at execution, because that check is the one that counts.
"""

from __future__ import annotations

from app.models.issue import Issue
from app.models.task import Task
from app.models.user import User
from app.schemas.voice_analysis import SuggestedActionType
from app.services.ai_tools.contracts import ToolError
from app.services.voice_analysis_authorization import authorized_voice_tasks
from app.services.voice_capabilities import capability_for, is_available


def _capability_or_refuse(db, actor: User, project_id, action: SuggestedActionType):
    """The same gate the voice path applies, applied before proposing.

    Refusing here is a courtesy, not the security boundary: it lets an agent be
    told "you cannot do this" instead of building a proposal a person would
    confirm only to have execution reject it. The boundary is still the rules
    engine at execution time.
    """
    capability = capability_for(action)
    if capability is None:
        raise ToolError("UNSUPPORTED", f"No capability is registered for {action.value}", status=400)
    if not is_available(db, user=actor, project_id=project_id, capability=capability):
        raise ToolError(
            "FORBIDDEN",
            f"You do not have permission to {capability.purpose} on this project.",
            status=403,
        )
    return capability


def _proposal(capability, action: SuggestedActionType, payload: dict, summary: str) -> dict:
    return {
        "actionType": action.value,
        "payload": payload,
        "summary": summary,
        "riskLevel": capability.risk.value if capability.risk else None,
        "isDestructive": capability.is_destructive,
        "requiredFields": list(capability.required_fields),
        "confirmation": (
            "This is a proposal. It has not been performed. A person must confirm it, "
            "after which the backend re-checks permission and executes it."
        ),
    }


def _own_task(db, actor: User, project_id, task_id) -> Task:
    task = next(
        (item for item in authorized_voice_tasks(db, actor, project_id) if item.id == task_id),
        None,
    )
    if not task:
        raise ToolError("NOT_FOUND", "No such task in this project for this user", status=404)
    return task


def create_task(db, actor: User, project_id, args) -> dict:
    capability = _capability_or_refuse(db, actor, project_id, SuggestedActionType.CREATE_TASK)
    payload = {
        "name": args.name, "description": args.description,
        "assigneeId": str(args.assignee_id) if args.assignee_id else None,
        "priority": args.priority, "dueDate": args.due_date,
    }
    return _proposal(capability, SuggestedActionType.CREATE_TASK, payload,
                     f"Create task {args.name!r}")


def update_task(db, actor: User, project_id, args) -> dict:
    """Mapped to the specific operation, not a general "update".

    The platform has no single update-a-task permission: changing progress,
    schedule and details are separate capabilities with separate rules. The
    tool takes the general shape an agent expects and resolves it to the
    capability that actually governs what is being changed.
    """
    if args.progress_percentage is None and args.status is None and args.note is None:
        raise ToolError("INVALID_ARGUMENTS", "Nothing to update was supplied", status=400)
    action = (
        SuggestedActionType.UPDATE_TASK_PROGRESS
        if args.progress_percentage is not None
        else SuggestedActionType.ADD_TASK_NOTE
        if args.note is not None and args.status is None
        else SuggestedActionType.UPDATE_TASK_DETAILS
    )
    capability = _capability_or_refuse(db, actor, project_id, action)
    task = _own_task(db, actor, project_id, args.task_id)
    payload = {
        "taskId": str(task.id), "taskName": task.name,
        "progressPercentage": args.progress_percentage,
        "status": args.status, "note": args.note,
    }
    return _proposal(capability, action, payload, f"Update task {task.name!r}")


def create_issue(db, actor: User, project_id, args) -> dict:
    capability = _capability_or_refuse(db, actor, project_id, SuggestedActionType.CREATE_ISSUE)
    if args.task_id:
        _own_task(db, actor, project_id, args.task_id)
    payload = {
        "title": args.title, "description": args.description,
        "severity": args.severity, "taskId": str(args.task_id) if args.task_id else None,
    }
    return _proposal(capability, SuggestedActionType.CREATE_ISSUE, payload,
                     f"Raise issue {args.title!r}")


def update_issue(db, actor: User, project_id, args) -> dict:
    action = (
        SuggestedActionType.ASSIGN_ISSUE if args.assignee_id
        else SuggestedActionType.UPDATE_ISSUE_STATUS
    )
    capability = _capability_or_refuse(db, actor, project_id, action)
    issue = db.query(Issue).filter(
        Issue.id == args.issue_id, Issue.project_id == project_id
    ).first()
    if not issue:
        raise ToolError("NOT_FOUND", "No such issue in this project", status=404)
    payload = {
        "issueId": str(issue.id), "title": issue.title,
        "status": args.status, "assigneeId": str(args.assignee_id) if args.assignee_id else None,
    }
    return _proposal(capability, action, payload, f"Update issue {issue.title!r}")


def send_message(db, actor: User, project_id, args) -> dict:
    """Proposed, never sent.

    Messaging has no catalogue permission because the messaging service decides
    per recipient — so this cannot pre-check who may be written to, and does not
    pretend otherwise. The recipient check happens where it belongs, when a
    confirmed message is actually sent.
    """
    capability = _capability_or_refuse(db, actor, project_id, SuggestedActionType.SEND_PROJECT_MESSAGE)
    payload = {
        "recipientId": str(args.recipient_id), "body": args.body,
        "taskId": str(args.task_id) if args.task_id else None,
    }
    return _proposal(capability, SuggestedActionType.SEND_PROJECT_MESSAGE, payload,
                     "Send a project message")
