from typing import Callable
from uuid import UUID

from app.ai.action_schemas import ActionRuleResult, VoiceAction, VoiceActionType


#: The permission each action that changes project data needs. The proposal
#: is checked against it before the speaker is asked to confirm; execution
#: checks again. Was `role in {"engineer", "project_manager"}` on the retired
#: enum, which refused every role an office created.
ACTION_PERMISSIONS = {
    VoiceActionType.UPDATE_TASK_PROGRESS: "task.update_progress",
    VoiceActionType.UPDATE_TASK_STATUS: "task.update_progress",
    VoiceActionType.SUBMIT_TASK_FOR_REVIEW: "task.update_progress",
    VoiceActionType.ADD_TASK_COMMENT: "task.comment",
    VoiceActionType.CREATE_ISSUE: "issue.create",
    VoiceActionType.CREATE_SITE_REPORT: "site_report.submit",
}
MUTATING_ACTIONS = set(ACTION_PERMISSIONS)


def validate_proposed_action(
    action: VoiceAction,
    *,
    selected_project_id: UUID,
    may: Callable[[str], bool],
) -> tuple[VoiceAction, ActionRuleResult]:
    """Check a proposed action before the speaker confirms it.

    `may(code)` answers whether the speaker holds a permission code on the
    selected project — normally `has_permission(db, user, code, project_id)`.
    """
    errors: list[str] = []
    warnings: list[str] = []
    requires_clarification = action.requires_clarification

    if action.project_id and action.project_id != selected_project_id:
        errors.append("The proposed action targets a different project.")
    action = action.model_copy(update={"project_id": selected_project_id})

    if action.action_type == VoiceActionType.UNKNOWN:
        errors.append("No supported project action could be determined.")
    if action.confidence < 0.70:
        errors.append("AI confidence is below the execution threshold.")
    if action.action_type == VoiceActionType.UPDATE_TASK_PROGRESS:
        if action.progress_percentage is None:
            errors.append("A progress percentage is required.")
        if action.task_id is None:
            requires_clarification = True
            warnings.append("A task must be selected before this action can be confirmed.")
    if action.action_type in {
        VoiceActionType.UPDATE_TASK_STATUS,
        VoiceActionType.ADD_TASK_COMMENT,
        VoiceActionType.SUBMIT_TASK_FOR_REVIEW,
    } and action.task_id is None:
        requires_clarification = True
        warnings.append("A task must be selected before this action can be confirmed.")
    if action.action_type == VoiceActionType.CREATE_ISSUE and not action.description:
        errors.append("An issue description is required.")
    required = ACTION_PERMISSIONS.get(action.action_type)
    if required is not None and not may(required):
        errors.append("You do not have permission to perform the proposed action on this project.")

    warnings.append(
        "RBAC, dependency, review, and task rules will be checked again after confirmation."
    )
    action = action.model_copy(
        update={
            "requires_confirmation": action.action_type != VoiceActionType.UNKNOWN,
            "requires_clarification": requires_clarification,
        }
    )
    return action, ActionRuleResult(
        valid=not errors and not requires_clarification,
        errors=errors,
        warnings=warnings,
        requires_clarification=requires_clarification,
    )
