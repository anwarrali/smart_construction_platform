"""The eleven security properties the consulting-office redesign must hold.

Written as one file so the whole set can be run as a gate before the legacy
contract migration, rather than being spread across the suites that happen to
own each feature. Every test here corresponds to a numbered requirement:

  1. an internal office engineer reaches their permitted work
  2. a Site Engineer can file site and field evidence
  3. several Site Engineers coexist on one project
  4. discipline scope narrows what it should and nothing else
  5. an external contractor sees only what was explicitly shared
  6. a subcontractor does not inherit its main contractor's access
  7. an external participant cannot gain office authority through an override
  8. client isolation holds
  9. agent findings do not reach unauthorized external users
 10. a retired worker account cannot regain active permissions
 11. a permission change takes effect through the central layer

Everything runs in one transaction against the real database and is rolled
back, so nothing here writes to the shared development database.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.company import Company
from app.models.document import Document
from app.models.enums import (
    DocumentType, FieldSubmissionStatus, ProjectStatus, TaskStatus, UserRole,
    UserStatus,
)
from app.models.field_submission import FieldSubmission
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.rbac import (
    Discipline, DocumentPartyShare, ProjectMemberDiscipline, ProjectParty,
    RolePermission, UserDiscipline,
)
from app.models.site_report import SiteReport
from app.models.task import Task
from app.models.user import User
from app.services import rbac, work_scope
from app.services.authorization import effective_permissions, has_permission
from app.services.document_access import readable_document_ids
from app.services.field_submission_authorization import (
    can_review_field_submission, can_submit_field_evidence,
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
    """One office project with staff, two contractors and a client."""
    suffix = uuid4().hex[:10]
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    office = Company(name=f"Security Office {suffix}", kind="CONSULTING_OFFICE", is_active=True)
    db.add(office)
    db.flush()

    disciplines = {
        row.code: row for row in db.query(Discipline).filter(
            Discipline.organization_id.is_(None)
        ).all()
    }

    def user(name, role_code, legacy=UserRole.ENGINEER, status=UserStatus.ACTIVE):
        role = roles[role_code]
        person = User(
            full_name=name, email=f"{name.lower()}-{suffix}@test.local",
            hashed_password="x", role=legacy, status=status,
            company_id=office.id, org_role_id=role.id,
            is_internal=role.is_internal_only,
        )
        db.add(person)
        db.flush()
        return person

    manager = user("SecManager", "project_manager", UserRole.PROJECT_MANAGER)
    office_engineer = user("SecEngineer", "engineer")
    site_civil = user("SecSiteCivil", "site_engineer")
    site_elec = user("SecSiteElec", "site_engineer")
    reviewer = user("SecReviewer", "senior_engineer")
    contractor_person = user("SecContractor", "contractor_representative")
    sub_person = user("SecSub", "subcontractor_representative")
    client_person = user("SecClient", "client_representative", UserRole.OWNER)
    retired_worker = user(
        "SecRetiredWorker", "archived_field_staff", UserRole.WORKER, UserStatus.INACTIVE,
    )

    project = Project(
        name=f"Security Project {suffix}", status=ProjectStatus.ACTIVE,
        company_id=office.id, project_manager_id=manager.id, owner_id=client_person.id,
    )
    db.add(project)
    db.flush()

    main_contractor = ProjectParty(
        project_id=project.id, kind="MAIN_CONTRACTOR",
        display_name=f"Main {suffix}", is_primary=True,
    )
    db.add(main_contractor)
    db.flush()
    subcontractor = ProjectParty(
        project_id=project.id, kind="SUBCONTRACTOR", display_name=f"Sub {suffix}",
        parent_party_id=main_contractor.id,
    )
    client_party = ProjectParty(
        project_id=project.id, kind="CLIENT", display_name=f"Client {suffix}",
    )
    db.add_all([subcontractor, client_party])
    db.flush()

    def member(person, role_code, *, party=None, site=False, discipline=None):
        row = ProjectMember(
            project_id=project.id, user_id=person.id, role_on_project=person.role,
            project_role_id=roles[role_code].id, is_active=True,
            is_site_engineer=site, party_id=party.id if party else None,
        )
        db.add(row)
        db.flush()
        if discipline:
            db.add(UserDiscipline(user_id=person.id, discipline_id=disciplines[discipline].id))
            db.add(ProjectMemberDiscipline(
                project_member_id=row.id, discipline_id=disciplines[discipline].id,
            ))
            db.flush()
        return row

    member(manager, "project_manager")
    member(office_engineer, "engineer")
    civil_member = member(site_civil, "site_engineer", site=True, discipline="civil")
    elec_member = member(site_elec, "site_engineer", site=True, discipline="electrical")
    member(reviewer, "senior_engineer", discipline="mechanical")
    member(contractor_person, "contractor_representative", party=main_contractor)
    member(sub_person, "subcontractor_representative", party=subcontractor)
    member(client_person, "client_representative", party=client_party)

    civil_task = Task(
        project_id=project.id, name="Slab", task_code=f"C-{suffix[:5]}",
        status=TaskStatus.IN_PROGRESS, created_by_id=manager.id, discipline="civil",
    )
    done_task = Task(
        project_id=project.id, name="Approved", task_code=f"D-{suffix[:5]}",
        status=TaskStatus.DONE, review_status="approved", created_by_id=manager.id,
    )
    db.add_all([civil_task, done_task])
    db.flush()
    civil_task.assignees.append(site_civil)
    db.flush()

    drawing = Document(
        project_id=project.id, uploaded_by_id=office_engineer.id,
        title=f"Drawing {suffix}", document_type=DocumentType.DRAWING, file_url="/x/d.pdf",
    )
    contract = Document(
        project_id=project.id, uploaded_by_id=manager.id,
        title=f"Contract {suffix}", document_type=DocumentType.CONTRACT, file_url="/x/c.pdf",
    )
    db.add_all([drawing, contract])
    db.flush()

    return {
        "suffix": suffix, "office": office, "project": project, "roles": roles,
        "disciplines": disciplines, "manager": manager,
        "office_engineer": office_engineer, "site_civil": site_civil,
        "site_elec": site_elec, "reviewer": reviewer,
        "contractor_person": contractor_person, "sub_person": sub_person,
        "client_person": client_person, "retired_worker": retired_worker,
        "main_contractor": main_contractor, "subcontractor": subcontractor,
        "client_party": client_party, "civil_task": civil_task,
        "done_task": done_task, "drawing": drawing, "contract": contract,
        "civil_member": civil_member, "elec_member": elec_member,
    }


# --- 1 ----------------------------------------------------------------------

def test_1_an_internal_office_engineer_reaches_their_permitted_work(db, world):
    person = world["office_engineer"]
    project_id = world["project"].id
    assert has_permission(db, person, "task.view", project_id)
    assert has_permission(db, person, "document.upload", project_id)
    assert has_permission(db, person, "issue.create", project_id)
    # And is not narrowed out of the project's documents.
    assert len(readable_document_ids(db, person, project_id)) == 2


# --- 2 ----------------------------------------------------------------------

def test_2_a_site_engineer_can_file_site_and_field_evidence(db, world):
    person = world["site_civil"]
    project_id = world["project"].id
    assert has_permission(db, person, "site_report.submit", project_id)
    assert has_permission(db, person, "field_evidence.submit", project_id)
    assert work_scope.is_site_engineer(db, person, project_id)
    assert can_submit_field_evidence(db, person, world["civil_task"])

    submission = FieldSubmission(
        project_id=project_id, task_id=world["civil_task"].id,
        submitted_by_id=person.id, description="Formwork complete",
        status=FieldSubmissionStatus.SUBMITTED,
    )
    db.add(submission)
    db.flush()
    assert submission.submitted_by_id == person.id
    # And somebody else with the verify permission confirms it, never themselves.
    assert not can_review_field_submission(db, person, submission)
    assert can_review_field_submission(db, world["manager"], submission)


# --- 3 ----------------------------------------------------------------------

def test_3_several_site_engineers_coexist_with_different_disciplines(db, world):
    project_id = world["project"].id
    ids = work_scope.site_engineer_ids(db, project_id)
    assert ids == {world["site_civil"].id, world["site_elec"].id}
    assert work_scope.site_engineer_ids(db, project_id, discipline_codes={"civil"}) == {
        world["site_civil"].id
    }
    # Their reports are distinguishable.
    civil_report = SiteReport(
        project_id=project_id, task_id=world["civil_task"].id,
        submitted_by_id=world["site_civil"].id, report_date=date(2026, 4, 1),
        review_status="submitted",
        discipline_id=work_scope.report_discipline_id(
            db, world["site_civil"], project_id, world["civil_task"],
        ),
    )
    elec_report = SiteReport(
        project_id=project_id, submitted_by_id=world["site_elec"].id,
        report_date=date(2026, 4, 1), review_status="submitted",
        discipline_id=work_scope.report_discipline_id(
            db, world["site_elec"], project_id, None,
        ),
    )
    db.add_all([civil_report, elec_report])
    db.flush()
    assert civil_report.discipline_id == world["disciplines"]["civil"].id
    assert elec_report.discipline_id == world["disciplines"]["electrical"].id


# --- 4 ----------------------------------------------------------------------

def test_4_discipline_scope_narrows_only_who_it_should(db, world):
    project_id = world["project"].id
    # A narrowed reviewer.
    assert work_scope.scoped_discipline_codes(db, world["reviewer"], project_id) == {
        "mechanical"
    }
    # Not narrowed: whoever runs the project, and an ordinary office engineer.
    assert work_scope.scoped_discipline_codes(db, world["manager"], project_id) is None
    assert work_scope.scoped_discipline_codes(
        db, world["office_engineer"], project_id
    ) is None
    # Discipline is not an authority: two people, same role, different
    # disciplines, identical permissions.
    assert effective_permissions(db, world["site_civil"], project_id) == \
        effective_permissions(db, world["site_elec"], project_id)


# --- 5 ----------------------------------------------------------------------

def test_5_a_contractor_sees_only_what_was_explicitly_shared(db, world):
    person = world["contractor_person"]
    project_id = world["project"].id
    assert readable_document_ids(db, person, project_id) == []

    db.add(DocumentPartyShare(
        document_id=world["drawing"].id, party_id=world["main_contractor"].id,
    ))
    db.flush()
    assert readable_document_ids(db, person, project_id) == [world["drawing"].id]


# --- 6 ----------------------------------------------------------------------

def test_6_a_subcontractor_does_not_inherit_its_contractor_s_access(db, world):
    db.add(DocumentPartyShare(
        document_id=world["drawing"].id, party_id=world["main_contractor"].id,
    ))
    db.flush()
    project_id = world["project"].id
    assert readable_document_ids(db, world["contractor_person"], project_id) == [
        world["drawing"].id
    ]
    assert readable_document_ids(db, world["sub_person"], project_id) == []
    # The hierarchy exists — it just does not carry access.
    assert world["subcontractor"].parent_party_id == world["main_contractor"].id


# --- 7 ----------------------------------------------------------------------

#: Certification and access governance. Never held by an external participant,
#: at any price — no role, no override, no misconfiguration. This is the wall.
NEVER_EXTERNAL_AUTHORITY = (
    "task.review", "design_change.approve", "cost_validation.review",
    "field_evidence.verify", "site_report.verify",
    "ai.review_insight", "ai.promote_insight",
    "project.manage_members", "project.manage_parties",
    "document.share_external", "project.edit", "project.invite_external",
    # Deleting a project destroys every record the office and its external
    # participants hold against it. Adding it here is what makes
    # `test_7_...` prove that no override, on any project, can hand it to a
    # contractor, a subcontractor or the client.
    "project.delete",
)

#: Office *work*. An external role never inherits it, but an administrator can
#: delegate it to one named person on one named project — which is a real
#: arrangement (a main contractor maintaining the construction programme, or
#: raising and closing tasks on their own scope) and not the platform's
#: business to forbid.
DELEGABLE_OFFICE_WORK = ("task.create", "task.edit", "schedule.edit", "issue.resolve")
PLATFORM_AUTHORITY = (
    "platform.manage_users", "platform.manage_permissions",
    "platform.view_all_projects", "platform.create_project",
    "org.manage_roles", "org.manage_disciplines", "org.manage_settings",
)


def test_7_an_override_cannot_give_an_external_participant_office_authority(db, world):
    """The wall. Certification and access governance, granted every way at once."""
    project_id = world["project"].id
    for person in (world["contractor_person"], world["sub_person"], world["client_person"]):
        for code in NEVER_EXTERNAL_AUTHORITY + PLATFORM_AUTHORITY:
            db.add(UserPermissionOverride(
                user_id=person.id, permission_code=code, allowed=True,
                project_id=project_id, reason="deliberate mistake, for the test",
            ))
        db.flush()
        granted = effective_permissions(db, person, project_id)
        leaked = granted & set(NEVER_EXTERNAL_AUTHORITY + PLATFORM_AUTHORITY)
        assert leaked == set(), f"{person.full_name} leaked {sorted(leaked)}"


def test_7c_an_external_role_never_inherits_office_work_either(db, world):
    """The default. Nothing delegable arrives by accident, only by decision."""
    granted = effective_permissions(db, world["contractor_person"], world["project"].id)
    assert not (granted & set(DELEGABLE_OFFICE_WORK)), (
        "office work must not be inherited from a role"
    )


def test_7d_office_work_can_be_delegated_to_a_contractor_deliberately(db, world):
    """The other half of the rule, and the reason the wall had to be narrowed.

    A blanket ceiling meant an office could not let its main contractor
    maintain the construction programme or raise a task on their own scope,
    even when it wanted to — the platform overruling the office about its own
    project. Delegation is now possible, per person, per project.

    What must not follow is approval authority, so that is asserted in the same
    breath: the contractor can now do the work and still cannot sign it off.
    """
    project_id = world["project"].id
    person = world["contractor_person"]
    for code in DELEGABLE_OFFICE_WORK:
        db.add(UserPermissionOverride(
            user_id=person.id, permission_code=code, allowed=True,
            project_id=project_id, reason="the office delegated this deliberately",
        ))
    db.flush()

    granted = effective_permissions(db, person, project_id)
    assert set(DELEGABLE_OFFICE_WORK) <= granted, (
        "a deliberate, project-scoped grant must take effect"
    )
    # And the wall is untouched by it.
    assert not (granted & set(NEVER_EXTERNAL_AUTHORITY)), (
        "delegating office work must never carry certification with it"
    )
    # The grant is scoped to the project it was made on, and nowhere else.
    assert not (effective_permissions(db, person, None) & set(DELEGABLE_OFFICE_WORK))


def test_7e_the_two_ceilings_agree_with_the_catalogue(db, world):
    """The sets in this file are the catalogue's, not a second opinion."""
    from app.services import rbac as rbac_service

    assert set(NEVER_EXTERNAL_AUTHORITY) == set(rbac_service.NEVER_EXTERNAL)
    assert set(DELEGABLE_OFFICE_WORK) == set(rbac_service.OFFICE_ONLY) - set(rbac_service.NEVER_EXTERNAL)
    # The wall is a subset of the default: everything unreachable is also
    # uninheritable. A code that was `never_external` without being
    # `office_only` would be reachable through a role, which is the one
    # ordering mistake this arrangement could make.
    assert set(rbac_service.NEVER_EXTERNAL) <= set(rbac_service.OFFICE_ONLY)


