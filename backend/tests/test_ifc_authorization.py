"""The IFC HTTP surface, with authorization as the whole subject.

The IFC engine tests are thorough about geometry, parsing and detection, and
say nothing about who is allowed to ask. That gap mattered: `app/api/ifc.py`
carries fifty-five routes, eight permission verbs and a project filter on every
lookup, and none of it was exercised through a request. A missing `_require` on
a new route, or a `_version()` call that forgot its `project_id`, would have
shipped silently.

Everything here goes through `TestClient` rather than calling handlers, for the
reason `tests/test_rag_api.py` gives: calling a handler directly bypasses
`Depends(get_current_user)` and would make an unprotected route look protected.

Two properties are asserted throughout.

**A route is gated on exactly the code it claims.** Rather than pinning the
seeded role defaults — which an office is meant to reconfigure — the matrix
tests revoke one permission from an otherwise-authorized person and require the
route to close. That proves the mapping in `ifc_policy.IFC_VERB_PERMISSION` is
the thing actually being enforced, and it keeps passing when the defaults move.

**Project scoping is enforced server-side, not by the caller's honesty.** The
isolation tests come at a second project's data from both directions: with the
victim's `project_id` (refused as 403 by the permission layer, which checks
project access) and with the attacker's own `project_id` and the victim's
resource id (refused as 404 by the query filter). Both are checked because they
fail in different places and either could regress alone.

Nothing here writes to the shared development database beyond its own uniquely
suffixed rows, which the fixture removes.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.ifc import (
    IFCCoordinationFinding, IFCElement, IFCEntityLink, IFCModelGroup,
    IFCModelVersion, IFCSpatialNode, IFCSuggestion,
)
from app.models.issue import Issue
from app.models.notification import Notification
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.rbac import ProjectParty
from app.models.user import User
from app.services import rbac
from app.services.private_storage import private_storage

PASSWORD = "Correct#12345"
IFC_FIXTURE = Path(__file__).parent / "fixtures" / "minimal_ifc4.ifc"


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
    """Two projects in one office, and six people with different reach.

    The subjects are chosen so that every refusal this suite asserts has a
    *different* cause, and no test can pass for the wrong reason:

      * `manager`   — runs project A, holds every IFC verb
      * `bim`       — BIM Engineer on A; the only other role that may upload,
                      because `ifc.upload` below version-management level is
                      still behind `IFC_ENGINEER_UPLOAD_ENABLED`
      * `engineer`  — on A, holds everything except `ifc.manage_version`
      * `client_rep`— the client, external; holds `ifc.view` and nothing else
      * `staff`     — office staff on A; a member with no IFC permission at all
      * `outsider`  — runs project B with the same role as `manager`, so any
                      refusal on A is about the project and not about authority
    """
    suffix = uuid.uuid4().hex[:10]
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    office = Company(name=f"IFC Auth Office {suffix}", kind="CONSULTING_OFFICE", is_active=True)
    db.add(office)
    db.flush()

    def user(name, role_code, legacy=UserRole.ENGINEER, status=UserStatus.ACTIVE):
        role = roles[role_code]
        person = User(
            full_name=f"{name}{suffix}", email=f"{name.lower()}.{suffix}@constro.io",
            hashed_password=hash_password(PASSWORD), role=legacy, status=status,
            company_id=office.id, org_role_id=role.id, is_internal=role.is_internal_only,
        )
        db.add(person)
        db.flush()
        return person

    manager = user("Manager", "project_manager", UserRole.PROJECT_MANAGER)
    bim = user("Bim", "bim_engineer")
    engineer = user("Engineer", "engineer")
    client_rep = user("ClientRep", "client_representative", UserRole.OWNER)
    staff = user("Staff", "office_staff")
    outsider = user("Outsider", "project_manager", UserRole.PROJECT_MANAGER)

    def project(name, pm):
        item = Project(
            name=f"{name} {suffix}", status=ProjectStatus.ACTIVE,
            company_id=office.id, project_manager_id=pm.id,
        )
        db.add(item)
        db.flush()
        return item

    project_a = project("IFC Alpha", manager)
    project_b = project("IFC Beta", outsider)

    client_party = ProjectParty(
        project_id=project_a.id, kind="CLIENT", display_name=f"Client {suffix}",
    )
    db.add(client_party)
    db.flush()

    def member(person, project_item, role_code, party=None):
        row = ProjectMember(
            project_id=project_item.id, user_id=person.id, role_on_project=person.role,
            project_role_id=roles[role_code].id, is_active=True,
            party_id=party.id if party else None,
        )
        db.add(row)
        db.flush()
        return row

    member(manager, project_a, "project_manager")
    member(bim, project_a, "bim_engineer")
    member(engineer, project_a, "engineer")
    member(staff, project_a, "office_staff")
    member(client_rep, project_a, "client_representative", client_party)
    member(outsider, project_b, "project_manager")

    def model_and_version(project_item, label, author, *, store_file):
        group = IFCModelGroup(
            project_id=project_item.id, name=f"{label} model {suffix}",
            discipline="ARCHITECTURAL", created_by_id=author.id,
        )
        db.add(group)
        db.flush()
        storage_key = f"ifc/{uuid.uuid4()}_{label.lower()}_{suffix}.ifc"
        if store_file:
            # A real file on disk: `download_version` answers 404 when the
            # stored object is missing, which would hide the permission result
            # the download tests are actually about.
            with private_storage.writable_local_path(storage_key) as target:
                target.write_bytes(IFC_FIXTURE.read_bytes())
        version = IFCModelVersion(
            model_group_id=group.id, project_id=project_item.id, version_number=1,
            revision_code="P01", version_type="DESIGN", title=f"{label} revision {suffix}",
            original_filename=f"{label.lower()}.ifc", storage_key=storage_key,
            file_hash=uuid.uuid4().hex + uuid.uuid4().hex, file_size=1024,
            ifc_schema="IFC4", uploaded_by_id=author.id, processing_status="READY",
            processing_progress=100, entity_count=1, is_active=True,
            model_summary_json={"elements": 1},
        )
        db.add(version)
        db.flush()
        node = IFCSpatialNode(
            version_id=version.id, global_id=f"S{uuid.uuid4().hex[:20]}",
            entity_type="IfcBuildingStorey", name=f"{label} Level 01", node_type="STOREY",
            metadata_json={"stepId": 101},
        )
        db.add(node)
        db.flush()
        element = IFCElement(
            version_id=version.id, global_id=f"E{uuid.uuid4().hex[:20]}",
            entity_type="IfcWall", name=f"{label} wall", storey_node_id=node.id,
            discipline="ARCHITECTURAL", properties_json={}, quantities_json={},
            metadata_json={"stepId": 202},
        )
        db.add(element)
        db.flush()
        finding = IFCCoordinationFinding(
            project_id=project_item.id, version_id=version.id, element_a_id=element.id,
            finding_type="MISSING_MATERIAL", severity="MEDIUM", confidence=1.0,
            title=f"{label} materials are missing",
            description="Material data is not defined for some extracted elements.",
            geometry_evidence_json={"rule": "IFC_MATERIAL", "elementIds": [str(element.id)]},
            affected_disciplines_json=["ARCHITECTURAL"], status="PENDING",
        )
        suggestion = IFCSuggestion(
            project_id=project_item.id, version_id=version.id,
            suggestion_type="CREATE_TASK",
            payload_json={"title": f"{label} wall installation", "discipline": "ARCHITECTURAL"},
            confidence=0.8, reasoning="Derived from extracted elements.", status="PENDING",
        )
        link = IFCEntityLink(
            project_id=project_item.id, version_id=version.id, ifc_element_id=element.id,
            linked_entity_type="ISSUE", linked_entity_id=uuid.uuid4(),
            link_type="RELATED", source="USER", confidence=1.0,
        )
        db.add_all([finding, suggestion, link])
        db.flush()
        return {
            "group": group, "version": version, "node": node, "element": element,
            "finding": finding, "suggestion": suggestion, "link": link,
        }

    alpha = model_and_version(project_a, "Alpha", manager, store_file=True)
    beta = model_and_version(project_b, "Beta", outsider, store_file=True)

    # A second revision of Alpha's own group, so `ifc.compare` can be exercised
    # for real rather than skipped: a comparison needs two processed versions
    # from the same model group.
    alpha_second = IFCModelVersion(
        model_group_id=alpha["group"].id, project_id=project_a.id, version_number=2,
        revision_code="P02", version_type="DESIGN", title=f"Alpha revision 2 {suffix}",
        original_filename="alpha2.ifc", storage_key=f"ifc/{uuid.uuid4()}_alpha2_{suffix}.ifc",
        file_hash=uuid.uuid4().hex + uuid.uuid4().hex, file_size=1024,
        ifc_schema="IFC4", uploaded_by_id=manager.id, processing_status="READY",
        processing_progress=100, entity_count=0, model_summary_json={"elements": 0},
    )
    db.add(alpha_second)
    db.flush()
    alpha["second_version"] = alpha_second

    created = {
        "suffix": suffix, "office": office, "roles": roles,
        "manager": manager, "bim": bim, "engineer": engineer,
        "client_rep": client_rep, "staff": staff, "outsider": outsider,
        "project_a": project_a, "project_b": project_b,
        "a": alpha, "b": beta,
    }
    db.commit()

    try:
        yield created
    finally:
        db.rollback()
        project_ids = [project_a.id, project_b.id]
        user_ids = [manager.id, bim.id, engineer.id, client_rep.id, staff.id, outsider.id]
        # Stored objects first: the rows that name them are about to go, and a
        # test may have uploaded another version of its own.
        for key, geometry_key in db.query(
            IFCModelVersion.storage_key, IFCModelVersion.geometry_storage_key
        ).filter(IFCModelVersion.project_id.in_(project_ids)).all():
            private_storage.delete(key)
            if geometry_key:
                private_storage.delete(geometry_key)
        for model, column in (
            (UserPermissionOverride, UserPermissionOverride.user_id.in_(user_ids)),
            (AuditLog, AuditLog.project_id.in_(project_ids)),
            (IFCEntityLink, IFCEntityLink.project_id.in_(project_ids)),
            (IFCCoordinationFinding, IFCCoordinationFinding.project_id.in_(project_ids)),
            (IFCSuggestion, IFCSuggestion.project_id.in_(project_ids)),
            (Issue, Issue.project_id.in_(project_ids)),
            (Notification, Notification.project_id.in_(project_ids)),
            # Comparisons, change records and impacts cascade from the version
            # rows; the versions must go before the users, because a
            # comparison's `created_by_id` is RESTRICT.
            (IFCModelVersion, IFCModelVersion.project_id.in_(project_ids)),
            (IFCModelGroup, IFCModelGroup.project_id.in_(project_ids)),
            (ProjectMember, ProjectMember.project_id.in_(project_ids)),
            (ProjectParty, ProjectParty.project_id.in_(project_ids)),
            (Project, Project.id.in_(project_ids)),
            (User, User.id.in_(user_ids)),
            (Company, Company.id == office.id),
        ):
            db.query(model).filter(column).delete(synchronize_session=False)
        db.commit()


def _auth(client, user) -> dict:
    login = client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def ifc_url(project_id, suffix: str = "") -> str:
    return f"/api/v1/projects/{project_id}/ifc{suffix}"


def _upload_files():
    return {"file": ("model.ifc", IFC_FIXTURE.read_bytes(), "application/x-step")}


@pytest.fixture()
def no_background_processing(monkeypatch):
    """Accept the upload, skip the parse.

    A successful upload queues `_background_process`, which `TestClient` runs
    for real once the response is returned. That is the parsing pipeline's
    subject, covered by `test_ifc_interference_pipeline.py`; here it would only
    add a minute and a pile of rows to a test about who may post the file.
    """
    calls: list = []
    monkeypatch.setattr(
        "app.api.ifc._background_process",
        lambda version_id, actor_id: calls.append((version_id, actor_id)),
    )
    return calls


# --- authentication ---------------------------------------------------------


def _representative_routes(world) -> list[tuple[str, str, dict | None]]:
    """One route per shape of the IFC surface: collection, resource, action."""
    project = world["project_a"].id
    alpha = world["a"]
    return [
        ("get", ifc_url(project, "/upload-constraints"), None),
        ("get", ifc_url(project, "/models"), None),
        ("post", ifc_url(project, "/models"), {"name": "Anonymous model"}),
        ("get", ifc_url(project, f"/models/{alpha['group'].id}"), None),
        ("get", ifc_url(project, f"/models/{alpha['group'].id}/versions"), None),
        ("get", ifc_url(project, f"/versions/{alpha['version'].id}"), None),
        ("get", ifc_url(project, f"/versions/{alpha['version'].id}/download"), None),
        ("get", ifc_url(project, f"/versions/{alpha['version'].id}/hierarchy"), None),
        ("get", ifc_url(project, f"/versions/{alpha['version'].id}/elements"), None),
        ("get", ifc_url(project, f"/versions/{alpha['version'].id}/overview"), None),
        ("get", ifc_url(project, f"/versions/{alpha['version'].id}/geometry/status"), None),
        ("post", ifc_url(project, f"/versions/{alpha['version'].id}/geometry/generate"), None),
        ("get", ifc_url(project, f"/spatial/{alpha['node'].id}/details"), None),
        ("get", ifc_url(project, f"/elements/{alpha['element'].id}/project-data"), None),
        ("get", ifc_url(project, "/findings"), None),
        ("get", ifc_url(project, f"/findings/{alpha['finding'].id}"), None),
        ("patch", ifc_url(project, f"/findings/{alpha['finding'].id}"), {"status": "IGNORED"}),
        ("post", ifc_url(project, f"/findings/{alpha['finding'].id}/ignore"), None),
        ("post", ifc_url(project, f"/findings/{alpha['finding'].id}/create-issue"), None),
        ("get", ifc_url(project, "/suggestions"), None),
        ("patch", ifc_url(project, f"/suggestions/{alpha['suggestion'].id}"), {"status": "REJECTED"}),
        ("get", ifc_url(project, "/comparisons"), None),
        ("get", ifc_url(project, "/links"), None),
        ("delete", ifc_url(project, f"/links/{alpha['link'].id}"), None),
        ("get", ifc_url(project, "/processing-jobs"), None),
    ]


def test_every_ifc_route_refuses_an_anonymous_caller(client, world):
    for method, path, body in _representative_routes(world):
        response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
        assert response.status_code == 401, f"{method.upper()} {path} → {response.status_code}"


def test_a_garbage_bearer_token_is_not_accepted(client, world):
    response = client.get(
        ifc_url(world["project_a"].id, "/models"),
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_suspending_an_account_closes_ifc_for_the_token_it_already_holds(
    client, db, world
):
    """Suspension has to bite mid-session, not only at the next login.

    The token is taken while the account is still active and then reused, which
    is the case that matters: refusing a *new* login proves nothing about the
    credential somebody is already carrying. `get_current_user` re-reads the
    status on every request, and `can_ifc` checks it again.
    """
    manager, path = world["manager"], ifc_url(world["project_a"].id, "/models")
    headers = _auth(client, manager)
    assert client.get(path, headers=headers).status_code == 200

    db.query(User).filter(User.id == manager.id).update(
        {"status": UserStatus.SUSPENDED}, synchronize_session=False
    )
    db.commit()

    assert client.get(path, headers=headers).status_code == 403
    # And the credential cannot be renewed either.
    login = client.post(
        "/api/v1/auth/login", data={"username": manager.email, "password": PASSWORD}
    )
    assert login.status_code in (401, 403)


# --- the permission matrix --------------------------------------------------
#
# Each row is (permission code, HTTP method, path builder, body). The code is
# the one `ifc_policy.IFC_VERB_PERMISSION` maps the route's verb to.

MATRIX = [
    ("ifc.view", "get", lambda w: ifc_url(w["project_a"].id, "/models"), None),
    ("ifc.view", "get", lambda w: ifc_url(w["project_a"].id, f"/versions/{w['a']['version'].id}"), None),
    ("ifc.view", "get", lambda w: ifc_url(w["project_a"].id, "/findings"), None),
    ("ifc.view", "get", lambda w: ifc_url(w["project_a"].id, f"/versions/{w['a']['version'].id}/elements"), None),
    ("ifc.view", "get", lambda w: ifc_url(w["project_a"].id, f"/spatial/{w['a']['node'].id}/details"), None),
    ("ifc.download", "get", lambda w: ifc_url(w["project_a"].id, f"/versions/{w['a']['version'].id}/download"), None),
    ("ifc.upload", "post", lambda w: ifc_url(w["project_a"].id, "/models"), {"name": "New group"}),
    ("ifc.manage_version", "patch", lambda w: ifc_url(w["project_a"].id, f"/models/{w['a']['group'].id}"), {"description": "renamed"}),
    ("ifc.manage_version", "post", lambda w: ifc_url(w["project_a"].id, f"/versions/{w['a']['version'].id}/activate"), None),
    ("ifc.review_finding", "patch", lambda w: ifc_url(w["project_a"].id, f"/findings/{w['a']['finding'].id}"), {"status": "IGNORED"}),
    ("ifc.review_finding", "post", lambda w: ifc_url(w["project_a"].id, f"/findings/{w['a']['finding'].id}/mark-false-positive"), None),
    ("ifc.review_suggestion", "patch", lambda w: ifc_url(w["project_a"].id, f"/suggestions/{w['a']['suggestion'].id}"), {"status": "REJECTED"}),
    ("ifc.manage_link", "delete", lambda w: ifc_url(w["project_a"].id, f"/links/{w['a']['link'].id}"), None),
    # Listing comparisons is `ifc.view`; only *building* one is `ifc.compare`.
    ("ifc.view", "get", lambda w: ifc_url(w["project_a"].id, "/comparisons"), None),
    ("ifc.compare", "post", lambda w: ifc_url(w["project_a"].id, "/comparisons"), "COMPARE_BODY"),
]


def _body_for(world, body):
    """`COMPARE_BODY` needs ids the matrix table cannot see when it is built."""
    if body == "COMPARE_BODY":
        return {
            "baseVersionId": str(world["a"]["version"].id),
            "targetVersionId": str(world["a"]["second_version"].id),
        }
    return body


def _send(client, method, path, headers, body):
    if method in {"get", "delete"}:
        return getattr(client, method)(path, headers=headers)
    return getattr(client, method)(path, headers=headers, json=body)


@pytest.mark.parametrize(
    "code, method, path_of, body", MATRIX,
    ids=[f"{code}-{method}" for code, method, _, _ in MATRIX],
)
def test_the_route_closes_when_its_own_permission_is_revoked(
    client, db, world, code, method, path_of, body
):
    """The route is gated on exactly the code `IFC_VERB_PERMISSION` names.

    Revoking one code from somebody who otherwise holds everything is a
    sharper instrument than picking a role that happens to lack it: it cannot
    pass because of an unrelated restriction, and it keeps testing the same
    property when an office reconfigures its role defaults.
    """
    manager, path, body = world["manager"], path_of(world), _body_for(world, body)

    db.add(UserPermissionOverride(
        user_id=manager.id, project_id=world["project_a"].id,
        permission_code=code, allowed=False,
    ))
    db.commit()

    response = _send(client, method, path, _auth(client, manager), body)
    assert response.status_code == 403, f"{method.upper()} {path} → {response.status_code}"


@pytest.mark.parametrize(
    "code, method, path_of, body", MATRIX,
    ids=[f"{code}-{method}" for code, method, _, _ in MATRIX],
)
def test_the_same_route_is_open_to_somebody_holding_the_permission(
    client, world, code, method, path_of, body
):
    """The other half of the matrix: without the revoke, the route answers.

    Without this the revoke test above would pass just as well against a route
    that is broken for everybody.
    """
    response = _send(
        client, method, path_of(world), _auth(client, world["manager"]), _body_for(world, body)
    )
    assert response.status_code < 400, f"{method.upper()} → {response.status_code}: {response.text[:200]}"


def test_a_project_member_with_no_ifc_permission_is_refused_read_access(client, world):
    # Office staff are on the project and hold no IFC code at all. Project
    # membership must not be mistaken for IFC access.
    response = client.get(
        ifc_url(world["project_a"].id, "/models"), headers=_auth(client, world["staff"])
    )
    assert response.status_code == 403


def test_the_client_may_read_the_model_but_not_download_or_review_it(client, world):
    """The external client's real reach, as the seeded role defines it."""
    headers = _auth(client, world["client_rep"])
    project, alpha = world["project_a"].id, world["a"]

    assert client.get(ifc_url(project, "/models"), headers=headers).status_code == 200
    assert client.get(ifc_url(project, "/findings"), headers=headers).status_code == 200

    for method, path, body in (
        ("get", ifc_url(project, f"/versions/{alpha['version'].id}/download"), None),
        ("post", ifc_url(project, "/models"), {"name": "Client model"}),
        ("patch", ifc_url(project, f"/findings/{alpha['finding'].id}"), {"status": "IGNORED"}),
        ("patch", ifc_url(project, f"/suggestions/{alpha['suggestion'].id}"), {"status": "REJECTED"}),
    ):
        response = _send(client, method, path, headers, body)
        assert response.status_code == 403, f"{method.upper()} {path} → {response.status_code}"


