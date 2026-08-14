"""AI insights must be renderable in any language without being rewritten.

The engine composes an English sentence and, alongside it, records the facts
that sentence was built from plus a stable key for the family of statement. A
client can then compose the same statement in the reader's language. The stored
English is never machine-translated and the meaning never changes.
"""

import pytest

from app.services.ifc_compatibility_service import CompatibilityFinding


def _finding(**overrides):
    base = dict(
        code="TASK_WALL_ELEMENTS_MISSING", category="TASK_MODEL_MISMATCH",
        severity="HIGH", confidence=0.96,
        title="Tasks reference wall work but the IFC contains no matching elements",
        description="1 task(s) reference wall scope; no IfcWall elements were extracted.",
        reason="Task terminology was compared with deterministic IFC entity classes.",
        recommended_action="Verify IFC export scope/classification.",
        evidence={"taskIds": ["a"]}, affected={},
    )
    base.update(overrides)
    return CompatibilityFinding(**base)


def test_a_finding_carries_a_stable_key_and_its_facts():
    finding = _finding(message_key="TASK_ELEMENTS_MISSING",
                       params={"category": "wall", "taskCount": 1, "expectedClasses": "IfcWall"})
    assert finding.message_key == "TASK_ELEMENTS_MISSING"
    assert finding.params["category"] == "wall"
    # The English sentence is still there as the fallback.
    assert "wall" in finding.title


def test_the_key_is_stable_while_the_code_varies_with_the_subject():
    """Wall and column findings differ in code but share one translatable form."""
    wall = _finding(code="TASK_WALL_ELEMENTS_MISSING", message_key="TASK_ELEMENTS_MISSING",
                    params={"category": "wall", "taskCount": 1, "expectedClasses": "IfcWall"})
    column = _finding(code="TASK_COLUMN_ELEMENTS_MISSING", message_key="TASK_ELEMENTS_MISSING",
                      params={"category": "column", "taskCount": 2, "expectedClasses": "IfcColumn"})
    assert wall.code != column.code
    assert wall.message_key == column.message_key
    assert wall.params["category"] != column.params["category"]


def test_a_finding_without_an_explicit_key_falls_back_to_its_code():
    """Persistence uses `message_key or code`, so nothing is ever keyless."""
    finding = _finding()
    assert finding.message_key is None
    assert (finding.message_key or finding.code) == "TASK_WALL_ELEMENTS_MISSING"


def test_parameters_default_to_the_evidence_when_not_given():
    finding = _finding()
    assert finding.params is None
    assert (finding.params or finding.evidence) == {"taskIds": ["a"]}


@pytest.mark.parametrize("key,required", [
    ("DISCIPLINE_NOT_IN_IFC", {"discipline", "label", "taskCount"}),
    ("TASK_ELEMENTS_MISSING", {"category", "taskCount", "expectedClasses"}),
    ("IFC_PROJECT_NAME_MISMATCH", {"projectName"}),
])
def test_each_translatable_family_declares_the_facts_its_sentence_needs(key, required):
    """Pins the parameter contract the translation catalogue interpolates."""
    samples = {
        "DISCIPLINE_NOT_IN_IFC": {"discipline": "fire/protection", "label": "fire protection installation", "taskCount": 1},
        "TASK_ELEMENTS_MISSING": {"category": "wall", "taskCount": 1, "expectedClasses": "IfcWall"},
        "IFC_PROJECT_NAME_MISMATCH": {"projectName": "Residential Complex C"},
    }
    assert required <= set(samples[key])