def test_7b_a_role_edit_cannot_give_an_external_participant_office_authority(db, world):
    """The other way somebody would try: change the role, not the person."""
    role = world["roles"]["contractor_representative"]
    # Upserted rather than inserted: the seeded contractor template already
    # *holds* two of these, because it inherits an Engineer's permissions. That
    # is the point — the ceiling is what stops them mattering, not the absence
    # of the row.
    for code in ("design_change.approve", "task.review", "platform.manage_users"):
        rbac.set_role_permission(db, role=role, code=code, allowed=True)
    db.flush()
    assert {"design_change.approve", "task.review", "platform.manage_users"} <=         rbac.role_permission_codes(db, role.id), "the role really does hold them"
    granted = effective_permissions(db, world["contractor_person"], world["project"].id)
    assert "design_change.approve" not in granted
    assert "task.review" not in granted
    assert "platform.manage_users" not in granted


# --- 8 ----------------------------------------------------------------------

def test_8_client_isolation_holds(db, world):
    person = world["client_person"]
    project_id = world["project"].id
    readable = set(readable_document_ids(db, person, project_id))
    assert world["contract"].id in readable, "official project files"
    assert world["drawing"].id not in readable, "work in progress"
    granted = effective_permissions(db, person, project_id)
    # A client holds neither the wall nor the delegable office work: nobody
    # delegated any of it to them, and nobody could delegate the first half.
    assert granted & set(NEVER_EXTERNAL_AUTHORITY) == set()
    assert granted & set(DELEGABLE_OFFICE_WORK) == set()
    assert granted & set(PLATFORM_AUTHORITY) == set()


