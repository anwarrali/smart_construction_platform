from pathlib import Path

import pytest

from app.services.file_storage import _matches_signature
from app.services.ifc_parser import IFCParser, discipline_for_class, stable_json_hash
from app.services.ifc_intelligence import classify_element_category, classify_space


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_ifc4.ifc"


def test_ifc_signature_requires_step_header_and_sections():
    content = FIXTURE.read_bytes()
    assert _matches_signature(".ifc", content)
    assert not _matches_signature(".ifc", b"ISO-10303-21;\nHEADER;\n")
    assert not _matches_signature(".ifc", b"<script>alert(1)</script>")


def test_stable_json_hash_ignores_dict_order():
    assert stable_json_hash({"b": 2, "a": 1}) == stable_json_hash({"a": 1, "b": 2})


def test_real_ifcopenshell_extracts_spatial_and_properties():
    pytest.importorskip("ifcopenshell")
    parsed = IFCParser().parse(FIXTURE)
    assert parsed.schema.upper().startswith("IFC4")
    assert {node.node_type for node in parsed.nodes} >= {"PROJECT", "SITE", "BUILDING", "STOREY", "SPACE"}
    wall = next(item for item in parsed.elements if item.entity_type == "IfcWall")
    assert wall.space_global_id == "7YvctVUKr0kugbFTf53O9L"
    assert wall.storey_global_id == "5YvctVUKr0kugbFTf53O9L"
    assert "Pset_WallCommon" in wall.properties
    assert parsed.summary["elements"] == 1
    assert parsed.summary["projectOverview"]["ifcSchema"].upper().startswith("IFC4")
    assert parsed.summary["mainStatistics"]["walls"] == 1
    assert parsed.summary["modelCompleteness"]["validGlobalIds"]["count"] == 1
    assert parsed.summary["georeferencing"]["status"] in {"FULLY_GEOREFERENCED", "PARTIALLY_GEOREFERENCED", "LOCAL_COORDINATES_ONLY", "MISSING"}


def test_discipline_classification_includes_evidence_and_confidence():
    discipline, confidence, reason, attributes = discipline_for_class("IfcCableCarrierSegment")
    assert discipline == "ELECTRICAL"
    assert confidence >= .9
    assert reason
    assert attributes == ["IFC class: IfcCableCarrierSegment"]


def test_unknown_ifc_class_is_not_given_a_misleading_discipline():
    discipline, confidence, _, _ = discipline_for_class("IfcBuildingElementProxy")
    assert discipline == "UNCLASSIFIED"
    assert confidence < .5


def test_space_classification_is_evidence_backed_and_conservative():
    bathroom = classify_space([("IfcSpace.Name", "Master Bathroom")])
    assert bathroom["category"] == "BATHROOM"
    assert bathroom["confidence"] >= .95
    assert bathroom["evidence"] == "Master Bathroom"
    unknown = classify_space([("IfcSpace.Name", "Room 203")])
    assert unknown["category"] == "UNKNOWN"
    assert unknown["evidence"] is None


def test_generic_proxy_category_requires_a_whole_keyword():
    door = classify_element_category("IfcBuildingElementProxy", [("IfcProduct.ObjectType", "External Door")])
    assert door["category"] == "DOOR"
    assert door["source"] == "IfcProduct.ObjectType"
    assert classify_element_category("IfcBuildingElementProxy", [("IfcProduct.Name", "Outdoor unit")])["category"] == "UNKNOWN"


def test_generic_flow_discipline_uses_descriptive_evidence():
    discipline, confidence, _, evidence = discipline_for_class("IfcFlowTerminal", system_name="Supply Air", name="Vent cap")
    assert discipline == "MECHANICAL"
    assert confidence >= .8
    assert any("Supply Air" in item for item in evidence)