def test_creating_an_issue_from_a_finding_needs_more_than_the_ifc_verb(client, db, world):
    """`finding_to_issue` checks `issue.create` on top of `ifc.review_finding`.

    Revoking only the non-IFC half proves the second check is reached rather
    than being decorative — the IFC verb alone must not be enough.
    """
    manager = world["manager"]
    db.add(UserPermissionOverride(
        user_id=manager.id, project_id=world["project_a"].id,
        permission_code="issue.create", allowed=False,
    ))
    db.commit()
    response = client.post(
        ifc_url(world["project_a"].id, f"/findings/{world['a']['finding'].id}/create-issue"),
        headers=_auth(client, manager),
    )
    assert response.status_code == 403


# --- upload -----------------------------------------------------------------


def test_upload_is_refused_without_the_upload_permission(client, world):
    response = client.post(
        ifc_url(world["project_a"].id, f"/models/{world['a']['group'].id}/versions"),
        headers=_auth(client, world["client_rep"]),
        files=_upload_files(), data={"title": "Client upload"},
    )
    assert response.status_code == 403


def test_upload_below_version_management_stays_behind_its_rollout_flag(client, world):
    """`can_ifc` gates `UPLOAD` on `IFC_ENGINEER_UPLOAD_ENABLED` for anybody who
    does not also hold `ifc.manage_version`. The Engineer role holds
    `ifc.upload` and not `ifc.manage_version`, so the flag decides."""
    assert settings.IFC_ENGINEER_UPLOAD_ENABLED is False
    response = client.post(
        ifc_url(world["project_a"].id, f"/models/{world['a']['group'].id}/versions"),
        headers=_auth(client, world["engineer"]),
        files=_upload_files(), data={"title": "Engineer upload"},
    )
    assert response.status_code == 403


