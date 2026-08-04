import uuid

from app.services.ai_traceability_service import source_snapshot_hash


def test_ai_source_snapshot_is_stable_and_state_sensitive():
    source_id = uuid.uuid4()
    first = source_snapshot_hash("task", source_id, "official_project_information", "7")
    same = source_snapshot_hash("TASK", source_id, "OFFICIAL_PROJECT_INFORMATION", "7")
    changed = source_snapshot_hash("TASK", source_id, "REJECTED", "7")
    assert first == same
    assert first != changed
