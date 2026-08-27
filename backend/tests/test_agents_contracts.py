"""The agent layer's structural promises, checked without a database.

These hold for every agent, including any added later — which is the point.
A test naming only today's five would pass forever while a sixth quietly broke
the rule it was meant to protect.
"""

import pytest

from app.core.permission_catalogue import BY_CODE
from app.services.agents import AGENTS, BY_NAME, Certainty, agent_definitions
from app.services.agents.contracts import MAX_CONFIDENCE, AgentFinding, Evidence
from app.services.agents.runtime import AGENT_CATEGORY
from app.services.ai_tools import BY_NAME as TOOLS
from app.services.ai_tools.contracts import ToolKind
from app.services.domain_event_dispatcher import IMPORTANT_EVENTS

EXPECTED = {
    "site_report_agent", "document_consistency_agent", "revision_impact_agent",
    "rfi_agent", "schedule_risk_agent",
}


def test_exactly_the_five_specified_agents_exist():
    assert set(BY_NAME) == EXPECTED
    assert len(AGENTS) == 5


@pytest.mark.parametrize("agent", AGENTS, ids=lambda agent: agent.name)
def test_every_agent_is_describable(agent):
    assert agent.title.strip()
    assert agent.responsibility.strip()
    assert agent.analyzer is not None
    assert agent.source_engine.endswith("_V1")


def test_each_agent_has_a_distinct_source_engine():
    """So a stored finding says which agent produced it."""
    engines = [agent.source_engine for agent in AGENTS]
    assert len(set(engines)) == len(engines)


# --- Tools and permissions are explicit -------------------------------------

@pytest.mark.parametrize("agent", AGENTS, ids=lambda agent: agent.name)
def test_every_granted_tool_exists(agent):
    for tool in agent.allowed_tools:
        assert tool in TOOLS, f"{agent.name} grants {tool!r}, which is not a registered tool"


@pytest.mark.parametrize("agent", AGENTS, ids=lambda agent: agent.name)
def test_no_agent_is_granted_a_write_tool(agent):
    """Agents analyse. Proposing a change is a person's move, not an agent's."""
    for tool in agent.allowed_tools:
        assert TOOLS[tool].kind is ToolKind.READ, (
            f"{agent.name} holds {tool!r}, which is a {TOOLS[tool].kind.value} tool"
        )


@pytest.mark.parametrize("agent", AGENTS, ids=lambda agent: agent.name)
def test_every_agent_names_a_real_permission(agent):
    assert agent.permission_code in BY_CODE


@pytest.mark.parametrize("agent", AGENTS, ids=lambda agent: agent.name)
def test_tool_grants_are_narrow(agent):
    """No agent holds every tool; a grant is a decision, not a default."""
    assert set(agent.allowed_tools) < set(TOOLS)


def test_the_schedule_agent_cannot_reach_documents():
    """The containment that a prompt cannot talk its way around."""
    granted = set(BY_NAME["schedule_risk_agent"].allowed_tools)
    assert not granted & {"search_documents", "get_document", "query_project_knowledge"}


def test_the_document_agent_cannot_reach_the_model():
    granted = set(BY_NAME["document_consistency_agent"].allowed_tools)
    assert not granted & {"analyze_ifc", "query_ifc"}


# --- Proactive-compatible, not proactive ------------------------------------

@pytest.mark.parametrize("agent", AGENTS, ids=lambda agent: agent.name)
def test_subscribed_events_are_ones_the_platform_actually_emits(agent):
    """A subscription to an event that never fires would be dead wiring."""
    for event in agent.subscribes_to:
        assert event in IMPORTANT_EVENTS, f"{agent.name} subscribes to unknown event {event!r}"


def test_every_agent_declares_at_least_one_trigger():
    for agent in AGENTS:
        assert agent.subscribes_to, f"{agent.name} could never be woken by an event"


# --- Findings: the claim discipline -----------------------------------------

def _finding(**overrides):
    payload = dict(
        code="X", certainty=Certainty.DETECTED, severity="MEDIUM", confidence=0.8,
        title="t", description="d", reason="r", recommended_action="a",
        evidence=[Evidence("TASK", "1", "Task one")],
    )
    payload.update(overrides)
    return AgentFinding(**payload)


@pytest.mark.parametrize("certainty", list(Certainty))
def test_confidence_is_capped_by_the_kind_of_claim(certainty):
    ceiling = MAX_CONFIDENCE[certainty]
    with pytest.raises(ValueError, match="exceeds"):
        _finding(certainty=certainty, confidence=ceiling + 0.05)


def test_an_inference_can_never_be_as_confident_as_a_fact():
    assert MAX_CONFIDENCE[Certainty.INFERRED] < MAX_CONFIDENCE[Certainty.FACT]
    assert MAX_CONFIDENCE[Certainty.UNCERTAIN] < MAX_CONFIDENCE[Certainty.INFERRED]


def test_a_claim_without_evidence_is_refused():
    """The rule that stops an agent asserting what it cannot show."""
    with pytest.raises(ValueError, match="needs evidence"):
        _finding(evidence=[])


def test_an_uncertainty_finding_is_the_one_kind_allowed_without_evidence():
    finding = _finding(certainty=Certainty.UNCERTAIN, confidence=0.3, evidence=[])
    assert finding.certainty is Certainty.UNCERTAIN
    assert finding.evidence == []


def test_only_a_recommendation_requires_confirmation():
    assert _finding(certainty=Certainty.RECOMMENDATION, confidence=0.7).requires_confirmation
    assert not _finding(certainty=Certainty.FACT, confidence=1.0).requires_confirmation
    assert not _finding(certainty=Certainty.UNCERTAIN, confidence=0.3, evidence=[]).requires_confirmation


def test_a_finding_serialises_its_certainty_and_its_sources():
    payload = _finding().as_evidence_json()
    assert payload["certainty"] == "DETECTED"
    assert payload["claims"][0]["sourceType"] == "TASK"
    assert payload["requiresConfirmation"] is False


def test_agent_findings_are_categorised_apart_from_the_ifc_engines():
    assert AGENT_CATEGORY == "AGENT_FINDING"


def test_definitions_render_for_a_client():
    for definition in agent_definitions():
        assert set(definition) >= {
            "name", "title", "responsibility", "allowedTools",
            "permission", "sourceEngine", "subscribesTo",
        }
