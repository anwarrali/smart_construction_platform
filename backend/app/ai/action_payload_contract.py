"""The payload contract for voice-suggested actions — one definition.

This is the single source of truth for *which fields each action type may
carry*. Two consumers derive from it and neither may keep its own copy:

  1. `voice_rules_engine` validates a draft's payload against it before the
     action is allowed to execute.
  2. `construction_analysis_service` renders it into the system prompt, so the
     model is told the exact contract it will be judged against.

**Why this file exists.** The allowlist lived only in the rules engine, and
the prompt described action *types* while saying nothing about payload
*fields*. A real voice note ("the footings are poured, the cube tests still
need the consultant's review") produced a `SUBMIT_TASK_FOR_REVIEW` carrying
`subject`, `location`, `recipientRoles` and `sourceDiscipline` — all sensible
readings of what was said, all outside the allowlist — so the action was
rejected and the consultant was never contacted. The model was never told the
rule it broke. Two independently maintained definitions guaranteed that
would happen eventually; deriving both from this table means a new field is a
one-line change that updates the validator and the prompt together.

The allowlist is deliberately **not** relaxed into "silently drop unknown
fields". These actions perform real project operations, and a field the model
invented is evidence that it misunderstood the request — dropping it would
execute a half-understood instruction and hide the misunderstanding. The
action is refused, and the refusal now names both what was wrong and what was
allowed, so the user gets an explanation and the contract is self-teaching.
"""

from __future__ import annotations

from app.schemas.voice_analysis import SuggestedActionType


class ActionContract:
    """What one action type accepts."""

    __slots__ = ("purpose", "required", "optional")

    def __init__(
        self,
        purpose: str,
        *,
        required: tuple[str, ...] = (),
        optional: tuple[str, ...] = (),
    ) -> None:
        self.purpose = purpose
        self.required = required
        self.optional = optional

    @property
    def allowed(self) -> frozenset[str]:
        return frozenset(self.required) | frozenset(self.optional)


# Ordered so the rendered prompt is stable between runs; an unstable prompt
# would invalidate provider-side prompt caching for no reason.
ACTION_CONTRACTS: dict[SuggestedActionType, ActionContract] = {
    SuggestedActionType.CREATE_TASK: ActionContract(
        "Propose a new task.",
        required=("title",),
        optional=("description", "sourceDiscipline"),
    ),
    SuggestedActionType.START_TASK: ActionContract(
        "Move an existing To Do task into progress. Carries no payload.",
    ),
    SuggestedActionType.UPDATE_TASK_PROGRESS: ActionContract(
        "Set the completion percentage of an existing task.",
        required=("progressPercentage",),
        optional=("note", "correctionConfirmed"),
    ),
    SuggestedActionType.SUBMIT_TASK_FOR_REVIEW: ActionContract(
        "Hand a finished task to the reviewing consultant. Recipients are "
        "resolved by the backend from the project's reviewer assignment — "
        "never name them in the payload.",
        optional=("completionNote",),
    ),
    SuggestedActionType.CREATE_FIELD_SUBMISSION: ActionContract(
        "Record a worker's field evidence for later verification.",
        required=("description",),
    ),
    SuggestedActionType.CREATE_ISSUE: ActionContract(
        "Raise a site issue.",
        required=("title",),
        optional=(
            "description", "category", "severity", "affectsSchedule",
            "location", "recipientIds",
        ),
    ),
    SuggestedActionType.ADD_TASK_NOTE: ActionContract(
        "Append a note to a task's activity.",
        required=("content",),
    ),
    SuggestedActionType.CREATE_SITE_REPORT_DRAFT: ActionContract(
        "Draft a site report for the speaker to review.",
        required=("summaryText",),
        optional=("workCompleted", "delays", "issues", "notes"),
    ),
    SuggestedActionType.CREATE_TASK_MESSAGE: ActionContract(
        "Post a message into a task's discussion thread.",
        required=("content",),
    ),
    SuggestedActionType.PREPARE_CONSULTANT_REVIEW: ActionContract(
        "Record a consultant's spoken review decision.",
        required=("decision",),
        optional=("comments", "rejectionReason", "requiredCorrections"),
    ),
    SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT: ActionContract(
        "Propose a design change.",
        required=("title",),
        optional=(
            "description", "reason", "sourceDiscipline", "affectedDisciplines",
            "relatedDrawings", "location", "approved",
        ),
    ),
    SuggestedActionType.SEND_PROJECT_MESSAGE: ActionContract(
        "Send a message to named project members.",
        required=("content",),
        optional=("recipientIds", "recipientRoles", "subject"),
    ),
    SuggestedActionType.SEND_OWNER_UPDATE: ActionContract(
        "Send an update to the project owner.",
        required=("content",),
        optional=("recipientIds", "recipientRoles", "subject"),
    ),
}


def allowed_fields(action_type: SuggestedActionType) -> frozenset[str]:
    """Every field [action_type] may carry."""
    return ACTION_CONTRACTS[action_type].allowed


def rejection_detail(
    action_type: SuggestedActionType, unknown_keys: set[str]
) -> str:
    """The message shown when a payload carries fields outside the contract.

    It names the offending fields *and* the permitted ones. The previous
    wording listed only what was wrong, which told neither the user what to do
    nor a future maintainer what the action actually accepts.
    """
    allowed = sorted(allowed_fields(action_type))
    return (
        f"Unsupported fields for {action_type.value}: "
        f"{', '.join(sorted(unknown_keys))}. "
        f"Allowed fields: {', '.join(allowed) if allowed else 'none'}."
    )


def render_prompt_contract() -> str:
    """The contract as prompt text.

    Generated rather than written by hand so the model is always told exactly
    what the validator will enforce. Every action lists its allowed fields;
    the model is instructed to emit nothing else, which is the rule that was
    missing when this whole failure happened.
    """
    lines = [
        "ACTION PAYLOAD CONTRACT — emit payload keys from this table only.",
        "A payload key not listed for its action causes the action to be "
        "rejected and nothing is executed. Never move a field from one "
        "action onto another. Never invent recipient fields: the backend "
        "resolves recipients itself.",
    ]
    for action_type, contract in ACTION_CONTRACTS.items():
        required = ", ".join(contract.required) or "none"
        optional = ", ".join(contract.optional) or "none"
        lines.append(
            f"- {action_type.value}: {contract.purpose} "
            f"required=[{required}] optional=[{optional}]"
        )
    return "\n".join(lines)