def test_8b_a_client_cannot_reach_another_project(db, world):
    from app.core.deps import accessible_project_ids

    other = Project(
        name=f"Other {world['suffix']}", status=ProjectStatus.ACTIVE,
        company_id=world["office"].id, project_manager_id=world["manager"].id,
    )
    db.add(other)
    db.flush()
    reachable = accessible_project_ids(db, world["client_person"])
    assert reachable is not None
    assert other.id not in reachable


# --- 9 ----------------------------------------------------------------------

class _Insight:
    def __init__(self, affected):
        self.affected_json = affected


def test_9_agent_findings_never_reach_an_external_participant(db, world):
    from app.services.agents import finding_routing

    externals = {
        world["contractor_person"].id, world["sub_person"].id, world["client_person"].id,
    }
    for affected in ({}, {"disciplines": ["civil"]}, {"disciplines": ["STRUCTURAL"]},
                     {"disciplines": ["PLUMBING"]}):
        recipients = finding_routing.resolve(
            db, project_id=world["project"].id, insight=_Insight(affected),
            principal=world["manager"],
        )
        assert recipients.user_ids & externals == set(), affected


def test_9b_every_recipient_could_actually_open_the_finding(db, world):
    from app.services.agents import finding_routing

    recipients = finding_routing.resolve(
        db, project_id=world["project"].id,
        insight=_Insight({"disciplines": ["civil"]}), principal=world["manager"],
    )
    for user_id in recipients.user_ids:
        person = db.get(User, user_id)
        assert has_permission(db, person, "ai.review_insight", world["project"].id)