def test_the_same_engineer_may_upload_once_the_flag_is_on(
    client, world, monkeypatch, no_background_processing
):
    monkeypatch.setattr(settings, "IFC_ENGINEER_UPLOAD_ENABLED", True)
    response = client.post(
        ifc_url(world["project_a"].id, f"/models/{world['a']['group'].id}/versions"),
        headers=_auth(client, world["engineer"]),
        files=_upload_files(), data={"title": "Engineer upload"},
    )
    assert response.status_code == 202, response.text
    assert len(no_background_processing) == 1


def test_a_bim_engineer_may_upload_without_the_flag(client, world, no_background_processing):
    # Holding `ifc.manage_version` is what takes the flag out of the decision.
    response = client.post(
        ifc_url(world["project_a"].id, f"/models/{world['a']['group'].id}/versions"),
        headers=_auth(client, world["bim"]),
        files=_upload_files(), data={"title": "BIM upload"},
    )
    assert response.status_code == 202, response.text


def test_upload_into_another_projects_model_group_is_refused(client, world):
    """The group belongs to B; the path says A. `_group` filters on both."""
    response = client.post(
        ifc_url(world["project_a"].id, f"/models/{world['b']['group'].id}/versions"),
        headers=_auth(client, world["manager"]),
        files=_upload_files(), data={"title": "Cross-project upload"},
    )
    assert response.status_code == 404


