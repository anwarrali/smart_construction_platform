"""External participants must not be able to read the office's project.

The redesign lets people from outside the consulting office — a main
contractor, a subcontractor, the client — onto a project. That is the feature,
and it is also the largest new risk in the whole change: before it, everybody
with project access was staff, so document scoping only had to distinguish
between kinds of staff. Adding outsiders to that model without changing it
would have handed a contractor every drawing, specification and internal note
on the job the moment somebody added them to the team.

So the rule is deny-by-default, and these tests are the evidence for it. They
exercise the property from both ends: an external participant sees nothing they
were not deliberately given, and giving them one thing gives them exactly that
one thing.

Everything runs in a transaction against the real database and is rolled back.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.company import Company
from app.models.document import Document
from app.models.enums import (
    DocumentType, ProjectStatus, TaskStatus, UserRole, UserStatus,
)
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.rbac import DocumentPartyShare, ProjectParty, Role, RolePermission
from app.models.task import Task
from app.models.user import User
from app.services import rbac
from app.services.authorization import effective_permissions, has_permission
from app.services.document_access import (
    assert_document_readable, readable_document_ids,
)


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
def world(db):
    """An office project with a contractor, a subcontractor and a client on it.

    Built through the *new* model directly rather than through the backfill:
    this is what a project set up after the redesign looks like, and the
    deny-by-default rule has to hold for those without any migration having
    run.
    """
    suffix = uuid4().hex[:10]
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    office = Company(
        name=f"Redesign Office {suffix}", kind="CONSULTING_OFFICE",
        is_tenant=False, is_active=True,
    )
    db.add(office)
    db.flush()

    def user(name, role_code, *, legacy_role=UserRole.ENGINEER):
        role = roles[role_code]
        person = User(
            full_name=name, email=f"{name.lower()}-{suffix}@test.local",
            hashed_password="x", role=legacy_role, status=UserStatus.ACTIVE,
            company_id=office.id, org_role_id=role.id,
            is_internal=role.is_internal_only,
        )
        db.add(person)
        db.flush()
        return person

    manager = user("Manager", "project_manager", legacy_role=UserRole.PROJECT_MANAGER)
    site_engineer = user("SiteEng", "site_engineer")
    contractor_person = user("ContractorRep", "contractor_representative")
    subcontractor_person = user("SubRep", "subcontractor_representative")
    client_person = user("ClientRep", "client_representative", legacy_role=UserRole.OWNER)

    project = Project(
        name=f"Isolation Project {suffix}", status=ProjectStatus.ACTIVE,
        company_id=office.id, project_manager_id=manager.id, owner_id=client_person.id,
    )
    db.add(project)
    db.flush()

    main_contractor = ProjectParty(
        project_id=project.id, kind="MAIN_CONTRACTOR",
        display_name=f"Barakat Contracting {suffix}", is_primary=True,
    )
    db.add(main_contractor)
    db.flush()
    subcontractor = ProjectParty(
        project_id=project.id, kind="SUBCONTRACTOR",
        display_name=f"Nader Electrical {suffix}",
        parent_party_id=main_contractor.id,
    )
    client_party = ProjectParty(
        project_id=project.id, kind="CLIENT",
        display_name=f"Al-Quds Development {suffix}", is_primary=True,
    )
    db.add_all([subcontractor, client_party])
    db.flush()

    def member(person, role_code, party=None, site=False):
        row = ProjectMember(
            project_id=project.id, user_id=person.id,
            role_on_project=person.role, project_role_id=roles[role_code].id,
            party_id=party.id if party else None, is_active=True,
            is_site_engineer=site,
        )
        db.add(row)
        return row

    member(manager, "project_manager")
    member(site_engineer, "site_engineer", site=True)
    member(contractor_person, "contractor_representative", main_contractor)
    member(subcontractor_person, "subcontractor_representative", subcontractor)
    member(client_person, "client_representative", client_party)
    db.flush()

    done_task = Task(
        project_id=project.id, name="Completed slab", task_code=f"D-{suffix[:6]}",
        status=TaskStatus.DONE, review_status="approved", created_by_id=manager.id,
    )
    open_task = Task(
        project_id=project.id, name="Open works", task_code=f"O-{suffix[:6]}",
        status=TaskStatus.IN_PROGRESS, created_by_id=manager.id,
    )
    db.add_all([done_task, open_task])
    db.flush()

    internal_note = Document(
        project_id=project.id, uploaded_by_id=manager.id,
        title=f"Internal fee note {suffix}", document_type=DocumentType.OTHER,
        file_url="/x/internal.pdf",
    )
    drawing = Document(
        project_id=project.id, uploaded_by_id=site_engineer.id,
        title=f"Structural drawing {suffix}", document_type=DocumentType.DRAWING,
        file_url="/x/drawing.pdf",
    )
    contract = Document(
        project_id=project.id, uploaded_by_id=manager.id,
        title=f"Main contract {suffix}", document_type=DocumentType.CONTRACT,
        file_url="/x/contract.pdf",
    )
    approved_evidence = Document(
        project_id=project.id, uploaded_by_id=site_engineer.id, task_id=done_task.id,
        title=f"Approved slab record {suffix}", document_type=DocumentType.REPORT,
        file_url="/x/approved.pdf",
    )
    draft = Document(
        project_id=project.id, uploaded_by_id=site_engineer.id, task_id=open_task.id,
        title=f"Draft in progress {suffix}", document_type=DocumentType.REPORT,
        file_url="/x/draft.pdf",
    )
    db.add_all([internal_note, drawing, contract, approved_evidence, draft])
    db.flush()

    return {
        "suffix": suffix, "office": office, "project": project, "roles": roles,
        "manager": manager, "site_engineer": site_engineer,
        "contractor_person": contractor_person,
        "subcontractor_person": subcontractor_person, "client_person": client_person,
        "main_contractor": main_contractor, "subcontractor": subcontractor,
        "client_party": client_party,
        "internal_note": internal_note, "drawing": drawing, "contract": contract,
        "approved_evidence": approved_evidence, "draft": draft,
    }


# ---------------------------------------------------------------------------
# Documents: deny by default
# ---------------------------------------------------------------------------

def test_a_contractor_added_to_a_project_reads_no_documents(db, world):
    """The headline property. Membership is not access."""
    readable = readable_document_ids(db, world["contractor_person"], world["project"].id)
    assert readable == []


def test_a_subcontractor_reads_no_documents_either(db, world):
    readable = readable_document_ids(db, world["subcontractor_person"], world["project"].id)
    assert readable == []


def test_sharing_one_document_grants_exactly_that_document(db, world):
    db.add(DocumentPartyShare(
        document_id=world["drawing"].id, party_id=world["main_contractor"].id,
        shared_by_id=world["manager"].id,
    ))
    db.flush()

    readable = readable_document_ids(db, world["contractor_person"], world["project"].id)
    assert readable == [world["drawing"].id]
    # And it does not leak sideways to the subcontractor, who is a different
    # party even though they answer to this one.
    assert readable_document_ids(db, world["subcontractor_person"], world["project"].id) == []


def test_a_share_with_the_subcontractor_does_not_reach_the_main_contractor(db, world):
    db.add(DocumentPartyShare(
        document_id=world["drawing"].id, party_id=world["subcontractor"].id,
    ))
    db.flush()
    assert readable_document_ids(db, world["contractor_person"], world["project"].id) == []
    assert readable_document_ids(db, world["subcontractor_person"], world["project"].id) == [
        world["drawing"].id
    ]


def test_an_external_participant_reads_their_own_upload(db, world):
    """Otherwise submitting a document would mean losing sight of it."""
    theirs = Document(
        project_id=world["project"].id, uploaded_by_id=world["contractor_person"].id,
        title=f"Contractor method statement {world['suffix']}",
        document_type=DocumentType.TECHNICAL, file_url="/x/method.pdf",
    )
    db.add(theirs)
    db.flush()
    readable = readable_document_ids(db, world["contractor_person"], world["project"].id)
    assert readable == [theirs.id]


def test_the_client_keeps_the_portal_rule(db, world):
    """Official files and approved work — the rule the Owner role already had."""
    readable = set(readable_document_ids(db, world["client_person"], world["project"].id))
    assert world["contract"].id in readable
    assert world["approved_evidence"].id in readable
    assert world["draft"].id not in readable
    assert world["internal_note"].id not in readable


def test_office_staff_still_read_the_project(db, world):
    readable = set(readable_document_ids(db, world["manager"], world["project"].id))
    assert len(readable) == 5


def test_assert_document_readable_refuses_an_unshared_document(db, world):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        assert_document_readable(db, world["contractor_person"], world["internal_note"])
    assert caught.value.status_code == 403
    assert "shared" in caught.value.detail.lower()


def test_rag_retrieval_cannot_widen_what_the_contractor_reads(db, world):
    """Retrieval narrows through the same helper the download endpoint uses.

    Asserted as an identity rather than by running an embedding search: the
    property that matters is that there is one implementation, because a second
    one is what would drift.
    """
    from app.services import document_access

    ids = document_access.readable_document_ids(
        db, world["contractor_person"], world["project"].id
    )
    query_ids = [
        row.id for row in document_access.readable_documents_query(
            db, world["contractor_person"], world["project"].id
        ).all()
    ]
    assert ids == query_ids == []


# ---------------------------------------------------------------------------
# Permissions: the office-wide ceiling
# ---------------------------------------------------------------------------

def test_no_external_participant_holds_an_office_wide_permission(db, world):
    for key in ("contractor_person", "subcontractor_person", "client_person"):
        granted = effective_permissions(db, world[key], world["project"].id)
        assert granted & rbac.NON_PROJECT_SCOPED == set(), key


def test_an_explicit_grant_cannot_lift_the_ceiling(db, world):
    person = world["subcontractor_person"]
    db.add(UserPermissionOverride(
        user_id=person.id, permission_code="platform.view_all_projects", allowed=True,
    ))
    db.flush()
    assert not has_permission(db, person, "platform.view_all_projects")


def test_an_external_participant_cannot_reach_another_project(db, world):
    from app.core.deps import accessible_project_ids

    other = Project(
        name=f"Other project {world['suffix']}", status=ProjectStatus.ACTIVE,
        company_id=world["office"].id, project_manager_id=world["manager"].id,
    )
    db.add(other)
    db.flush()
    reachable = accessible_project_ids(db, world["contractor_person"])
    assert reachable is not None
    assert other.id not in reachable


# ---------------------------------------------------------------------------
# Role assignment rules
# ---------------------------------------------------------------------------

def test_external_role_templates_carry_no_office_wide_permission(db, world):
    for code in ("contractor_representative", "subcontractor_representative",
                 "client_representative", "external_reviewer"):
        role = world["roles"][code]
        assert role.is_internal_only is False
        held = rbac.role_permission_codes(db, role.id)
        assert held & rbac.NON_PROJECT_SCOPED == set(), code


def test_a_party_is_not_linked_to_a_company_record(db, world):
    """A project is the boundary; there is no firm-to-firm relationship.

    Asserted structurally because the temptation to add `organization_id` here
    is real, and doing so would make one office's directory reachable from
    another's project.
    """
    assert not hasattr(ProjectParty, "organization_id")
    columns = {column.name for column in ProjectParty.__table__.columns}
    assert "organization_id" not in columns
    assert "company_id" not in columns


def test_a_subcontractor_points_at_its_main_contractor(db, world):
    assert world["subcontractor"].parent_party_id == world["main_contractor"].id
    assert world["main_contractor"].parent_party_id is None


def test_a_project_can_hold_several_contractors(db, world):
    second = ProjectParty(
        project_id=world["project"].id, kind="MAIN_CONTRACTOR",
        display_name=f"Second contractor {world['suffix']}",
    )
    db.add(second)
    db.flush()
    contractors = db.query(ProjectParty).filter(
        ProjectParty.project_id == world["project"].id,
        ProjectParty.kind == "MAIN_CONTRACTOR",
    ).all()
    assert len(contractors) == 2
    assert sum(1 for item in contractors if item.is_primary) == 1
