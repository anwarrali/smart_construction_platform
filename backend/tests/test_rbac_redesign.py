"""The consulting-office RBAC redesign, applied to a legacy database.

A world containing every account shape the retired model could produce —
administrator, project manager, internal engineer, main-contractor engineers,
an external consultant, a client and two workers, with documents, field
evidence and two site engineers of different disciplines — is written the way
that model wrote it (`users.role`, `engineer_affiliation`, `role_on_project`,
no office role), then carried across by `app.db.rbac_backfill`.

It runs on a private copy of a database migrated to the last revision that
still has those columns (`legacy_db`, see `tests/isolated_databases.py`): the
shared development database no longer has them at all.
"""

from datetime import date

import pytest
from sqlalchemy import text

from app.core.permission_catalogue import BY_CODE
from app.core.role_templates import BY_CODE_TEMPLATE, TEMPLATES
from app.db import rbac_backfill
from app.models.company import Company
from app.models.document import Document
from app.models.enums import (
    DocumentType, EngineerDiscipline, FieldSubmissionStatus, ProjectStatus,
    TaskStatus, UserStatus,
)
from app.models.field_submission import FieldSubmission
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.rbac import (
    Discipline, DocumentPartyShare, OrganizationMembership,
    ProjectMemberDiscipline, ProjectParty, Role, RolePermission, UserDiscipline,
)
from app.models.task import Task
from app.models.user import EngineerProfile, User
from app.services import rbac
from app.services.authorization import effective_permissions, has_permission
from tests.isolated_databases import insert_legacy_account, insert_legacy_member


@pytest.fixture()
def db(legacy_db):
    session, _url = legacy_db
    return session


@pytest.fixture()
def legacy_world(db):
    """Every account shape the retired model could produce, plus real data."""
    office = Company(name="Nasser Consulting Office", is_active=True)
    contractor = Company(name="Barakat Contracting", is_active=True)
    client_firm = Company(name="Al-Quds Development", is_active=True)
    db.add_all([office, contractor, client_firm])
    db.flush()

    def user(name, role, affiliation=None, company=None, organization=None):
        user_id = insert_legacy_account(
            db, email=f"{name.lower()}@legacy.test", full_name=name, role=role,
            affiliation=affiliation, company_id=company.id if company else None,
            organization=organization,
        )
        return db.get(User, user_id)

    admin = user("Admin", "ADMIN", company=office)
    manager = user("Manager", "PROJECT_MANAGER", company=office)
    architect = user("Architect", "ENGINEER", "internal_engineer", office)
    site_civil = user("SiteCivil", "ENGINEER", "main_contractor", contractor,
                      organization="Barakat Contracting")
    site_elec = user("SiteElec", "ENGINEER", "main_contractor", contractor,
                     organization="Barakat Contracting")
    reviewer = user("Reviewer", "ENGINEER", "external_consultant", office,
                    organization="Nasser Consulting Office")
    client = user("Client", "OWNER", company=client_firm)
    worker_a = user("WorkerA", "WORKER", company=contractor, organization="Barakat Contracting")
    worker_b = user("WorkerB", "WORKER", company=contractor, organization="Barakat Contracting")

    db.add_all([
        EngineerProfile(user_id=architect.id, discipline=EngineerDiscipline.ARCHITECTURAL),
        EngineerProfile(user_id=site_civil.id, discipline=EngineerDiscipline.CIVIL),
        EngineerProfile(user_id=site_elec.id, discipline=EngineerDiscipline.ELECTRICAL),
        EngineerProfile(user_id=reviewer.id, discipline=EngineerDiscipline.MECHANICAL),
    ])

    project = Project(
        name="Ramallah Tower", status=ProjectStatus.ACTIVE,
        company_id=office.id, owner_id=client.id, project_manager_id=manager.id,
        start_date=date(2026, 1, 5),
    )
    db.add(project)
    db.flush()

    def member(person, role_on_project, *, site_engineer=False, discipline=None):
        member_id = insert_legacy_member(
            db, project_id=project.id, user_id=person.id, role_on_project=role_on_project,
            site_engineer=site_engineer, discipline=discipline,
        )
        return db.get(ProjectMember, member_id)

    member(manager, "PROJECT_MANAGER")
    member(architect, "ENGINEER", discipline="architectural")
    # Two site engineers, different disciplines, same project.
    civil_member = member(site_civil, "ENGINEER", site_engineer=True, discipline="civil")
    elec_member = member(site_elec, "ENGINEER", site_engineer=True, discipline="electrical")
    # An external consultant was stored as ENGINEER globally and CONSULTANT on
    # the project; the backfill derives the project role from the person.
    member(reviewer, "CONSULTANT", discipline="mechanical")
    member(client, "OWNER")
    member(worker_a, "WORKER", discipline="civil")
    member(worker_b, "WORKER", discipline="electrical")

    task = Task(
        project_id=project.id, name="Column pour, zone B", task_code="T-LEGACY",
        status=TaskStatus.IN_PROGRESS, created_by_id=manager.id, discipline="civil",
    )
    db.add(task)
    db.flush()

    documents = [
        Document(project_id=project.id, uploaded_by_id=architect.id,
                 title="Structural drawings", document_type=DocumentType.DRAWING,
                 file_url="/x/a.pdf"),
        Document(project_id=project.id, uploaded_by_id=manager.id,
                 title="Main contract", document_type=DocumentType.CONTRACT,
                 file_url="/x/b.pdf"),
    ]
    db.add_all(documents)
    db.flush()

    evidence = FieldSubmission(
        project_id=project.id, task_id=task.id, submitted_by_id=worker_a.id,
        description="Formwork complete", status=FieldSubmissionStatus.SUBMITTED,
    )
    db.add(evidence)
    db.commit()

    return {
        "office": office, "contractor": contractor,
        "client_firm": client_firm, "project": project, "task": task,
        "admin": admin, "manager": manager, "architect": architect,
        "site_civil": site_civil, "site_elec": site_elec, "reviewer": reviewer,
        "client": client, "worker_a": worker_a, "worker_b": worker_b,
        "documents": documents, "evidence": evidence,
        "civil_member": civil_member, "elec_member": elec_member,
    }


