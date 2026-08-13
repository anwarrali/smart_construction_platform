"""IFC ↔ project mismatch detection.

The acceptance case is an IFC sample that has nothing to do with the project's
actual work: the platform must say *what* does not line up and *why*, not print
a tidy element count.
"""

from uuid import uuid4

from app.services.ifc_compatibility_service import (
    DISCIPLINE_TERMS,
    evaluate_ifc_compatibility,
)


ARCHITECTURAL_ONLY = {"IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcDoor", "IfcWindow", "IfcSpace"}


def _evaluate(**overrides):
    payload = dict(
        project_name="Al Quds Residential Villa",
        project_type="residential villa",
        summary={"projectOverview": {"projectName": "Al Quds Residential Villa"}, "elements": 120},
        storey_names=["Ground Floor", "Floor 1"],
        space_names=["Room 101"],
        element_types=set(ARCHITECTURAL_ONLY),
        task_texts=[],
        scheduled_tasks=[],
    )
    payload.update(overrides)
    return evaluate_ifc_compatibility(**payload)


def _by_code(findings):
    return {item.code: item for item in findings}


def test_electrical_tasks_without_electrical_model_elements_are_flagged():
    task_ids = [str(uuid4()) for _ in range(3)]
    findings = _evaluate(task_texts=[
        (task_ids[0], "Install electrical conduit in the ground floor"),
        (task_ids[1], "Pull cable to the distribution board"),
        (task_ids[2], "Fix lighting fixtures in the corridor"),
    ])
    finding = _by_code(findings)["DISCIPLINE_ELECTRICAL_NOT_IN_IFC"]
    assert finding.category == "DISCIPLINE_MISMATCH"
    assert finding.severity == "CRITICAL"  # three or more matched tasks
    assert finding.evidence["matchedTaskCount"] == 3
    assert set(finding.affected["tasks"]) == set(task_ids)
    assert "IfcLightFixture" in finding.evidence["expectedIfcClasses"]
    assert finding.reason and finding.recommended_action


def test_a_single_discipline_task_is_high_rather_than_critical():
    findings = _evaluate(task_texts=[(str(uuid4()), "Install sprinkler heads above the lobby")])
    assert _by_code(findings)["DISCIPLINE_FIRE_PROTECTION_NOT_IN_IFC"].severity == "HIGH"


def test_declared_task_discipline_is_used_even_without_matching_wording():
    task_id = str(uuid4())
    findings = _evaluate(
        task_texts=[(task_id, "Second fix works in unit 4")],
        scheduled_tasks=[{"taskId": task_id, "discipline": "electrical", "text": "Second fix works in unit 4",
                          "plannedStart": None, "name": "Second fix", "taskCode": "T-1"}],
    )
    finding = _by_code(findings)["DISCIPLINE_ELECTRICAL_NOT_IN_IFC"]
    assert finding.evidence["matchedTasks"][0]["matchedTerm"] == "task.discipline field"


def test_discipline_present_in_the_model_is_not_flagged():
    findings = _evaluate(
        task_texts=[(str(uuid4()), "Install electrical conduit on floor 1")],
        element_types=ARCHITECTURAL_ONLY | {"IfcCableCarrierSegment"},
    )
    assert "DISCIPLINE_ELECTRICAL_NOT_IN_IFC" not in _by_code(findings)


def test_structural_vocabulary_does_not_fire_on_a_structural_model():
    findings = _evaluate(
        task_texts=[(str(uuid4()), "Foundation reinforcement and concrete pour")],
        element_types=ARCHITECTURAL_ONLY | {"IfcFooting"},
    )
    assert "DISCIPLINE_STRUCTURAL_NOT_IN_IFC" not in _by_code(findings)


def test_no_discipline_work_means_no_discipline_finding():
    findings = _evaluate(task_texts=[(str(uuid4()), "Paint the entrance hall")])
    assert not [item for item in findings if item.category == "DISCIPLINE_MISMATCH"]


def test_every_configured_discipline_can_produce_a_finding():
    for discipline, (terms, _classes, _label) in DISCIPLINE_TERMS.items():
        term = sorted(terms)[0]
        # No elements at all, so no discipline can be considered represented.
        findings = _evaluate(task_texts=[(str(uuid4()), f"Works involving {term} on site")],
                             element_types=set())
        assert f"DISCIPLINE_{discipline}_NOT_IN_IFC" in _by_code(findings), discipline


def test_a_villa_project_with_a_tower_model_raises_a_scale_anomaly():
    findings = _evaluate(storey_names=[f"Floor {index}" for index in range(1, 15)])
    finding = _by_code(findings)["IFC_MODEL_SCALE_ANOMALY"]
    assert finding.severity == "WARNING"
    assert finding.evidence["modelStoreys"] == 14
    assert finding.evidence["expectedStoreyRange"] == [1, 4]
    # The check is an inference, and says so rather than claiming certainty.
    assert "assumption" in finding.evidence


def test_scale_anomaly_is_silent_when_the_model_matches_the_project_type():
    assert "IFC_MODEL_SCALE_ANOMALY" not in _by_code(_evaluate(storey_names=["Ground Floor", "Floor 1"]))


