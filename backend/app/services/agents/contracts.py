"""What an agent is, and what it is allowed to claim.

Five agents, fixed. Each one is a bounded analyst over data the platform
already holds: it reads through the Phase 5 tool layer, reasons
deterministically, and produces findings. None of them writes project data,
and none of them decides an authorization question — the tool runtime does
that, before an agent's code is reached.

The distinction this module exists to enforce is `Certainty`. An agent that
reports "the slab is late" and "the slab may be late because two reports
mention rain" in the same voice is worse than one that reports neither: a
reader cannot tell which one to act on. So every finding states what kind of
claim it is, and the type is carried through to the stored insight rather than
being flattened into prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class Certainty(str, Enum):
    """What kind of claim a finding is making.

    Ordered from strongest to weakest, and never mixed inside one finding.
    """

    #: Read directly from a record. "This report says three days of delay."
    FACT = "FACT"
    #: A rule fired on real data. "Four reports in a row mention the same delay."
    DETECTED = "DETECTED"
    #: A conclusion drawn from facts, which could be wrong. "This suggests the
    #: crane is the constraint."
    INFERRED = "INFERRED"
    #: A suggested next step. Never performed by the agent.
    RECOMMENDATION = "RECOMMENDATION"
    #: The agent looked and could not tell. Reported explicitly, because
    #: "nothing found" and "could not look" are different answers.
    UNCERTAIN = "UNCERTAIN"


#: Confidence ceilings by claim type. An inference drawn from project data is
#: never as certain as a value read out of a row, and the numbers say so —
#: Phase 8 keys notification policy off them and must not be handed false
#: certainty.
MAX_CONFIDENCE = {
    Certainty.FACT: 1.0,
    Certainty.DETECTED: 0.9,
    Certainty.INFERRED: 0.7,
    Certainty.RECOMMENDATION: 0.7,
    Certainty.UNCERTAIN: 0.3,
}


def json_safe(value):
    """Coerce a value into something JSONB accepts.

    The tool layer already emits clean values; this is the second line, because
    evidence detail is assembled by analyzers and a single stray `Decimal` or
    `date` would lose the whole finding at insert time.
    """
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


@dataclass(frozen=True)
class Evidence:
    """One record a finding rests on, in a form a citation can be built from."""

    source_type: str
    source_id: str
    label: str
    #: The specific values that mattered, so the claim can be re-checked
    #: without reopening the source.
    detail: dict = field(default_factory=dict)

    def as_json(self) -> dict:
        return {
            "sourceType": self.source_type, "sourceId": self.source_id,
            "label": self.label, "detail": json_safe(self.detail),
        }


@dataclass(frozen=True)
class AgentFinding:
    """One thing an agent concluded, and everything needed to judge it."""

    code: str
    certainty: Certainty
    severity: str
    confidence: float
    title: str
    description: str
    #: Why the agent concluded this — the reasoning, not a restatement.
    reason: str
    recommended_action: str
    evidence: list[Evidence] = field(default_factory=list)
    #: Project entities this is about, by type.
    affected: dict = field(default_factory=dict)
    related_task_ids: list[str] = field(default_factory=list)
    related_issue_ids: list[str] = field(default_factory=list)
    potential_impact: str | None = None

    def __post_init__(self):
        ceiling = MAX_CONFIDENCE[self.certainty]
        if self.confidence > ceiling:
            raise ValueError(
                f"{self.code}: confidence {self.confidence} exceeds the {ceiling} "
                f"ceiling for a {self.certainty.value} claim"
            )
        if self.certainty is not Certainty.UNCERTAIN and not self.evidence:
            # The rule that stops an agent asserting something it cannot show.
            raise ValueError(f"{self.code}: a {self.certainty.value} claim needs evidence")

    @property
    def requires_confirmation(self) -> bool:
        """True when acting on this would change project data.

        Informational findings do not need a decision; a recommendation does,
        and it is a person who makes it.
        """
        return self.certainty is Certainty.RECOMMENDATION

    def as_evidence_json(self) -> dict:
        return {
            "certainty": self.certainty.value,
            "claims": [item.as_json() for item in self.evidence],
            "requiresConfirmation": self.requires_confirmation,
        }


@dataclass(frozen=True)
class AgentSpec:
    """One agent, declared.

    Everything an agent may do is on this record: which tools it can call,
    which permission a caller needs, and which domain events would make it
    worth running. Nothing is discovered at runtime, so an agent cannot grow a
    capability without the change being visible here.
    """

    name: str
    title: str
    #: What it is responsible for, in one sentence.
    responsibility: str
    #: The only tools this agent may call. The runtime refuses anything else,
    #: so a handler cannot reach data the agent was not granted.
    allowed_tools: tuple[str, ...]
    #: Catalogue permission the *caller* must hold to run this agent, on top of
    #: the per-tool permissions the tool runtime already enforces.
    permission_code: str
    #: `AIInsight.source_engine` for findings this agent stores.
    source_engine: str
    #: Domain events that should eventually trigger this agent. Declared in
    #: Phase 6, wired in Phase 8 — the dispatcher is untouched here.
    subscribes_to: tuple[str, ...] = ()
    #: The analyzer. Signature: (context) -> list[AgentFinding].
    analyzer: object = field(repr=False, default=None)

    def as_definition(self) -> dict:
        return {
            "name": self.name, "title": self.title,
            "responsibility": self.responsibility,
            "allowedTools": list(self.allowed_tools),
            "permission": self.permission_code,
            "sourceEngine": self.source_engine,
            "subscribesTo": list(self.subscribes_to),
        }


class AgentError(Exception):
    """An agent run that could not proceed, with a reason worth showing."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