PEOPLE = ("admin", "manager", "architect", "site_civil", "site_elec", "reviewer",
          "client", "worker_a", "worker_b")


@pytest.fixture()
def migrated(db, legacy_world):
    """`legacy_world` after the backfill."""
    report = rbac_backfill.run(db)
    for key in PEOPLE:
        db.refresh(legacy_world[key])
    return {**legacy_world, "report": report}


# ---------------------------------------------------------------------------
# Where everybody lands
# ---------------------------------------------------------------------------

#: The office role each legacy account must end up on.
LANDS_ON = {
    "admin": "org_admin",
    "manager": "project_manager",
    "architect": "engineer",
    "site_civil": "contractor_representative",
    "site_elec": "contractor_representative",
    "reviewer": "senior_engineer",
    "client": "client_representative",
    "worker_a": "archived_field_staff",
    "worker_b": "archived_field_staff",
}


def test_every_account_lands_on_its_office_role(db, migrated):
    landed = {key: db.get(Role, migrated[key].org_role_id).code for key in PEOPLE}
    assert landed == LANDS_ON


def test_office_staff_hold_exactly_their_template(db, migrated):
    """What an internal account may do is its template, nothing carried over
    from the retired role and nothing lost on the way."""
    for key in ("admin", "manager", "architect", "reviewer"):
        person = migrated[key]
        template = BY_CODE_TEMPLATE[LANDS_ON[key]]
        assert effective_permissions(db, person) == template.permissions(), key


def test_external_accounts_hold_none_of_the_office_authority(db, migrated):
    project_id = migrated["project"].id
    for key in ("site_civil", "site_elec", "client"):
        granted = effective_permissions(db, migrated[key], project_id)
        assert granted <= BY_CODE_TEMPLATE[LANDS_ON[key]].permissions(), key
        assert not granted & rbac.NON_PROJECT_SCOPED, key
        assert not {code for code in granted if BY_CODE[code].office_only}, key


# ---------------------------------------------------------------------------
# Worker removal
# ---------------------------------------------------------------------------

def test_worker_accounts_survive_with_no_permissions(db, migrated):
    worker = migrated["worker_a"]
    assert worker.org_role_id is not None
    role = db.get(Role, worker.org_role_id)
    assert role.code == "archived_field_staff"
    assert effective_permissions(db, worker) == set()
    assert effective_permissions(db, worker, migrated["project"].id) == set()


def test_worker_field_evidence_stays_attributable(db, migrated):
    """Removing the role must not orphan the evidence it produced."""
    evidence = db.get(FieldSubmission, migrated["evidence"].id)
    assert evidence is not None
    assert evidence.submitted_by_id == migrated["worker_a"].id
    assert evidence.submitted_by.full_name == "WorkerA"
    assert evidence.status == FieldSubmissionStatus.SUBMITTED