def test_scheduled_work_in_an_unmodelled_area_is_reported_with_its_dates():
    task_id = str(uuid4())
    findings = _evaluate(scheduled_tasks=[{
        "taskId": task_id, "taskCode": "T-204", "name": "Floor 7 blockwork",
        "text": "Floor 7 blockwork in room 705", "discipline": None, "plannedStart": "2026-09-01",
    }])
    finding = _by_code(findings)["SCHEDULED_WORK_NOT_MAPPABLE_TO_IFC"]
    assert finding.category == "SCHEDULE_MODEL_MISMATCH"
    entry = finding.evidence["unmappableTasks"][0]
    assert entry["taskId"] == task_id
    assert entry["plannedStart"] == "2026-09-01"
    assert entry["unresolvedFloors"] == ["7"]


def test_unscheduled_work_is_not_reported_as_a_schedule_inconsistency():
    findings = _evaluate(scheduled_tasks=[{
        "taskId": str(uuid4()), "taskCode": "T-9", "name": "Floor 7 blockwork",
        "text": "Floor 7 blockwork", "discipline": None, "plannedStart": None,
    }])
    assert "SCHEDULED_WORK_NOT_MAPPABLE_TO_IFC" not in _by_code(findings)


def test_scheduled_work_inside_the_model_is_not_reported():
    findings = _evaluate(scheduled_tasks=[{
        "taskId": str(uuid4()), "taskCode": "T-9", "name": "Floor 1 blockwork",
        "text": "Floor 1 blockwork in room 101", "discipline": None, "plannedStart": "2026-09-01",
    }])
    assert "SCHEDULED_WORK_NOT_MAPPABLE_TO_IFC" not in _by_code(findings)


def test_acceptance_unrelated_sample_ifc_produces_several_explained_mismatches():
    """§28: an obviously unrelated model must not come back as 'looks fine'."""
    task_ids = [str(uuid4()) for _ in range(4)]
    findings = evaluate_ifc_compatibility(
        project_name="Al Quds Residential Villa",
        project_type="residential villa",
        summary={
            "projectOverview": {"projectName": "AC20-FZK-Haus", "buildingName": "FZK Haus Sample"},
            "assetType": {"value": "OFFICE"},
            "elements": 40,
        },
        storey_names=[f"Floor {index}" for index in range(1, 13)],
        space_names=["Room 12"],
        element_types={"IfcWall", "IfcSlab", "IfcRoof"},
        task_texts=[
            (task_ids[0], "Install electrical sockets on floor 3"),
            (task_ids[1], "Run ductwork for the air conditioning on floor 3"),
            (task_ids[2], "Install windows in room 305"),
            (task_ids[3], "Sanitary pipe installation in room 305"),
        ],
        scheduled_tasks=[{
            "taskId": task_ids[0], "taskCode": "T-1", "name": "Electrical sockets room 305",
            "text": "Install electrical sockets in room 305", "discipline": "electrical",
            "plannedStart": "2026-09-10",
        }],
    )
    codes = _by_code(findings)
    # Identity, disciplines, elements, spaces and schedule all disagree.
    assert "IFC_PROJECT_NAME_MISMATCH" in codes
    assert "IFC_ASSET_TYPE_MISMATCH" in codes
    assert "DISCIPLINE_ELECTRICAL_NOT_IN_IFC" in codes
    assert "DISCIPLINE_MECHANICAL_HVAC_NOT_IN_IFC" in codes
    assert "DISCIPLINE_PLUMBING_NOT_IN_IFC" in codes
    assert "TASK_WINDOW_ELEMENTS_MISSING" in codes
    assert "TASK_ROOM_NOT_IN_IFC" in codes
    assert "SCHEDULED_WORK_NOT_MAPPABLE_TO_IFC" in codes
    # Every finding carries the evidence behind it.
    for finding in findings:
        assert finding.evidence, finding.code
        assert finding.reason, finding.code
        assert finding.recommended_action, finding.code
        assert 0 < finding.confidence <= 1, finding.code
        assert finding.severity in {"CRITICAL", "HIGH", "WARNING", "INFO"}, finding.code


def test_a_genuinely_matching_model_stays_quiet():
    findings = evaluate_ifc_compatibility(
        project_name="Al Quds Residential Villa",
        project_type="residential villa",
        summary={
            "projectOverview": {"projectName": "Al Quds Residential Villa", "buildingType": "RESIDENTIAL"},
            "assetType": {"value": "RESIDENTIAL"},
            "elements": 300,
        },
        storey_names=["Ground Floor", "Floor 1"],
        space_names=["Room 101"],
        element_types={"IfcWall", "IfcWindow", "IfcDoor", "IfcSlab", "IfcCableCarrierSegment"},
        task_texts=[(str(uuid4()), "Install electrical conduit and windows in room 101")],
        scheduled_tasks=[{
            "taskId": str(uuid4()), "taskCode": "T-1", "name": "Room 101 fit-out",
            "text": "Install electrical conduit and windows in room 101",
            "discipline": "electrical", "plannedStart": "2026-09-01",
        }],
    )
    assert findings == [], [item.code for item in findings]
