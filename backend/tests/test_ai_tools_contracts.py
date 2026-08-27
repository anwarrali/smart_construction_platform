"""The tool layer's structural promises, checked without a database.

These are the guarantees that must hold for *every* tool, including ones added
later. A test that only checked the tools written today would pass forever
while the next addition quietly broke the rule it was meant to protect.
"""

import pytest
from pydantic import ValidationError

from app.core.permission_catalogue import BY_CODE
from app.services.ai_tools import BY_NAME, TOOLS, ToolKind, tool_definitions
from app.services.ai_tools import arguments as args
from app.services.voice_capabilities import CAPABILITIES

#: Phase 5's list, as written in the roadmap. `get_issues` is the one addition:
#: `update_issue` is meaningless without a way to find an issue to update.
REQUIRED_TOOLS = {
    "get_project", "get_project_status", "get_tasks", "get_task", "update_task",
    "create_task", "create_issue", "update_issue", "get_site_reports",
    "search_documents", "get_document", "query_project_knowledge", "query_ifc",
    "analyze_ifc", "send_message", "get_project_users",
}

PERMISSION_CODES = set(BY_CODE)


def test_every_tool_the_roadmap_asked_for_exists():
    assert REQUIRED_TOOLS <= set(BY_NAME)


def test_tool_names_are_unique():
    assert len(BY_NAME) == len(TOOLS)


# --- Contracts --------------------------------------------------------------

@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.name)
def test_every_tool_has_a_usable_contract(tool):
    assert tool.description.strip(), f"{tool.name} has no description"
    assert tool.handler is not None, f"{tool.name} declares no handler"
    schema = tool.json_schema()
    assert schema["type"] == "object"
    # An agent framework reads this; a contract it cannot render is not a contract.
    assert "properties" in schema


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.name)
def test_a_tool_names_a_real_permission_or_explains_its_absence(tool):
    if tool.permission_code is None:
        assert tool.authorization_note.strip(), (
            f"{tool.name} declares no permission and gives no reason; "
            "an unexplained gap is how a bypass gets in"
        )
    else:
        assert tool.permission_code in PERMISSION_CODES, (
            f"{tool.name} names {tool.permission_code!r}, which is not in the catalogue"
        )


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.name)
def test_every_tool_explains_why_it_is_safe(tool):
    assert tool.authorization_note.strip(), f"{tool.name} has no authorization note"


def test_the_definitions_render_for_an_agent_framework():
    definitions = tool_definitions()
    assert len(definitions) == len(TOOLS)
    for definition in definitions:
        assert set(definition) >= {
            "name", "kind", "description", "parameters",
            "permission", "requiresConfirmation", "authorizationNote",
        }


# --- Reads never write, writes never execute --------------------------------

def test_only_read_tools_skip_confirmation():
    for tool in TOOLS:
        assert tool.requires_confirmation is (tool.kind is ToolKind.PROPOSE)


def test_every_write_tool_is_a_proposal():
    """The rule that keeps the tool layer from being a bypass."""
    for name in ("create_task", "update_task", "create_issue", "update_issue", "send_message"):
        assert BY_NAME[name].kind is ToolKind.PROPOSE
        assert BY_NAME[name].requires_confirmation


def test_no_tool_can_delete_anything():
    # Deletion is destructive and stays out of the tool layer entirely.
    assert not any("delete" in tool.name for tool in TOOLS)


def test_analyze_ifc_is_declared_read_only_despite_its_name():
    """It must not be a way for an agent to trigger a parse-and-tessellate run."""
    tool = BY_NAME["analyze_ifc"]
    assert tool.kind is ToolKind.READ
    assert "does not re-run" in tool.description.casefold() or "not re-run" in tool.description


# --- Shared definitions with voice ------------------------------------------

def test_write_tools_map_onto_capabilities_voice_already_declares():
    """Phase 5 asks Voice and Agents to share definitions. This is that sharing.

    Every proposal a tool can make is one the voice capability registry already
    describes, so there is one answer to "who may do this", not two.
    """
    from app.services.ai_tools import write_tools

    declared = {capability.action for capability in CAPABILITIES}
    from app.schemas.voice_analysis import SuggestedActionType

    used = {
        SuggestedActionType.CREATE_TASK, SuggestedActionType.UPDATE_TASK_PROGRESS,
        SuggestedActionType.ADD_TASK_NOTE, SuggestedActionType.UPDATE_TASK_DETAILS,
        SuggestedActionType.CREATE_ISSUE, SuggestedActionType.UPDATE_ISSUE_STATUS,
        SuggestedActionType.ASSIGN_ISSUE, SuggestedActionType.SEND_PROJECT_MESSAGE,
    }
    assert used <= declared
    assert write_tools.capability_for is not None


# --- Argument validation ----------------------------------------------------

def test_an_invented_argument_is_rejected_rather_than_ignored():
    """A model that invents `force=true` must fail loudly, not be humoured."""
    with pytest.raises(ValidationError):
        args.GetTasksArguments.model_validate({"limit": 10, "force": True})


def test_out_of_range_values_are_refused():
    with pytest.raises(ValidationError):
        args.GetTasksArguments.model_validate({"limit": 5000})
    with pytest.raises(ValidationError):
        args.UpdateTaskArguments.model_validate(
            {"taskId": "00000000-0000-0000-0000-000000000001", "progressPercentage": 150}
        )


def test_a_malformed_identifier_is_refused():
    with pytest.raises(ValidationError):
        args.TaskIdArgument.model_validate({"taskId": "not-a-uuid"})


def test_an_unbounded_string_is_refused():
    with pytest.raises(ValidationError):
        args.CreateIssueArguments.model_validate(
            {"title": "x" * 5000, "description": "y"}
        )


def test_a_status_outside_the_platforms_own_values_is_refused():
    with pytest.raises(ValidationError):
        args.GetTasksArguments.model_validate({"status": "almost_done"})


def test_required_arguments_cannot_be_omitted():
    with pytest.raises(ValidationError):
        args.CreateTaskArguments.model_validate({})


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.name)
def test_no_tool_accepts_unexpected_arguments(tool):
    """Uniform across the layer, so no single tool becomes the soft spot."""
    assert tool.arguments.model_config.get("extra") == "forbid"
