"""Upload to finding, on a real IFC with real solids.

`tests/fixtures/interference_ifc4.ifc` is an IFC4 model whose four elements
carry genuine extruded solids, placed so the answer is arithmetic a reader can
check without running anything:

    beam        x[-0.15, 0.15]  y[-2.0, 2.0]  z[3.0, 3.4]   IfcBeam
    duct        x[-2.0, 2.0]    y[-0.25, .25] z[3.1, 3.6]   IfcDuctSegment
    clear_duct  same, but z[6.0, 6.5]                       IfcDuctSegment
    tray        x[-2.0, 2.0]    y[-0.15, .15] z[3.4, 3.9]   IfcCableCarrierSegment

The duct crosses the beam, overlapping by 0.3 m on its shallowest axis. The
clear duct is three metres above it. The tray rests exactly on the beam's top
face, so it touches without overlapping — the case a naive test would report
and a coordinator would reject.

Exactly one finding is correct.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.ifc import list_findings
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.ifc import IFCCoordinationFinding, IFCElement, IFCModelGroup, IFCModelVersion
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services import ifc_processing_service as service

pytest.importorskip("ifcopenshell")

FIXTURE = Path(__file__).parent / "fixtures" / "interference_ifc4.ifc"
INTERFERENCE = service.INTERFERENCE_FINDING_TYPE


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:  # pragma: no cover - only without a database
        session.close()
        pytest.skip("database is not reachable")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def processed(db, tmp_path, monkeypatch):
    """The fixture uploaded and taken all the way through processing."""
    suffix = uuid4().hex[:10]
    root = tmp_path / "private"
    (root / "ifc").mkdir(parents=True)
    storage_key = f"ifc/{suffix}.ifc"
    (root / storage_key).write_bytes(FIXTURE.read_bytes())
    # The parser and the tessellator both run in spawned processes that
    # re-read this from the environment; see test_ifc_secondary_product_failure.
    monkeypatch.setenv("PRIVATE_UPLOAD_DIR", str(root))
    monkeypatch.setattr(settings, "PRIVATE_UPLOAD_DIR", str(root))
    monkeypatch.setattr(settings, "IFC_GEOMETRY_ENABLED", True)
    monkeypatch.setattr(settings, "IFC_COORDINATION_CHECKS_ENABLED", True)

    manager = User(full_name="ClashPm", email=f"clashpm-{suffix}@test.local", hashed_password="x",
                   role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    owner = User(full_name="ClashOwner", email=f"clashowner-{suffix}@test.local", hashed_password="x",
                 role=UserRole.OWNER, status=UserStatus.ACTIVE)
    db.add_all([manager, owner])
    db.flush()
    project = Project(name=f"Interference {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=manager.id,
                         role_on_project=UserRole.PROJECT_MANAGER, is_active=True))
    group = IFCModelGroup(project_id=project.id, name=f"Group {suffix}", created_by_id=manager.id)
    db.add(group)
    db.flush()
    version = IFCModelVersion(
        project_id=project.id, model_group_id=group.id, version_number=1,
        title="Coordination model", processing_status="UPLOADED", uploaded_by_id=manager.id,
        original_filename="interference.ifc", storage_key=storage_key,
        file_hash=uuid4().hex, file_size=FIXTURE.stat().st_size,
    )
    db.add(version)
    db.commit()

    service.process_version(db, version.id, manager.id)
    db.refresh(version)
    try:
        yield {"version": version, "project": project, "manager": manager}
    finally:
        _purge(db, project.id, [manager.id, owner.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    params = {"projects": [project_id], "users": list(user_ids)}
    for statement in (
        "DELETE FROM ifc_coordination_findings WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_elements WHERE version_id IN (SELECT id FROM ifc_model_versions WHERE project_id = ANY(:projects))",
        "DELETE FROM ifc_spatial_nodes WHERE version_id IN (SELECT id FROM ifc_model_versions WHERE project_id = ANY(:projects))",
        "DELETE FROM ifc_processing_jobs WHERE version_id IN (SELECT id FROM ifc_model_versions WHERE project_id = ANY(:projects))",
        "DELETE FROM ifc_suggestions WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_entity_links WHERE project_id = ANY(:projects)",
        "DELETE FROM ai_insights WHERE project_id = ANY(:projects)",
        "DELETE FROM tasks WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM issues WHERE project_id = ANY(:projects) OR raised_by_id = ANY(:users)",
        "DELETE FROM ifc_model_versions WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_model_groups WHERE project_id = ANY(:projects)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        try:
            db.execute(text(statement), params)
        except SQLAlchemyError:
            db.rollback()
    db.commit()


def _interferences(db, version):
    return db.query(IFCCoordinationFinding).filter(
        IFCCoordinationFinding.version_id == version.id,
        IFCCoordinationFinding.finding_type == INTERFERENCE,
    ).all()


def test_the_model_processes_and_produces_geometry(processed):
    version = processed["version"]
    assert version.processing_status in {"READY", "READY_WITH_WARNINGS"}
    assert version.geometry_status in {"GEOMETRY_READY", "GEOMETRY_PARTIAL"}, version.geometry_error


def test_every_element_gets_its_measured_extent_from_tessellation(db, processed):
    elements = db.query(IFCElement).filter(IFCElement.version_id == processed["version"].id).all()
    assert len(elements) == 4
    for element in elements:
        box = element.bounding_box_json
        assert box, f"{element.name} has no bounding box"
        assert box["source"] == "IFC_GEOMETRY_TESSELLATION"
        assert box["coordinateSpace"] == "IFC_WORLD"
        assert box["lengthUnit"] == "m"
    beam = next(item for item in elements if item.entity_type == "IfcBeam")
    assert beam.bounding_box_json["min"] == pytest.approx([-0.15, -2.0, 3.0])
    assert beam.bounding_box_json["max"] == pytest.approx([0.15, 2.0, 3.4])


def test_exactly_the_real_interference_is_found(db, processed):
    findings = _interferences(db, processed["version"])
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "HIGH"
    assert finding.confidence == pytest.approx(0.70)
    assert finding.geometry_evidence_json["penetrationMetres"] == pytest.approx(0.3)


def test_the_finding_names_both_elements_and_they_exist(db, processed):
    finding = _interferences(db, processed["version"])[0]
    structural = db.get(IFCElement, finding.element_a_id)
    served = db.get(IFCElement, finding.element_b_id)
    assert structural.entity_type == "IfcBeam"
    assert served.entity_type == "IfcDuctSegment"
    assert served.name == "Supply Duct SA-01"
    assert sorted(finding.affected_disciplines_json) == ["MECHANICAL", "STRUCTURAL"]


def test_the_touching_tray_is_not_reported(db, processed):
    findings = _interferences(db, processed["version"])
    reported = {db.get(IFCElement, item.element_b_id).name for item in findings}
    assert "Cable Tray CT-01" not in reported
    assert "Return Duct RA-01" not in reported


def test_the_finding_records_where_to_go_and_look(db, processed):
    finding = _interferences(db, processed["version"])[0]
    assert finding.storey == "Level 1"
    assert finding.geometry_evidence_json["location"]["storeySource"] == "IFC_SPATIAL_CONTAINMENT"


def test_the_evidence_can_be_recomputed_from_what_was_stored(db, processed):
    """Traceability in the strict sense: the claim is checkable from the record."""
    finding = _interferences(db, processed["version"])[0]
    evidence = finding.geometry_evidence_json
    left = evidence["structural"]["boundingBox"]
    right = evidence["service"]["boundingBox"]
    overlap = [min(left["max"][axis], right["max"][axis]) - max(left["min"][axis], right["min"][axis])
               for axis in range(3)]
    assert min(overlap) == pytest.approx(evidence["penetrationMetres"])
    # And the stored boxes are the elements' own stored boxes, not a copy that
    # could have drifted.
    assert db.get(IFCElement, finding.element_a_id).bounding_box_json["min"] == pytest.approx(left["min"])


def test_the_summary_reports_what_was_analysed(db, processed):
    report = processed["version"].model_summary_json["interference"]
    assert report["analysed"] is True
    assert report["structuralElements"] == 1
    assert report["serviceElements"] == 3
    assert report["stored"] == 1
    assert report["skippedReason"] is None


# --- Re-running -------------------------------------------------------------

def test_re_running_does_not_duplicate_findings(db, processed):
    service.run_interference_analysis(db, processed["version"].id)
    service.run_interference_analysis(db, processed["version"].id)
    assert len(_interferences(db, processed["version"])) == 1


def test_a_pair_marked_false_positive_stays_dismissed_on_re_analysis(db, processed):
    """The correction path. An engineer who has ruled on a pair is not re-asked."""
    finding = _interferences(db, processed["version"])[0]
    finding.status = "FALSE_POSITIVE"
    finding.false_positive = True
    db.commit()

    service.run_interference_analysis(db, processed["version"].id)

    findings = _interferences(db, processed["version"])
    assert len(findings) == 1
    assert findings[0].status == "FALSE_POSITIVE"
    report = db.get(IFCModelVersion, processed["version"].id).model_summary_json["interference"]
    assert report["reviewedPairsPreserved"] == 1
    assert report["stored"] == 0


def test_metadata_quality_findings_are_untouched_by_interference_analysis(db, processed):
    """The two rule families share a table and must not delete each other."""
    others = db.query(IFCCoordinationFinding).filter(
        IFCCoordinationFinding.version_id == processed["version"].id,
        IFCCoordinationFinding.finding_type != INTERFERENCE,
    ).count()
    assert others > 0
    service.run_interference_analysis(db, processed["version"].id)
    assert db.query(IFCCoordinationFinding).filter(
        IFCCoordinationFinding.version_id == processed["version"].id,
        IFCCoordinationFinding.finding_type != INTERFERENCE,
    ).count() == others


def test_metadata_quality_findings_keep_full_confidence(db, processed):
    """A missing material is missing. Only inferred findings are uncertain."""
    quality = db.query(IFCCoordinationFinding).filter(
        IFCCoordinationFinding.version_id == processed["version"].id,
        IFCCoordinationFinding.finding_type == "MISSING_MATERIAL",
    ).first()
    assert quality is not None
    assert quality.confidence == pytest.approx(1.0)


# --- What a reviewer is handed ---------------------------------------------

def _listed(db, processed):
    """The reviewer's findings, unwrapped from the page around them.

    `list_findings` is paged now, and its `page`/`page_size` defaults are
    `Query(...)` markers that only the request pipeline resolves — so calling
    the handler directly means passing them. One large page keeps these
    assertions about grouping, ordering and evidence; paging has its own tests
    in `test_ifc_findings_pagination.py`.
    """
    return list_findings(
        processed["project"].id, page=1, page_size=200,
        db=db, current_user=processed["manager"],
    )["items"]


def test_the_findings_list_carries_confidence_and_location(db, processed):
    interference = next(item for item in _listed(db, processed) if item["findingType"] == INTERFERENCE)
    assert interference["confidence"] == pytest.approx(0.70)
    assert interference["storey"] == "Level 1"
    assert interference["claim"] == "potential-interference"
    assert "not prove" in interference["verification"]


def test_the_worst_finding_is_listed_first(db, processed):
    listed = _listed(db, processed)
    assert listed[0]["findingType"] == INTERFERENCE
    assert listed[0]["severity"] == "HIGH"
    # Severity is stored as text; ordering it in SQL would have put MEDIUM first.
    order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    positions = [order.index(item["severity"]) for item in listed]
    assert positions == sorted(positions)


def test_each_interference_pair_stays_separately_reviewable(db, processed):
    """Merging pairs would leave a reviewer unable to dismiss just one."""
    version = processed["version"]
    elements = db.query(IFCElement).filter(IFCElement.version_id == version.id).all()
    beam = next(item for item in elements if item.entity_type == "IfcBeam")
    tray = next(item for item in elements if item.entity_type == "IfcCableCarrierSegment")
    # A second, independent pair on the same revision.
    db.add(IFCCoordinationFinding(
        project_id=version.project_id, version_id=version.id,
        element_a_id=beam.id, element_b_id=tray.id, finding_type=INTERFERENCE,
        severity="LOW", confidence=0.55, title="Second pair", description="Another pair",
        geometry_evidence_json={"claim": "potential-interference"},
        affected_disciplines_json=["ELECTRICAL", "STRUCTURAL"], status="PENDING",
    ))
    db.commit()
    interferences = [item for item in _listed(db, processed) if item["findingType"] == INTERFERENCE]
    assert len(interferences) == 2
    assert len({item["id"] for item in interferences}) == 2


def test_metadata_quality_findings_are_still_aggregated_per_rule(db, processed):
    """The existing shape for the existing rules, unchanged."""
    quality = [item for item in _listed(db, processed) if item["findingType"] == "MISSING_MATERIAL"]
    assert len(quality) == 1
    assert quality[0]["affectedElementCount"] == 4
    assert quality[0]["confidence"] == pytest.approx(1.0)
