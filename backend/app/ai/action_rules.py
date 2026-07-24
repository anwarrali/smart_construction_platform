from uuid import UUID

from app.ai.action_schemas import ActionRuleResult, VoiceAction, VoiceActionType


MUTATING_ACTIONS = {
    VoiceActionType.UPDATE_TASK_PROGRESS,
    VoiceActionType.UPDATE_TASK_STATUS,
    VoiceActionType.CREATE_ISSUE,
    VoiceActionType.CREATE_SITE_REPORT,
    VoiceActionType.ADD_TASK_COMMENT,
    VoiceActionType.SUBMIT_TASK_FOR_REVIEW,
}


def validate_proposed_action(
    action: VoiceAction,
    *,
    selected_project_id: UUID,
    user_role: str,
) -> tuple[VoiceAction, ActionRuleResult]:
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
    if action.action_type in MUTATING_ACTIONS and user_role not in {
        "engineer",
        "project_manager",
    }:
        errors.append("This role cannot perform the proposed action.")

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