# --- project isolation ------------------------------------------------------


def test_an_outsider_holding_every_ifc_permission_is_refused_another_project(client, world):
    """The whole surface, from somebody whose authority is real but elsewhere.

    `outsider` runs project B under the same role as `manager` runs A, so a
    200 here could only mean the project half of the check is missing.
    """
    headers = _auth(client, world["outsider"])
    for method, path, body in _representative_routes(world):
        response = _send(client, method, path, headers, body)
        assert response.status_code == 403, f"{method.upper()} {path} → {response.status_code}"


@pytest.mark.parametrize("path_suffix", [
    "/versions/{version}",
    "/versions/{version}/download",
    "/versions/{version}/hierarchy",
    "/versions/{version}/elements",
    "/versions/{version}/overview",
    "/versions/{version}/geometry/status",
    "/versions/{version}/geometry/mapping",
    "/versions/{version}/project-data",
    "/versions/{version}/storeys",
    "/versions/{version}/spaces",
])
def test_another_projects_version_is_invisible_under_your_own_project_id(
    client, world, path_suffix
):
    """The second attack shape: attacker's project, victim's resource id.

    The permission layer cannot refuse this — the caller really does have
    access to the project in the path — so the only thing standing between the
    two projects is the `project_id` filter inside each lookup.
    """
    path = ifc_url(
        world["project_b"].id, path_suffix.format(version=world["a"]["version"].id)
    )
    response = client.get(path, headers=_auth(client, world["outsider"]))
    assert response.status_code == 404, f"{path} → {response.status_code}"
    assert world["a"]["version"].title not in response.text