def test_field_evidence_permission_replaces_the_worker_role(db, migrated):
    """A site engineer can now file what only a worker used to be able to."""
    site_engineer = migrated["site_civil"]
    project_id = migrated["project"].id
    assert has_permission(db, site_engineer, "field_evidence.submit", project_id)
    assert not has_permission(db, migrated["worker_a"], "field_evidence.submit", project_id)


# ---------------------------------------------------------------------------
# Internal vs external
# ---------------------------------------------------------------------------

def test_contractor_engineers_become_external_participants(db, migrated):
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == migrated["project"].id,
        ProjectMember.user_id == migrated["site_civil"].id,
    ).first()
    assert member.party_id is not None
    party = db.get(ProjectParty, member.party_id)
    assert party.kind == "MAIN_CONTRACTOR"
    assert party.display_name == "Barakat Contracting"
    assert migrated["site_civil"].is_internal is False


def test_office_staff_are_not_attached_to_a_party(db, migrated):
    for key in ("manager", "architect", "reviewer"):
        member = db.query(ProjectMember).filter(
            ProjectMember.project_id == migrated["project"].id,
            ProjectMember.user_id == migrated[key].id,
        ).first()
        assert member.party_id is None, f"{key} was treated as an outside party"
        assert migrated[key].is_internal is True


def test_external_consultant_becomes_office_staff_not_an_outside_party(db, migrated):
    """The deliberate non-literal mapping, pinned.

    In the new product the consulting office *is* the reviewer, so a retired
    `external_consultant` account is office staff with review authority. Reading
    the old affiliation string literally would have moved the office's own
    reviewers behind external document scoping.
    """
    reviewer = migrated["reviewer"]
    role = db.get(Role, reviewer.org_role_id)
    assert role.code == "senior_engineer"
    assert role.is_internal_only is True
    assert reviewer.is_internal is True


def test_an_external_participant_can_never_hold_a_platform_permission(db, migrated):
    """The ceiling holds even against an explicit administrator grant."""
    contractor_engineer = migrated["site_civil"]
    project_id = migrated["project"].id

    db.add(UserPermissionOverride(
        user_id=contractor_engineer.id, permission_code="platform.manage_users",
        allowed=True, reason="deliberate mistake, for the test",
    ))
    db.add(UserPermissionOverride(
        user_id=contractor_engineer.id, permission_code="platform.view_all_projects",
        allowed=True, reason="deliberate mistake, for the test",
    ))
    db.flush()

    granted = effective_permissions(db, contractor_engineer, project_id)
    assert "platform.manage_users" not in granted
    assert "platform.view_all_projects" not in granted
    assert not has_permission(db, contractor_engineer, "platform.manage_users")


def test_the_client_is_an_external_party_with_the_portal_intact(db, migrated):
    client = migrated["client"]
    role = db.get(Role, client.org_role_id)
    assert role.code == "client_representative"
    assert role.is_internal_only is False

    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == migrated["project"].id,
        ProjectMember.user_id == client.id,
    ).first()
    party = db.get(ProjectParty, member.party_id)
    assert party.kind == "CLIENT"

    # The client portal's own capabilities are untouched by becoming a party.
    granted = effective_permissions(db, client, migrated["project"].id)
    assert "owner_request.create" in granted
    assert "task.view" in granted


def test_contractor_document_access_is_carried_over_explicitly(db, migrated):
    """Deny-by-default from here, but nothing revoked retroactively."""
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == migrated["project"].id,
        ProjectMember.user_id == migrated["site_civil"].id,
    ).first()
    shared = {
        row.document_id for row in db.query(DocumentPartyShare).filter(
            DocumentPartyShare.party_id == member.party_id
        ).all()
    }
    assert shared == {document.id for document in migrated["documents"]}


# ---------------------------------------------------------------------------
# Roles: configurable, and bounded
# ---------------------------------------------------------------------------

def test_a_new_role_grants_a_permission_with_no_code_change(db, migrated):
    """Acceptance criterion 1, executed.

    Create "Resident Engineer", give it two permissions, put somebody on it —
    and they can do the thing. No deployment, no migration, no enum.
    """
    office = migrated["office"]
    resident = Role(
        organization_id=office.id, code="resident_engineer",
        name_en="Resident Engineer", name_ar="مهندس مقيم", scope="BOTH",
        is_internal_only=True,
    )
    db.add(resident)
    db.flush()
    for code in ("site_report.submit", "field_evidence.submit"):
        db.add(RolePermission(role_id=resident.id, permission_code=code, allowed=True))
    db.flush()

    person = migrated["architect"]
    rbac.assign_org_role(db, user=person, role=resident, organization_id=office.id)
    db.flush()

    project_id = migrated["project"].id
    assert has_permission(db, person, "site_report.submit", project_id)
    assert has_permission(db, person, "field_evidence.submit", project_id)
    # And only those: the role is the whole of their office authority now.
    assert not has_permission(db, person, "platform.manage_users")