# --- 10 ---------------------------------------------------------------------

def test_10_a_retired_worker_account_cannot_regain_permissions(db, world):
    person = world["retired_worker"]
    assert effective_permissions(db, person) == set()

    # Reactivating the account is not enough: the role it sits on holds nothing.
    person.status = UserStatus.ACTIVE
    db.flush()
    assert effective_permissions(db, person) == set()

    # And an override cannot resurrect office authority through it either,
    # because the archived role is still what it holds.
    db.add(UserPermissionOverride(
        user_id=person.id, permission_code="task.view", allowed=True,
    ))
    db.flush()
    granted = effective_permissions(db, person)
    assert granted == {"task.view"}, "only what was explicitly granted, nothing inherited"


def test_10b_worker_is_not_an_assignable_role_template(db, world):
    from app.core.role_templates import TEMPLATES

    codes = {template.code for template in TEMPLATES}
    assert "worker" not in codes
    archived = next(item for item in TEMPLATES if item.code == "archived_field_staff")
    assert archived.permissions() == set()


# --- 11 ---------------------------------------------------------------------

def test_11_a_permission_change_takes_effect_through_the_central_layer(db, world):
    """One edit, and every consumer of the central layer follows it."""
    person = world["office_engineer"]
    project_id = world["project"].id
    assert has_permission(db, person, "document.upload", project_id)

    role_id = person.org_role_id
    row = db.query(RolePermission).filter(
        RolePermission.role_id == role_id,
        RolePermission.permission_code == "document.upload",
    ).first()
    db.delete(row)
    db.flush()

    assert not has_permission(db, person, "document.upload", project_id)
    assert "document.upload" not in effective_permissions(db, person, project_id)