@pytest.mark.parametrize("path_suffix, method, body", [
    ("/models/{group}", "get", None),
    ("/models/{group}", "patch", {"description": "renamed"}),
    ("/models/{group}/versions", "get", None),
    ("/models/{group}", "delete", None),
])
def test_another_projects_model_group_is_invisible_under_your_own_project_id(
    client, world, path_suffix, method, body
):
    path = ifc_url(world["project_b"].id, path_suffix.format(group=world["a"]["group"].id))
    response = _send(client, method, path, _auth(client, world["outsider"]), body)
    assert response.status_code == 404
    assert world["a"]["group"].name not in response.text


@pytest.mark.parametrize("path_suffix, method, body", [
    ("/findings/{finding}", "get", None),
    ("/findings/{finding}", "patch", {"status": "IGNORED"}),
    ("/findings/{finding}/ignore", "post", None),
    ("/findings/{finding}/mark-false-positive", "post", None),
    ("/findings/{finding}/create-issue", "post", None),
])
def test_another_projects_finding_cannot_be_read_or_reviewed(
    client, world, path_suffix, method, body
):
    path = ifc_url(world["project_b"].id, path_suffix.format(finding=world["a"]["finding"].id))
    response = _send(client, method, path, _auth(client, world["outsider"]), body)
    assert response.status_code == 404
    assert world["a"]["finding"].title not in response.text