def test_renaming_a_role_does_not_touch_its_permissions(db, migrated):
    role = db.get(Role, migrated["manager"].org_role_id)
    before = rbac.role_permission_codes(db, role.id)
    role.name_en = "Projects Lead"
    role.name_ar = "قائد المشاريع"
    db.flush()
    assert rbac.role_permission_codes(db, role.id) == before


def test_the_office_administrator_cannot_be_configured_out_of_administering(db, migrated):
    admin = migrated["admin"]
    role = db.get(Role, admin.org_role_id)
    assert role.undeletable is True

    for code in ("platform.manage_users", "platform.manage_permissions", "org.manage_roles"):
        row = db.query(RolePermission).filter(
            RolePermission.role_id == role.id, RolePermission.permission_code == code,
        ).first()
        if row is not None:
            db.delete(row)
    db.flush()

    granted = effective_permissions(db, admin)
    assert "platform.manage_users" in granted
    assert "platform.manage_permissions" in granted
    assert "org.manage_roles" in granted


def test_a_project_role_can_differ_from_the_office_role(db, migrated):
    """The thing the retired model forbade: a project role had to equal the global one."""
    architect = migrated["architect"]
    pm_role = rbac.role_by_code(db, "project_manager")
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == migrated["project"].id,
        ProjectMember.user_id == architect.id,
    ).first()
    member.project_role_id = pm_role.id
    db.flush()

    project_id = migrated["project"].id
    # Gains the project role's authority, on this project only.
    assert has_permission(db, architect, "task.create", project_id)
    assert "task.create" not in effective_permissions(db, architect, None)


def test_the_backfill_folds_retired_role_overrides_into_the_roles(db, legacy_world):
    """An office that had customised the retired roles keeps its customisation."""
    granted, denied = "schedule.edit", "issue.create"
    assert granted not in BY_CODE_TEMPLATE["engineer"].permissions()
    assert denied in BY_CODE_TEMPLATE["engineer"].permissions()
    for code, allowed in ((granted, True), (denied, False)):
        db.execute(text(
            "INSERT INTO role_permission_overrides (id, role, permission_code, allowed) "
            "VALUES (gen_random_uuid(), CAST('ENGINEER' AS user_role), :code, :allowed)"
        ), {"code": code, "allowed": allowed})
    db.commit()

    rbac_backfill.run(db)

    engineer = rbac.role_by_code(db, "engineer")
    held = rbac.role_permission_codes(db, engineer.id)
    assert granted in held
    assert denied not in held
    # A role that did not inherit from ENGINEER is unaffected.
    office_staff = rbac.role_by_code(db, "office_staff")
    assert granted not in rbac.role_permission_codes(db, office_staff.id)


# ---------------------------------------------------------------------------
# Disciplines
# ---------------------------------------------------------------------------

def test_one_person_can_cover_two_disciplines(db, migrated):
    """The structure `EngineerProfile.discipline` could not express."""
    person = migrated["architect"]
    mechanical = db.query(Discipline).filter(
        Discipline.code == "mechanical", Discipline.organization_id.is_(None)
    ).first()
    electrical = db.query(Discipline).filter(
        Discipline.code == "electrical", Discipline.organization_id.is_(None)
    ).first()
    rbac.set_user_disciplines(
        db, user=person, discipline_ids=[mechanical.id, electrical.id],
        primary_id=mechanical.id,
    )
    db.flush()

    held = rbac.disciplines_for_user(db, person.id)
    assert {item.code for item in held} == {"mechanical", "electrical"}


def test_mep_bridges_to_the_ifc_vocabulary(db, migrated):
    """A reviewer scoped to MEP matches a finding tagged PLUMBING.

    The two vocabularies were unrelated before, which made this impossible.
    """
    mep = db.query(Discipline).filter(
        Discipline.code == "mep", Discipline.organization_id.is_(None)
    ).first()
    assert mep is not None
    names = rbac.ifc_discipline_names([mep])
    assert {"MECHANICAL", "ELECTRICAL", "PLUMBING", "FIRE_PROTECTION"} <= names