def test_11b_voice_and_the_tool_layer_read_the_same_answer(db, world):
    """No second authorization model anywhere in the AI path."""
    from app.services.voice_capabilities import CAPABILITIES, is_available

    person = world["site_civil"]
    project_id = world["project"].id
    capability = next(
        item for item in CAPABILITIES
        if item.permission_code == "field_evidence.submit"
    )
    assert is_available(db, user=person, project_id=project_id, capability=capability)

    role_row = db.query(RolePermission).filter(
        RolePermission.role_id == person.org_role_id,
        RolePermission.permission_code == "field_evidence.submit",
    ).first()
    db.delete(role_row)
    db.flush()
    assert not is_available(
        db, user=person, project_id=project_id, capability=capability
    )


# --- 12: this pass ----------------------------------------------------------
#
# Three properties the redesign asserted but nothing enforced until now.


def test_12_no_new_account_can_be_provisioned_as_a_worker(db, world):
    """Worker is not an account type an administrator can still create.

    Test 10 proves a *retired* worker account holds nothing. This proves the
    other half — that the platform cannot produce a new one. Both provisioning
    paths are covered: the administrator helper and the schema the registration
    model validates against.
    """
    from pydantic import ValidationError

    from app.core.permissions import PRIMARY_ROLES, ROLE_LABELS, can_create_team_role
    from app.schemas.user import UserCreate

    assert UserRole.WORKER not in PRIMARY_ROLES
    assert UserRole.WORKER not in ROLE_LABELS
    assert can_create_team_role(UserRole.ADMIN, UserRole.WORKER) is False
    assert can_create_team_role(UserRole.ADMIN, UserRole.ENGINEER) is True

    with pytest.raises(ValidationError):
        UserCreate(
            email=f"newworker-{world['suffix']}@test.local",
            full_name="New Worker", password="Sufficiently-Long-1",
            phone_number="+970599123456", role=UserRole.WORKER,
        )