def test_reviewing_across_projects_leaves_the_finding_untouched(client, db, world):
    """A 404 must also mean nothing happened, not merely that nothing was shown."""
    finding = world["a"]["finding"]
    assert finding.status == "PENDING"
    client.post(
        ifc_url(world["project_b"].id, f"/findings/{finding.id}/ignore"),
        headers=_auth(client, world["outsider"]),
    )
    db.expire_all()
    assert db.get(IFCCoordinationFinding, finding.id).status == "PENDING"


@pytest.mark.parametrize("path_suffix, method, body", [
    ("/suggestions/{suggestion}", "patch", {"status": "REJECTED"}),
    ("/suggestions/{suggestion}/accept", "post", None),
    ("/suggestions/{suggestion}/reject", "post", None),
])
def test_another_projects_suggestion_cannot_be_reviewed(
    client, world, path_suffix, method, body
):
    path = ifc_url(
        world["project_b"].id, path_suffix.format(suggestion=world["a"]["suggestion"].id)
    )
    response = _send(client, method, path, _auth(client, world["outsider"]), body)
    assert response.status_code == 404


def test_another_projects_spatial_node_and_element_are_invisible(client, world):
    headers = _auth(client, world["outsider"])
    project_b = world["project_b"].id
    for path in (
        ifc_url(project_b, f"/spatial/{world['a']['node'].id}/details"),
        ifc_url(project_b, f"/spatial/{world['a']['node'].id}/project-data"),
        ifc_url(project_b, f"/storeys/{world['a']['node'].id}/project-data"),
        ifc_url(project_b, f"/elements/{world['a']['element'].id}/project-data"),
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 404, f"{path} → {response.status_code}"
        assert world["a"]["element"].name not in response.text


def test_an_element_is_not_readable_through_another_versions_path(client, world):
    """`element_detail` scopes to the version, not only to the project."""
    response = client.get(
        ifc_url(
            world["project_b"].id,
            f"/versions/{world['b']['version'].id}/elements/{world['a']['element'].id}",
        ),
        headers=_auth(client, world["outsider"]),
    )
    assert response.status_code == 404


def test_another_projects_link_cannot_be_deleted(client, db, world):
    link_id = world["a"]["link"].id
    response = client.delete(
        ifc_url(world["project_b"].id, f"/links/{link_id}"),
        headers=_auth(client, world["outsider"]),
    )
    assert response.status_code == 404
    db.expire_all()
    assert db.get(IFCEntityLink, link_id) is not None


def test_the_listing_endpoints_never_return_another_projects_rows(client, world):
    """Scoping on the collections, not only on the resource lookups."""
    headers = _auth(client, world["outsider"])
    project_b = world["project_b"].id

    models = client.get(ifc_url(project_b, "/models"), headers=headers).json()
    assert [item["id"] for item in models] == [str(world["b"]["group"].id)]

    # Paged since the collection could grow without bound; the scoping claim is
    # unchanged — nothing from the other project may appear on any page.
    findings = client.get(ifc_url(project_b, "/findings"), headers=headers).json()
    assert {item["versionId"] for item in findings["items"]} == {str(world["b"]["version"].id)}
    assert findings["total"] == len(findings["items"])

    suggestions = client.get(ifc_url(project_b, "/suggestions"), headers=headers).json()
    assert {item["versionId"] for item in suggestions} == {str(world["b"]["version"].id)}

    links = client.get(ifc_url(project_b, "/links"), headers=headers).json()
    assert {item["projectId"] for item in links} == {str(project_b)}

    jobs = client.get(ifc_url(project_b, "/processing-jobs"), headers=headers).json()
    assert isinstance(jobs, list)


def test_a_comparison_cannot_be_built_across_two_projects(client, world):
    """Both versions must belong to the caller's project *and* the same group."""
    response = client.post(
        ifc_url(world["project_a"].id, "/comparisons"),
        headers=_auth(client, world["manager"]),
        json={
            "baseVersionId": str(world["a"]["version"].id),
            "targetVersionId": str(world["b"]["version"].id),
        },
    )
    assert response.status_code == 404


@pytest.fixture()
def comparison(client, world):
    """A real comparison between Alpha's two revisions, for the sub-resources."""
    response = client.post(
        ifc_url(world["project_a"].id, "/comparisons"),
        headers=_auth(client, world["manager"]),
        json={
            "baseVersionId": str(world["a"]["version"].id),
            "targetVersionId": str(world["a"]["second_version"].id),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_the_comparison_sub_resources_are_gated_and_project_scoped(
    client, world, comparison
):
    """`changes` and `impacts` borrow `comparison_detail`'s check rather than
    calling `_require` themselves, so they need their own proof."""
    comparison_id = comparison["id"]
    for suffix in (f"/comparisons/{comparison_id}",
                   f"/comparisons/{comparison_id}/changes",
                   f"/comparisons/{comparison_id}/impacts"):
        assert client.get(
            ifc_url(world["project_a"].id, suffix), headers=_auth(client, world["manager"])
        ).status_code == 200, suffix

        # Somebody with full IFC authority on another project must not reach it
        # by either route: their own project id, or the owning one.
        assert client.get(
            ifc_url(world["project_b"].id, suffix), headers=_auth(client, world["outsider"])
        ).status_code == 404, suffix
        assert client.get(
            ifc_url(world["project_a"].id, suffix), headers=_auth(client, world["outsider"])
        ).status_code == 403, suffix

        assert client.get(ifc_url(world["project_a"].id, suffix)).status_code == 401, suffix


def test_re_running_impact_analysis_needs_the_compare_permission(
    client, db, world, comparison
):
    manager = world["manager"]
    path = ifc_url(world["project_a"].id, f"/comparisons/{comparison['id']}/analyze-impact")
    assert client.post(path, headers=_auth(client, manager)).status_code == 200

    db.add(UserPermissionOverride(
        user_id=manager.id, project_id=world["project_a"].id,
        permission_code="ifc.compare", allowed=False,
    ))
    db.commit()
    assert client.post(path, headers=_auth(client, manager)).status_code == 403


def test_an_unknown_project_id_is_refused_rather_than_answered(client, world):
    response = client.get(
        ifc_url(uuid.uuid4(), "/models"), headers=_auth(client, world["manager"])
    )
    assert response.status_code == 403


# --- download ---------------------------------------------------------------


def test_an_authorized_caller_downloads_the_stored_file(client, world):
    response = client.get(
        ifc_url(world["project_a"].id, f"/versions/{world['a']['version'].id}/download"),
        headers=_auth(client, world["manager"]),
    )
    assert response.status_code == 200
    assert response.content == IFC_FIXTURE.read_bytes()
    assert world["a"]["version"].original_filename in response.headers["content-disposition"]


def test_a_successful_download_is_written_to_the_audit_trail(client, db, world):
    version = world["a"]["version"]
    before = db.query(AuditLog).filter(
        AuditLog.action == "ifc_version_downloaded", AuditLog.entity_id == version.id
    ).count()

    assert client.get(
        ifc_url(world["project_a"].id, f"/versions/{version.id}/download"),
        headers=_auth(client, world["manager"]),
    ).status_code == 200

    rows = db.query(AuditLog).filter(
        AuditLog.action == "ifc_version_downloaded", AuditLog.entity_id == version.id
    ).all()
    assert len(rows) == before + 1
    assert rows[-1].actor_id == world["manager"].id
    assert rows[-1].project_id == world["project_a"].id


def test_a_refused_download_writes_no_audit_row(client, db, world):
    """The audit trail must record downloads, not attempts to download."""
    version = world["a"]["version"]
    before = db.query(AuditLog).filter(
        AuditLog.action == "ifc_version_downloaded", AuditLog.entity_id == version.id
    ).count()

    assert client.get(
        ifc_url(world["project_a"].id, f"/versions/{version.id}/download"),
        headers=_auth(client, world["client_rep"]),
    ).status_code == 403

    after = db.query(AuditLog).filter(
        AuditLog.action == "ifc_version_downloaded", AuditLog.entity_id == version.id
    ).count()
    assert after == before


def test_download_is_refused_to_a_member_of_a_different_project(client, world):
    """Both directions: the victim's project id, and the attacker's own."""
    headers = _auth(client, world["outsider"])
    version = world["a"]["version"]

    denied = client.get(
        ifc_url(world["project_a"].id, f"/versions/{version.id}/download"), headers=headers
    )
    assert denied.status_code == 403

    not_found = client.get(
        ifc_url(world["project_b"].id, f"/versions/{version.id}/download"), headers=headers
    )
    assert not_found.status_code == 404
    assert not_found.content != IFC_FIXTURE.read_bytes()


def test_download_needs_its_own_permission_not_merely_view(client, db, world):
    """`ifc.download` is a separate code, not an alias for `ifc.view`."""
    manager = world["manager"]
    db.add(UserPermissionOverride(
        user_id=manager.id, project_id=world["project_a"].id,
        permission_code="ifc.download", allowed=False,
    ))
    db.commit()
    headers = _auth(client, manager)

    assert client.get(
        ifc_url(world["project_a"].id, f"/versions/{world['a']['version'].id}"), headers=headers
    ).status_code == 200
    assert client.get(
        ifc_url(world["project_a"].id, f"/versions/{world['a']['version'].id}/download"),
        headers=headers,
    ).status_code == 403


def test_the_generated_viewer_asset_follows_the_same_project_scoping(client, world):
    """`geometry/asset` serves a file too, and is scoped the same way.

    The 409 is the right refusal for the caller's own project — no geometry has
    been generated — and the 404 is the point: another project's revision is
    not found at all, so the two answers never converge into a probe.
    """
    own = client.get(
        ifc_url(world["project_b"].id, f"/versions/{world['b']['version'].id}/geometry/asset"),
        headers=_auth(client, world["outsider"]),
    )
    assert own.status_code == 409

    theirs = client.get(
        ifc_url(world["project_b"].id, f"/versions/{world['a']['version'].id}/geometry/asset"),
        headers=_auth(client, world["outsider"]),
    )
    assert theirs.status_code == 404


# --- feature flag -----------------------------------------------------------


def test_turning_the_ifc_feature_off_closes_the_whole_surface(client, world, monkeypatch):
    """`IFC_FEATURE_ENABLED` is an operational kill switch, ahead of every verb."""
    monkeypatch.setattr(settings, "IFC_FEATURE_ENABLED", False)
    headers = _auth(client, world["manager"])
    for method, path, body in _representative_routes(world):
        response = _send(client, method, path, headers, body)
        assert response.status_code == 403, f"{method.upper()} {path} → {response.status_code}"


def test_the_surface_reopens_when_the_flag_is_restored(client, world):
    # The flag is process-level state; a test that switched it off must not be
    # able to leave the suite in a state where everything trivially passes.
    assert settings.IFC_FEATURE_ENABLED is True
    assert client.get(
        ifc_url(world["project_a"].id, "/models"), headers=_auth(client, world["manager"])
    ).status_code == 200


def test_comparison_can_be_disabled_without_disabling_the_rest(client, world, monkeypatch):
    monkeypatch.setattr(settings, "IFC_COMPARISON_ENABLED", False)
    headers = _auth(client, world["manager"])
    response = client.post(
        ifc_url(world["project_a"].id, "/comparisons"), headers=headers,
        json={
            "baseVersionId": str(world["a"]["version"].id),
            "targetVersionId": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 503
    assert client.get(ifc_url(world["project_a"].id, "/models"), headers=headers).status_code == 200


def test_upload_constraints_report_the_live_configuration(client, world):
    """The client checks a file against these before sending it, so they have
    to be the server's own limits rather than a copy that can drift."""
    response = client.get(
        ifc_url(world["project_a"].id, "/upload-constraints"),
        headers=_auth(client, world["manager"]),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["maxFileMb"] == settings.IFC_MAX_FILE_MB
    assert payload["maxEntityCount"] == settings.IFC_MAX_ENTITY_COUNT
    assert payload["acceptedExtensions"] == [".ifc"]
