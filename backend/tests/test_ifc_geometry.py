import json
import struct
from array import array
from pathlib import Path

import pytest

from app.services.ifc_geometry_service import MAGIC, build_geometry_artifact


def _write_renderable_ifc(path):
    ifcopenshell = pytest.importorskip("ifcopenshell")
    api = pytest.importorskip("ifcopenshell.api")
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Geometry test")
    api.run("unit.assign_unit", model)
    model_context = api.run("context.add_context", model, context_type="Model")
    body_context = api.run(
        "context.add_context", model, context_type="Model", context_identifier="Body",
        target_view="MODEL_VIEW", parent=model_context,
    )
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    storey = api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Level 01")
    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Test wall")
    api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    api.run("aggregate.assign_object", model, products=[building], relating_object=site)
    api.run("aggregate.assign_object", model, products=[storey], relating_object=building)
    representation = api.run(
        "geometry.add_wall_representation", model, context=body_context,
        length=5.0, height=3.0, thickness=0.2,
    )
    api.run("geometry.assign_representation", model, product=wall, representation=representation)
    api.run("spatial.assign_container", model, products=[wall], relating_structure=storey)
    model.write(str(path))
    return wall.id()


def test_real_ifc_geometry_artifact_contains_mesh_and_stable_express_id(tmp_path):
    source = tmp_path / "renderable.ifc"
    target = tmp_path / "renderable.bimgeom"
    wall_step_id = _write_renderable_ifc(source)

    header = build_geometry_artifact(
        source, target, {wall_step_id}, workers=1, max_vertices=100_000,
        version_id="test-version", source_hash="test-hash",
    )

    assert header["shapeCount"] == 1
    assert header["triangleCount"] == 12
    assert header["vertexCount"] == 8
    assert header["partial"] is False
    payload = target.read_bytes()
    assert payload[:8] == MAGIC
    header_length = struct.unpack("<I", payload[8:12])[0]
    stored_header = json.loads(payload[12:12 + header_length])
    offset = 12 + header_length + stored_header["vertexCount"] * 3 * 4
    express_ids = array("I")
    express_ids.frombytes(payload[offset:offset + stored_header["vertexCount"] * 4])
    assert set(express_ids) == {wall_step_id}
    expected_bytes = (
        12 + header_length + stored_header["vertexCount"] * 3 * 4
        + stored_header["vertexCount"] * 4 + stored_header["indexCount"] * 4
    )
    assert len(payload) == expected_bytes


def test_geometry_artifact_rejects_metadata_only_ifc(tmp_path):
    # ifcopenshell is a real, pinned production dependency (requirements.txt),
    # installed in the actual backend image — confirmed there by running this
    # exact test inside the container, where it passes. It is simply heavy and
    # awkward to install into an ad-hoc local Python environment, so an
    # environment without it should skip cleanly rather than fail with a
    # confusing ModuleNotFoundError, exactly like the sibling test above does.
    pytest.importorskip("ifcopenshell")
    source = Path(__file__).parent / "fixtures" / "minimal_ifc4.ifc"
    with pytest.raises(RuntimeError, match="did not produce any renderable geometry"):
        build_geometry_artifact(
            source, tmp_path / "missing.bimgeom", {31}, workers=1,
            max_vertices=100_000, version_id="test-version", source_hash="test-hash",
        )
