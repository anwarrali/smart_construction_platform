"""Paging the findings queue, and the filters that had to move with it.

`GET /ifc/findings` returned every finding in the project — every revision, no
limit — and the client kept one revision's worth and discarded the rest. On a
project with several revisions of a badly coordinated model that is thousands
of rows assembled, serialised and thrown away per request.

The fix is a filter and a page, and the filters are the interesting half: once
a response is one page, a filter applied in the browser filters *that page*,
so severity and discipline had to become the server's job or they would have
started lying. These tests pin the shape, the scoping, the ordering-before-
paging, and the fact that a page never reaches past its own project.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.company import Company
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.ifc import (
    IFCCoordinationFinding, IFCElement, IFCModelGroup, IFCModelVersion, IFCSpatialNode,
)
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services import rbac

PASSWORD = "Correct#12345"
INTERFERENCE = "INTERFERENCE_STRUCTURAL_SERVICE"


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
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def world(db):
    """Two revisions carrying findings of several severities and disciplines.

    Deliberately more than one page of interference findings on revision one,
    because a single page would let a broken `page` parameter pass unnoticed.
    """
    suffix = uuid.uuid4().hex[:10]
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    office = Company(name=f"IFC Paging Office {suffix}", kind="CONSULTING_OFFICE", is_active=True)
    db.add(office)
    db.flush()

    role = roles["project_manager"]
    manager = User(
        full_name=f"PagingManager{suffix}", email=f"paging.{suffix}@constro.io",
        hashed_password=hash_password(PASSWORD), role=UserRole.PROJECT_MANAGER,
        status=UserStatus.ACTIVE, company_id=office.id, org_role_id=role.id,
        is_internal=role.is_internal_only,
    )
    db.add(manager)
    db.flush()

    project = Project(
        name=f"IFC Paging {suffix}", status=ProjectStatus.ACTIVE,
        company_id=office.id, project_manager_id=manager.id,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(
        project_id=project.id, user_id=manager.id, role_on_project=manager.role,
        project_role_id=role.id, is_active=True,
    ))
    db.flush()

    group = IFCModelGroup(project_id=project.id, name=f"Paging model {suffix}", created_by_id=manager.id)
    db.add(group)
    db.flush()

    def revision(number: int) -> IFCModelVersion:
        item = IFCModelVersion(
            model_group_id=group.id, project_id=project.id, version_number=number,
            revision_code=f"P0{number}", version_type="DESIGN",
            title=f"Paging revision {number} {suffix}", original_filename=f"p{number}.ifc",
            storage_key=f"ifc/{uuid.uuid4()}_p{number}_{suffix}.ifc",
            file_hash=uuid.uuid4().hex + uuid.uuid4().hex, file_size=10,
            uploaded_by_id=manager.id, processing_status="READY", processing_progress=100,
            model_summary_json={},
        )
        db.add(item)
        db.flush()
        return item

    first, second = revision(1), revision(2)

    def element(version: IFCModelVersion, label: str) -> IFCElement:
        node = IFCSpatialNode(
            version_id=version.id, global_id=f"S{uuid.uuid4().hex[:20]}",
            entity_type="IfcBuildingStorey", name=f"{label} level", node_type="STOREY",
        )
        db.add(node)
        db.flush()
        item = IFCElement(
            version_id=version.id, global_id=f"E{uuid.uuid4().hex[:20]}",
            entity_type="IfcWall", name=f"{label} element", storey_node_id=node.id,
            properties_json={}, quantities_json={},
        )
        db.add(item)
        db.flush()
        return item

    base_time = datetime.now(timezone.utc)

    def add_finding(version, anchor, finding_type, severity, disciplines, index, confidence=1.0):
        row = IFCCoordinationFinding(
            project_id=project.id, version_id=version.id, element_a_id=anchor.id,
            finding_type=finding_type, severity=severity, confidence=confidence,
            title=f"{finding_type} {index}", description="Recorded for the paging tests.",
            geometry_evidence_json={"rule": finding_type, "elementIds": [str(anchor.id)]},
            affected_disciplines_json=disciplines, status="PENDING",
            created_at=base_time - timedelta(seconds=index),
        )
        db.add(row)
        return row

    first_anchor = element(first, "First")
    second_anchor = element(second, "Second")

    # One card per metadata rule, whatever the row count — so these four rules
    # produce four cards on revision one.
    for index, (rule, severity, disciplines) in enumerate((
        ("MISSING_MATERIAL", "MEDIUM", ["STRUCTURAL"]),
        ("MISSING_NAME", "MEDIUM", ["ARCHITECTURAL"]),
        ("MISSING_CLASSIFICATION", "LOW", ["ARCHITECTURAL"]),
        ("UNASSIGNED_STOREY", "CRITICAL", ["MECHANICAL"]),
    )):
        for _ in range(3):  # several rows, still one card
            add_finding(first, first_anchor, rule, severity, disciplines, index)

    # Interference stays one card per pair, so these are 60 separate cards.
    for index in range(60):
        add_finding(
            first, first_anchor, INTERFERENCE,
            "HIGH" if index < 10 else "LOW", ["STRUCTURAL", "PLUMBING"],
            100 + index, confidence=0.7,
        )

    # A second revision, to prove the version filter does something.
    add_finding(second, second_anchor, "MISSING_MATERIAL", "HIGH", ["ELECTRICAL"], 5)
    db.flush()

    created = {
        "manager": manager, "project": project, "first": first, "second": second,
        "metadata_cards": 4, "interference_cards": 60,
    }
    db.commit()

    try:
        yield created
    finally:
        db.rollback()
        db.query(IFCCoordinationFinding).filter(IFCCoordinationFinding.project_id == project.id).delete(synchronize_session=False)
        db.query(IFCModelVersion).filter(IFCModelVersion.project_id == project.id).delete(synchronize_session=False)
        db.query(IFCModelGroup).filter(IFCModelGroup.project_id == project.id).delete(synchronize_session=False)
        db.query(ProjectMember).filter(ProjectMember.project_id == project.id).delete(synchronize_session=False)
        db.query(Project).filter(Project.id == project.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == manager.id).delete(synchronize_session=False)
        db.query(Company).filter(Company.id == office.id).delete(synchronize_session=False)
        db.commit()


def _auth(client, user) -> dict:
    login = client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture()
def findings(client, world):
    def request(**params):
        response = client.get(
            f"/api/v1/projects/{world['project'].id}/ifc/findings",
            headers=_auth(client, world["manager"]), params=params,
        )
        assert response.status_code == 200, response.text
        return response.json()

    return request


# --- the shape --------------------------------------------------------------


def test_the_response_is_the_projects_existing_page_shape(findings):
    payload = findings()
    assert set(payload) >= {"items", "total", "page", "pageSize"}
    assert isinstance(payload["items"], list)


def test_a_page_is_never_larger_than_it_says(findings):
    payload = findings(page_size=10)
    assert payload["pageSize"] == 10
    assert len(payload["items"]) == 10


def test_the_total_counts_the_whole_result_not_the_page(findings, world):
    payload = findings(version_id=str(world["first"].id), page_size=10)
    assert payload["total"] == world["metadata_cards"] + world["interference_cards"]
    assert len(payload["items"]) == 10


def test_every_card_is_reachable_by_walking_the_pages(findings, world):
    seen: list[str] = []
    page = 1
    while True:
        payload = findings(version_id=str(world["first"].id), page=page, page_size=25)
        seen.extend(item["id"] for item in payload["items"])
        if page * 25 >= payload["total"]:
            break
        page += 1
    assert len(seen) == world["metadata_cards"] + world["interference_cards"]
    assert len(set(seen)) == len(seen), "a card appeared on two pages"


def test_a_page_past_the_end_is_empty_rather_than_an_error(findings, world):
    payload = findings(version_id=str(world["first"].id), page=99, page_size=25)
    assert payload["items"] == []
    assert payload["total"] > 0


def test_the_page_size_is_capped(client, world):
    response = client.get(
        f"/api/v1/projects/{world['project'].id}/ifc/findings",
        headers=_auth(client, world["manager"]), params={"page_size": 5000},
    )
    assert response.status_code == 422


# --- scoping and filters ----------------------------------------------------


def test_the_version_filter_is_what_bounds_the_query(findings, world):
    everything = findings()
    one = findings(version_id=str(world["first"].id))
    assert everything["total"] > one["total"]
    assert {item["versionId"] for item in one["items"]} == {str(world["first"].id)}


def test_severity_is_matched_on_the_server(findings, world):
    payload = findings(version_id=str(world["first"].id), severity="CRITICAL", page_size=200)
    assert payload["total"] == 1
    assert {item["severity"] for item in payload["items"]} == {"CRITICAL"}


def test_a_severity_filter_narrows_the_total_not_only_the_page(findings, world):
    # The property that a browser-side filter could not provide: `total` has to
    # describe the filtered result, or the pager counts pages that do not exist.
    high = findings(version_id=str(world["first"].id), severity="HIGH", page_size=5)
    assert high["total"] == 10
    assert len(high["items"]) == 5
    assert all(item["severity"] == "HIGH" for item in high["items"])


def test_discipline_is_matched_on_the_server(findings, world):
    payload = findings(version_id=str(world["first"].id), discipline="MECHANICAL", page_size=200)
    assert payload["total"] == 1
    assert all("MECHANICAL" in item["disciplines"] for item in payload["items"])


def test_filters_combine(findings, world):
    payload = findings(
        version_id=str(world["first"].id), severity="HIGH", discipline="PLUMBING", page_size=200,
    )
    assert payload["total"] == 10
    payload = findings(
        version_id=str(world["first"].id), severity="HIGH", discipline="ARCHITECTURAL", page_size=200,
    )
    assert payload["total"] == 0


def test_the_status_filter_still_works(findings, world):
    assert findings(version_id=str(world["first"].id), status="RESOLVED")["total"] == 0
    assert findings(version_id=str(world["first"].id), status="PENDING")["total"] > 0


# --- ordering ---------------------------------------------------------------


def test_the_worst_findings_are_on_the_first_page(findings, world):
    """Ordering has to happen before the cut, or page one is an arbitrary
    slice and a reviewer working top-down sees the wrong things first."""
    first_page = findings(version_id=str(world["first"].id), page=1, page_size=5)
    severities = [item["severity"] for item in first_page["items"]]
    assert severities[0] == "CRITICAL"
    assert severities[1:] == ["HIGH"] * 4


def test_the_order_is_stable_across_identical_requests(findings, world):
    one = findings(version_id=str(world["first"].id), page_size=20)
    two = findings(version_id=str(world["first"].id), page_size=20)
    assert [item["id"] for item in one["items"]] == [item["id"] for item in two["items"]]


def test_grouping_survives_pagination(findings, world):
    """A metadata rule is one card built from several rows. Paging must cut
    between cards, never inside one: three rows of MISSING_MATERIAL are still
    a single entry carrying all of their elements."""
    payload = findings(version_id=str(world["first"].id), severity="MEDIUM", page_size=200)
    types = [item["findingType"] for item in payload["items"]]
    assert types.count("MISSING_MATERIAL") == 1
    material = next(item for item in payload["items"] if item["findingType"] == "MISSING_MATERIAL")
    assert material["affectedElementCount"] >= 1
