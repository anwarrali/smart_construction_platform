import uuid

from app.services.ai_insight_engine import _fingerprint, calculate_alignment


def test_alignment_score_is_weighted_and_explainable():
    result = calculate_alignment(
        {"ARCHITECTURAL": 80, "MECHANICAL": 20}, {"ARCHITECTURAL": 3},
        task_count=4, issue_count=2, linked_task_count=2, linked_issue_count=1,
        verified_evidence_count=4, linked_evidence_count=1,
    )
    assert result["components"] == {
        "taskScopeCoverage": 80.0,
        "disciplineCoverage": 50.0,
        "locationLinkedTasks": 50.0,
        "ifcLinkedIssues": 50.0,
        "verifiedEvidenceCoverage": 25.0,
    }
    assert result["overall"] == 59.5
    assert sum(result["weights"].values()) == 100


def test_alignment_caps_link_coverage_and_ignores_unclassified_elements():
    result = calculate_alignment(
        {"STRUCTURAL": 10, "UNCLASSIFIED": 1000}, {"STRUCTURAL": 1},
        task_count=1, issue_count=0, linked_task_count=5, linked_issue_count=0,
        verified_evidence_count=1, linked_evidence_count=3,
    )
    assert result["ifcDisciplines"] == {"STRUCTURAL": 10}
    assert result["components"]["locationLinkedTasks"] == 100.0
    assert result["components"]["verifiedEvidenceCoverage"] == 100.0


def test_insight_fingerprint_is_stable_but_context_sensitive():
    project_id = uuid.uuid4()
    version_id = uuid.uuid4()
    first = _fingerprint("RULE", project_id, version_id, {"storey": "L02", "count": 12})
    reordered = _fingerprint("RULE", project_id, version_id, {"count": 12, "storey": "L02"})
    changed = _fingerprint("RULE", project_id, version_id, {"count": 13, "storey": "L02"})
    assert first == reordered
    assert first != changed