def test_project_disciplines_are_backfilled_from_the_member_row(db, migrated):
    rows = db.query(ProjectMemberDiscipline).filter(
        ProjectMemberDiscipline.project_member_id == migrated["civil_member"].id
    ).all()
    assert [row.discipline.code for row in rows] == ["civil"]


def test_discipline_is_never_an_input_to_a_permission_check(db, migrated):
    """Discipline narrows; it does not grant.

    Two people on the same project with the same role and different
    disciplines must resolve to the same permission set. Anything else means a
    discipline has quietly become an authority.
    """
    project_id = migrated["project"].id
    civil = effective_permissions(db, migrated["site_civil"], project_id)
    electrical = effective_permissions(db, migrated["site_elec"], project_id)
    assert civil == electrical


# ---------------------------------------------------------------------------
# Site engineers
# ---------------------------------------------------------------------------

def test_a_project_supports_several_site_engineers_of_different_disciplines(db, migrated):
    members = db.query(ProjectMember).filter(
        ProjectMember.project_id == migrated["project"].id,
        ProjectMember.is_site_engineer.is_(True),
    ).all()
    assert len(members) == 2
    site_engineer_role = rbac.role_by_code(db, "site_engineer")
    assert {member.project_role_id for member in members} == {site_engineer_role.id}

    disciplines = set()
    for member in members:
        disciplines |= {
            row.discipline.code for row in db.query(ProjectMemberDiscipline).filter(
                ProjectMemberDiscipline.project_member_id == member.id
            ).all()
        }
    assert disciplines == {"civil", "electrical"}


# ---------------------------------------------------------------------------
# Backfill mechanics
# ---------------------------------------------------------------------------

def test_the_backfill_is_idempotent(db, migrated):
    before = {
        "roles": db.query(Role).count(),
        "parties": db.query(ProjectParty).count(),
        "memberships": db.query(OrganizationMembership).count(),
        "user_disciplines": db.query(UserDiscipline).count(),
        "shares": db.query(DocumentPartyShare).count(),
    }
    report = rbac_backfill.run(db)
    assert report.users_mapped == 0
    after = {
        "roles": db.query(Role).count(),
        "parties": db.query(ProjectParty).count(),
        "memberships": db.query(OrganizationMembership).count(),
        "user_disciplines": db.query(UserDiscipline).count(),
        "shares": db.query(DocumentPartyShare).count(),
    }
    assert before == after


def test_the_backfill_maps_every_account(db, migrated):
    assert migrated["report"].unmapped_users == []
    assert db.query(User).filter(User.org_role_id.is_(None)).count() == 0


def test_the_office_is_the_project_owner_organization(db, migrated):
    project = db.get(Project, migrated["project"].id)
    assert project.company_id is not None
    office = db.get(Company, project.company_id)
    assert office.id == migrated["office"].id


def test_a_contractor_organization_is_a_label_not_a_parent(db, migrated):
    """No hierarchy: the contractor takes part through the project only."""
    contractor = db.get(Company, migrated["contractor"].id)
    assert contractor.kind == "CONTRACTOR"
    assert contractor.is_tenant is False
    # The party that represents them on the project holds no link back to it.
    party = db.query(ProjectParty).filter(
        ProjectParty.project_id == migrated["project"].id,
        ProjectParty.kind == "MAIN_CONTRACTOR",
    ).first()
    assert party is not None
    assert not hasattr(party, "organization_id")


# ---------------------------------------------------------------------------
# Catalogue integrity
# ---------------------------------------------------------------------------

def test_every_template_permission_exists_in_the_catalogue():
    for template in TEMPLATES:
        unknown = {code for code in template.permissions() if code not in BY_CODE}
        assert unknown == set(), f"{template.code} names permissions that do not exist: {unknown}"


def test_no_template_grants_a_non_project_scoped_permission_to_an_external_role():
    for template in TEMPLATES:
        if template.is_internal_only:
            continue
        offending = template.permissions() & rbac.NON_PROJECT_SCOPED
        assert offending == set(), (
            f"{template.code} is an external role but would grant {offending}"
        )


def test_an_account_without_a_role_is_refused():
    """Resolution never guesses: no office role, no permissions — an error."""
    from uuid import uuid4

    from app.services.rbac import UnmigratedUser

    roleless = User(id=uuid4(), full_name="Roleless", email="roleless@legacy.test",
                    hashed_password="x", status=UserStatus.ACTIVE, is_internal=True)
    with pytest.raises(UnmigratedUser):
        effective_permissions(None, roleless)