def test_12b_site_responsibility_follows_the_assignment_not_the_legacy_role(db, world):
    """A project may put site responsibility on any of its own people.

    The retired rule was "only a contractor-side Engineer", which read the
    legacy enum on the *account* and so made an office's own manager, architect
    or surveyor ineligible to carry the site on a project the office runs. The
    rule that replaced it is structural and reads the *membership*: somebody
    taking part for an outside party does not carry the office's site
    responsibility.
    """
    project_id = world["project"].id

    # The manager's legacy role is PROJECT_MANAGER, which the retired rule
    # rejected outright. Nothing about the office model says it should.
    manager_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == world["manager"].id,
    ).one()
    manager_member.is_site_engineer = True
    db.flush()
    assert work_scope.is_site_engineer(db, world["manager"], project_id) is True
    assert world["manager"].id in work_scope.site_engineer_ids(db, project_id)

    # An external participant is the case that must stay closed, and it is
    # closed by the party link rather than by any role name.
    contractor_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == world["contractor_person"].id,
    ).one()
    assert contractor_member.party_id is not None
    assert contractor_member.is_site_engineer is False
    assert rbac.membership_context(
        db, world["contractor_person"].id, project_id,
    ).is_external is True


def test_12c_field_evidence_serialises_with_the_renamed_author(db, world):
    """`FieldSubmission.worker_id` became `submitted_by_id`, everywhere.

    The column, the relationship and the two response schemas have to move
    together: a schema still asking for `worker_id` cannot be built from the
    record at all, so every field-evidence endpoint answers 500 rather than
    denying anything. That failure is invisible to a permission test, which is
    why it is asserted here.
    """
    from app.schemas.field_submission import (
        EvidencePhotoArchiveItem, FieldSubmissionOut,
    )

    # A submitter with a routable e-mail domain: `UserOut.email` is an
    # `EmailStr`, and the fixture's `.test.local` is a reserved name pydantic
    # refuses — which would fail this test for a reason that has nothing to do
    # with the rename it exists to pin.
    submitter = User(
        full_name="SecEvidenceAuthor",
        email=f"evidence-{world['suffix']}@example.com",
        hashed_password="x", role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
        company_id=world["office"].id,
        org_role_id=world["roles"]["site_engineer"].id, is_internal=True,
    )
    db.add(submitter)
    db.flush()
    submission = FieldSubmission(
        project_id=world["project"].id, task_id=world["civil_task"].id,
        submitted_by_id=submitter.id,
        description="Slab poured", status=FieldSubmissionStatus.SUBMITTED,
    )
    db.add(submission)
    db.flush()
    db.refresh(submission)

    rendered = FieldSubmissionOut.model_validate(submission)
    assert rendered.submitted_by_id == submitter.id
    assert rendered.submitted_by.id == submitter.id
    assert "workerId" not in rendered.model_dump(by_alias=True)
    assert "submittedById" in rendered.model_dump(by_alias=True)

    # The archive item is assembled by hand in app.api.photo_archive rather
    # than read off the ORM, so its field names are pinned separately.
    fields = set(EvidencePhotoArchiveItem.model_fields)
    assert {"submitted_by_id", "submitted_by_name"} <= fields
    assert not {"worker_id", "worker_name"} & fields
