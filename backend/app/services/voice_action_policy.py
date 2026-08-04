"""Pure, deterministic policy metadata for construction voice actions."""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.voice_analysis import ActionRiskLevel, SuggestedActionType


RISK_BY_ACTION = {
    SuggestedActionType.CREATE_TASK: ActionRiskLevel.HIGH,
    SuggestedActionType.ADD_TASK_NOTE: ActionRiskLevel.LOW,
    SuggestedActionType.CREATE_FIELD_SUBMISSION: ActionRiskLevel.LOW,
    SuggestedActionType.CREATE_SITE_REPORT_DRAFT: ActionRiskLevel.LOW,
    SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT: ActionRiskLevel.MEDIUM,
    SuggestedActionType.CREATE_ISSUE: ActionRiskLevel.MEDIUM,
    SuggestedActionType.CREATE_TASK_MESSAGE: ActionRiskLevel.MEDIUM,
    SuggestedActionType.SEND_PROJECT_MESSAGE: ActionRiskLevel.MEDIUM,
    SuggestedActionType.SEND_OWNER_UPDATE: ActionRiskLevel.HIGH,
    SuggestedActionType.START_TASK: ActionRiskLevel.MEDIUM,
    SuggestedActionType.UPDATE_TASK_PROGRESS: ActionRiskLevel.MEDIUM,
    SuggestedActionType.SUBMIT_TASK_FOR_REVIEW: ActionRiskLevel.HIGH,
    SuggestedActionType.PREPARE_CONSULTANT_REVIEW: ActionRiskLevel.HIGH,
}


def action_risk(action_type: SuggestedActionType | str) -> ActionRiskLevel:
    return RISK_BY_ACTION[SuggestedActionType(action_type)]


def requires_detailed_confirmation(action_type: SuggestedActionType | str) -> bool:
    return action_risk(action_type) == ActionRiskLevel.HIGH


@dataclass(frozen=True)
class UserFacingVoiceError:
    code: str
    title: str
    description: str
    retryable: bool
    suggested_action: str


VOICE_ERRORS = {
    "VOICE_PROCESSING_FAILED": UserFacingVoiceError(
        "VOICE_PROCESSING_FAILED",
        "We could not process the recording",
        "Your recording was saved, so you can try the analysis again.",
        True,
        "Try again",
    ),
    "VOICE_TIMEOUT": UserFacingVoiceError(
        "VOICE_TIMEOUT",
        "Voice analysis is taking too long",
        "The analysis service is temporarily slow. Your recording is safe.",
        True,
        "Try again",
    ),
    "VOICE_PERMISSION_DENIED": UserFacingVoiceError(
        "VOICE_PERMISSION_DENIED",
        "This action is not available to you",
        "You can still submit a report to the responsible project engineer.",
        False,
        "Submit a field report",
    ),
    "VOICE_STALE_DATA": UserFacingVoiceError(
        "VOICE_STALE_DATA",
        "Project information changed",
        "Review the latest task information before confirming.",
        True,
        "Refresh the action",
    ),
    "VOICE_DEPENDENCY_BLOCKED": UserFacingVoiceError(
        "VOICE_DEPENDENCY_BLOCKED",
        "This task cannot start yet",
        "A required predecessor task is not complete.",
        False,
        "Review the blocking task",
    ),
    "VOICE_EVIDENCE_REQUIRED": UserFacingVoiceError(
        "VOICE_EVIDENCE_REQUIRED",
        "More evidence is required",
        "Upload the requested project evidence before submitting this action.",
        False,
        "Upload evidence",
    ),
}


def user_facing_error(code: str, *, detail: str | None = None) -> dict:
    item = VOICE_ERRORS.get(code, VOICE_ERRORS["VOICE_PROCESSING_FAILED"])
    return {
        "code": item.code,
        "title": item.title,
        "description": detail or item.description,
        "retryable": item.retryable,
        "suggestedAction": item.suggested_action,
    }
