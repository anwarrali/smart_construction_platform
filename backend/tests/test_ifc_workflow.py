from types import SimpleNamespace

import pytest

from app.services.ifc_processing_service import transition_version


def version(status="UPLOADED"):
    return SimpleNamespace(processing_status=status, processing_progress=0, row_version=1)


def test_processing_state_machine_accepts_expected_sequence():
    item = version()
    for state, progress in [("QUEUED", 5), ("PARSING", 20), ("BUILDING_HIERARCHY", 38), ("EXTRACTING_ELEMENTS", 52), ("EXTRACTING_PROPERTIES", 68), ("QUALITY_CHECKS", 82), ("ANALYZING", 92), ("READY", 100)]:
        transition_version(item, state, progress)
    assert item.processing_status == "READY"
    assert item.processing_progress == 100
    assert item.row_version == 9


def test_processing_state_machine_rejects_unsafe_jump():
    with pytest.raises(ValueError, match="Invalid IFC state transition"):
        transition_version(version(), "READY", 100)
