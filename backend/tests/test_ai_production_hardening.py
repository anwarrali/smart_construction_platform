from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import TaskStatus
from app.schemas.voice_command import VoiceTranscriptCommandCreate
from app.schemas.voice_analysis import SuggestedAction, SuggestedActionType
from app.services.voice_action_policy import action_risk
from app.services.ai_action_history_service import undo_status
from app.services.domain_event_dispatcher import emit_domain_event
from app.services.ifc_compatibility_service import evaluate_ifc_compatibility


client = TestClient(app)


def test_transcript_simulation_schema_does_not_accept_client_role_or_extracted_entities():
    with pytest.raises(ValidationError):
        VoiceTranscriptCommandCreate.model_validate({
            "transcript": "Foundation reinforcement reached 75 percent",
            "projectId": str(uuid4()),
            "idempotencyKey": "mobile-request-001",
            "role": "administrator",
            "extractedEntities": {"taskId": str(uuid4())},
        })


def test_project_manager_task_creation_proposal_is_strict_and_high_risk():
    proposal = SuggestedAction(
        type=SuggestedActionType.CREATE_TASK,
        reason="Explicit project manager request",
        payload={"title": "Inspect basement waterproofing", "sourceDiscipline": "civil"},
        confidence=.94,
    )
    assert proposal.target_id is None
    assert proposal.payload_dict()["title"] == "Inspect basement waterproofing"
    assert action_risk(proposal.type).value == "HIGH"


def test_task_creation_proposal_requires_a_title():
    with pytest.raises(ValidationError, match="CREATE_TASK requires title"):
        SuggestedAction(
            type=SuggestedActionType.CREATE_TASK,
            reason="Incomplete request",
            payload={"description": "No title"},
            confidence=.9,
        )


def test_unrelated_ifc_identity_is_critical_and_explainable():
    findings = evaluate_ifc_compatibility(
        project_name="Al Quds Residential Villa",
        project_type="residential villa",
        summary={
            "projectOverview": {"projectName": "North Harbor Airport Terminal", "buildingName": "Terminal C"},
            "assetType": {"value": "TRANSPORT"},
            "elements": 100,
        },
        storey_names=["Ground Floor"],
        space_names=[],
        element_types={"IfcSlab"},
        task_texts=[],
    )
    mismatch = next(item for item in findings if item.code == "IFC_PROJECT_NAME_MISMATCH")
    assert mismatch.severity == "CRITICAL"
    assert mismatch.evidence["platformProjectName"] == "Al Quds Residential Villa"
    assert "ifcNameScores" in mismatch.evidence


def test_task_floor_room_and_element_references_are_checked_against_ifc():
    findings = evaluate_ifc_compatibility(
        project_name="Tower A",
        project_type=None,
        summary={"projectOverview": {"projectName": "Tower A"}, "elements": 30},
        storey_names=["Floor 1", "Floor 2", "Floor 3"],
        space_names=["Room 201"],
        element_types={"IfcWall"},
        task_texts=[
            (str(uuid4()), "Install Floor 5 windows in Room 204"),
        ],
    )
    codes = {item.code for item in findings}
    assert "TASK_FLOOR_NOT_IN_IFC" in codes
    assert "TASK_ROOM_NOT_IN_IFC" in codes
    assert "TASK_WINDOW_ELEMENTS_MISSING" in codes


def test_major_ifc_revision_drift_is_reported_without_auto_rejection():
    findings = evaluate_ifc_compatibility(
        project_name="Tower A",
        project_type=None,
        summary={
            "projectOverview": {"projectName": "Tower A"},
            "elements": 900,
            "mainStatistics": {"storeys": 11, "spaces": 150},
        },
        storey_names=[f"Floor {value}" for value in range(1, 12)],
        space_names=[],
        element_types={"IfcWall"},
        task_texts=[],
        previous_summary={"elements": 100, "mainStatistics": {"storeys": 4, "spaces": 20}},
    )
    drift = next(item for item in findings if item.code == "IFC_MAJOR_REVISION_DRIFT")
    assert drift.severity == "HIGH"
    assert drift.recommended_action


def test_compatible_ifc_does_not_generate_identity_or_scope_mismatch():
    findings = evaluate_ifc_compatibility(
        project_name="Tower A Residential",
        project_type="residential",
        summary={
            "projectOverview": {"projectName": "Tower A Residential", "buildingType": "RESIDENTIAL"},
            "assetType": {"value": "RESIDENTIAL"},
            "elements": 10,
        },
        storey_names=["Floor 2"],
        space_names=["Room 204"],
        element_types={"IfcWindow", "IfcWall"},
        task_texts=[(str(uuid4()), "Install Floor 2 windows in Room 204")],
    )
    assert not {item.code for item in findings} & {
        "IFC_PROJECT_NAME_MISMATCH", "IFC_ASSET_TYPE_MISMATCH",
        "TASK_FLOOR_NOT_IN_IFC", "TASK_ROOM_NOT_IN_IFC", "TASK_WINDOW_ELEMENTS_MISSING",
    }


def test_only_progress_compensation_is_automatically_reversible():
    action = SimpleNamespace(result="APPLIED", undo_policy="MANUAL_REVIEW")
    available, reason = undo_status(MagicMock(), action)
    assert available is False
    assert reason == "Manual review required for this action type."


def test_progress_revert_is_blocked_when_newer_ai_action_exists():
    action = SimpleNamespace(
        id=uuid4(), result="APPLIED", undo_policy="AUTOMATIC_PROGRESS_COMPENSATION",
        entity_type="TASK", entity_id=uuid4(), created_at=datetime.now(timezone.utc),
    )
    db = MagicMock()
    first_query = MagicMock()
    second_query = MagicMock()
    first_query.filter.return_value.first.return_value = None
    second_query.filter.return_value.first.return_value = (uuid4(),)
    db.query.side_effect = [first_query, second_query]
    available, reason = undo_status(db, action)
    assert available is False
    assert "newer dependent" in reason


def test_domain_event_dispatcher_rejects_unknown_event_types_before_persistence():
    with pytest.raises(ValueError, match="Unsupported domain event"):
        emit_domain_event(
            MagicMock(), project_id=uuid4(), event_type="SQL_QUERY_EXECUTED",
            entity_type="QUERY", entity_id=uuid4(), actor_user_id=None,
        )


def test_transcript_simulation_requires_authenticated_backend_identity():
    response = client.post("/api/v1/voice/commands/from-transcript", json={
        "transcript": "Foundation reinforcement reached 75 percent",
        "projectId": str(uuid4()),
        "idempotencyKey": "mobile-request-auth-test",
    })
    assert response.status_code in {401, 403}


def test_ai_action_history_requires_authenticated_backend_identity():
    response = client.get("/api/v1/ai/actions", params={"project_id": str(uuid4())})
    assert response.status_code in {401, 403}
