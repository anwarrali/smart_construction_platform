"""Parse the representative IFC corpus with the real parser.

`minimal_ifc4.ifc` proves one wall in one schema. These fixtures cover what an
actual project sends: two storeys of mixed-discipline content, the older
IFC2X3 export that most authoring tools still emit, an IFC4X3 infrastructure
model with no building at all, Arabic metadata, and the two shapes that make
downstream intelligence go quiet — a model with no storey hierarchy and one
with colliding element tags.

Every fixture was produced by IfcOpenShell and is checked in, so the corpus is
identical on every machine and in CI.
"""

from pathlib import Path

import pytest

from app.services.ifc_parser import IFCParser

pytest.importorskip("ifcopenshell")

FIXTURES = Path(__file__).parent / "fixtures"


def parse(name: str):
    return IFCParser().parse(FIXTURES / name)


@pytest.fixture(scope="module")
def ifc4():
    return parse("multi_discipline_ifc4.ifc")


@pytest.fixture(scope="module")
def ifc2x3():
    return parse("multi_discipline_ifc2x3.ifc")


@pytest.mark.parametrize(
    "name, expected_schema",
    [
        ("multi_discipline_ifc4.ifc", "IFC4"),
        ("multi_discipline_ifc2x3.ifc", "IFC2X3"),
        ("infrastructure_ifc4x3.ifc", "IFC4X3"),
        ("arabic_ifc4.ifc", "IFC4"),
        ("no_storey_ifc4.ifc", "IFC4"),
        ("duplicate_tags_ifc4.ifc", "IFC4"),
    ],
)
def test_every_supported_schema_family_parses(name, expected_schema):
    parsed = parse(name)
    assert parsed.schema.upper() == expected_schema
    assert parsed.summary["projectOverview"]["ifcSchema"].upper() == expected_schema


def test_multi_discipline_model_separates_every_discipline(ifc4):
    breakdown = ifc4.summary["disciplineBreakdown"]
    # Two storeys of the same kit, so every count is doubled.
    assert breakdown["STRUCTURAL"] == 4
    assert breakdown["ARCHITECTURAL"] == 10
    assert breakdown["MECHANICAL"] == 2
    assert breakdown["ELECTRICAL"] == 4
    assert breakdown["PLUMBING"] == 2
    assert breakdown["FIRE_PROTECTION"] == 2
    # A proxy with no descriptive evidence must not be guessed into a trade.
    assert breakdown["UNCLASSIFIED"] == 2


def test_multi_discipline_model_places_elements_in_the_hierarchy(ifc4):
    assert ifc4.summary["mainStatistics"]["storeys"] == 2
    assert ifc4.summary["mainStatistics"]["spaces"] == 8
    assert all(item.storey_global_id for item in ifc4.elements)
    assert not ifc4.warnings


def test_office_building_is_recognised_from_room_names(ifc4):
    asset = ifc4.summary["assetType"]
    assert asset["value"] == "OFFICE_BUILDING"
    assert "office" in asset["evidence"]


def test_ifc4_projected_crs_is_read_as_full_georeferencing(ifc4):
    georeferencing = ifc4.summary["georeferencing"]
    assert georeferencing["status"] == "FULLY_GEOREFERENCED"
    assert georeferencing["epsgCode"] == "32636"
    assert georeferencing["easting"] == 700000.0


def test_ifc2x3_cannot_express_a_crs_and_is_not_claimed_to_be_georeferenced(ifc2x3):
    # IFC2X3 has no IfcProjectedCRS, so latitude/longitude alone is all there
    # is. Reporting anything stronger than partial would overstate the source.
    assert ifc2x3.summary["georeferencing"]["status"] == "PARTIALLY_GEOREFERENCED"
    assert ifc2x3.summary["georeferencing"]["epsgCode"] is None


def test_ifc2x3_extracts_the_same_hierarchy_as_ifc4(ifc4, ifc2x3):
    for key in ("storeys", "spaces"):
        assert ifc2x3.summary["mainStatistics"][key] == ifc4.summary["mainStatistics"][key]


def test_infrastructure_model_without_a_building_is_not_called_a_building():
    parsed = parse("infrastructure_ifc4x3.ifc")
    assert parsed.summary["disciplineBreakdown"]["SITE_CIVIL"] == 4
    assert parsed.summary["assetType"]["value"] == "UNKNOWN"
    assert parsed.summary["assetType"]["confidence"] < 0.5


def test_arabic_metadata_survives_extraction_unchanged():
    parsed = parse("arabic_ifc4.ifc")
    storey = next(node for node in parsed.nodes if node.node_type == "STOREY")
    assert storey.name == "الطابق الأرضي"
    wall = next(item for item in parsed.elements if item.entity_type == "IfcWall")
    assert wall.name == "جدار خارجي"
    assert wall.tag == "ج-01"
    assert "ساعتان" in str(wall.properties)


def test_arabic_space_is_classified_from_its_english_long_name():
    parsed = parse("arabic_ifc4.ifc")
    room = next(node for node in parsed.nodes if node.node_type == "SPACE")
    assert room.metadata["spaceClassification"]["category"] == "BATHROOM"


def test_a_model_with_no_storey_hierarchy_warns_instead_of_failing():
    parsed = parse("no_storey_ifc4.ifc")
    assert parsed.elements
    assert any("IfcBuildingStorey" in warning for warning in parsed.warnings)
    assert all(item.storey_global_id is None for item in parsed.elements)


def test_unnamed_elements_are_reported_as_missing_rather_than_invented():
    parsed = parse("no_storey_ifc4.ifc")
    element = parsed.elements[0]
    assert element.metadata["originalName"] is None
    assert "name" in element.metadata["missingData"]
    assert element.name.startswith("Unnamed ")


def test_repeated_element_tags_are_preserved_for_the_quality_check():
    parsed = parse("duplicate_tags_ifc4.ifc")
    assert [item.tag for item in parsed.elements] == ["C-01"] * 3
    # Distinct GlobalIds: the duplication is in the tag, not the identifier.
    assert len({item.global_id for item in parsed.elements}) == 3


def test_task_suggestions_count_the_elements_they_cite(ifc4):
    suggestion = next(item for item in ifc4.task_suggestions if item["title"] == "Column installation")
    assert suggestion["elementCount"] == 2
    assert len(suggestion["relatedGlobalIds"]) == 2
    assert suggestion["discipline"] == "STRUCTURAL"
