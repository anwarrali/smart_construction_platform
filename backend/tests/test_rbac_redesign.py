"""The consulting-office RBAC redesign, proved rather than asserted.

The load-bearing test here is `test_backfill_changes_nobody_s_permissions`: it
builds a world containing every account shape the old model could produce —
administrator, project manager, internal engineer, main-contractor engineers,
an external consultant, a client and two workers, with documents, field
evidence and two site engineers of different disciplines — migrates it, and
then compares the retired permission resolution against the live one for every
(person, project) pair. Anything that differs must be a change declared in
advance in `app.db.rbac_equivalence.INTENTIONAL_CHANGES`; anything else fails.

Everything runs inside one transaction against the real database and is rolled
back, so the shared development database is never written to. That matters
here more than usual: the backfill's normal entry point commits.
"""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.permission_catalogue import BY_CODE, role_defaults
from app.core.role_templates import (
    LEGACY_ROLE_MAP,
    TEMPLATES,
    BY_CODE_TEMPLATE,
    template_for_legacy,
)
from app.db import rbac_backfill, rbac_equivalence
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.company import Company
from app.models.document import Document
from app.models.enums import (
    DocumentType, EngineerDiscipline, FieldSubmissionStatus, ProjectStatus,
    TaskStatus, UserRole, UserStatus,
)
from app.models.field_submission import FieldSubmission
from app.models.permission import RolePermissionOverride, UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.rbac import (
    Discipline, DocumentPartyShare, OrganizationMembership,
    ProjectMemberDiscipline, ProjectParty, Role, RolePermission, UserDiscipline,
)
from app.models.task import Task
from app.models.user import EngineerProfile, User
from app.services import rbac
from app.services.authorization import (
    effective_permissions, has_permission, legacy_effective_permissions,
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
def legacy_world(db):
    """Every account shape the retired model could produce, plus real data.

    Deliberately built with the *old* columns only — `role`,
    `engineer_affiliation`, `role_on_project`, `EngineerProfile.discipline` —
    because that is what a database being migrated actually looks like. Nothing
    here sets `org_role_id`; the backfill is what fills it in.
    """
    suffix = uuid4().hex[:10]

    office = Company(name=f"Nasser Consulting Office {suffix}", is_active=True)
    contractor = Company(name=f"Barakat Contracting {suffix}", is_active=True)
    client_firm = Company(name=f"Al-Quds Development {suffix}", is_active=True)
    db.add_all([office, contractor, client_firm])
    db.flush()

    def user(name, role, affiliation=None, company=None, organization=None,
             status=UserStatus.ACTIVE):
        person = User(
            full_name=name, email=f"{name.lower().replace(' ', '')}-{suffix}@test.local",
            hashed_password="x", role=role, status=status,
            engineer_affiliation=affiliation,
            company_id=company.id if company else None,
            organization=organization,
        )
        db.add(person)
        return person

    admin = user("Admin", UserRole.ADMIN, company=office)
    manager = user("Manager", UserRole.PROJECT_MANAGER, company=office)
    architect = user("Architect", UserRole.ENGINEER, "internal_engineer", office)
    site_civil = user("SiteCivil", UserRole.ENGINEER, "main_contractor", contractor,
                      organization="Barakat Contracting")
    site_elec = user("SiteElec", UserRole.ENGINEER, "main_contractor", contractor,
                     organization="Barakat Contracting")
    reviewer = user("Reviewer", UserRole.ENGINEER, "external_consultant", office,
                    organization="Nasser Consulting Office")
    client = user("Client", UserRole.OWNER, company=client_firm)
    worker_a = user("WorkerA", UserRole.WORKER, company=contractor,
                    organization="Barakat Contracting")
    worker_b = user("WorkerB", UserRole.WORKER, company=contractor,
                    organization="Barakat Contracting")
    db.flush()

    db.add_all([
        EngineerProfile(user_id=architect.id, discipline=EngineerDiscipline.ARCHITECTURAL),
        EngineerProfile(user_id=site_civil.id, discipline=EngineerDiscipline.CIVIL),
        EngineerProfile(user_id=site_elec.id, discipline=EngineerDiscipline.ELECTRICAL),
        EngineerProfile(user_id=reviewer.id, discipline=EngineerDiscipline.MECHANICAL),
    ])

    project = Project(
        name=f"Ramallah Tower {suffix}", status=ProjectStatus.ACTIVE,
        company_id=office.id, owner_id=client.id, project_manager_id=manager.id,
        start_date=date(2026, 1, 5),
    )
    db.add(project)
    db.flush()

    def member(person, role_on_project, *, site_engineer=False, discipline=None):
        row = ProjectMember(
            project_id=project.id, user_id=person.id, role_on_project=role_on_project,
            is_active=True, is_site_engineer=site_engineer, project_discipline=discipline,
        )
        db.add(row)
        return row

    member(manager, UserRole.PROJECT_MANAGER)
    member(architect, UserRole.ENGINEER, discipline="architectural")
    # Two site engineers, different disciplines, same project — the shape the
    # brief calls out and that the old model had no test for.
    civil_member = member(site_civil, UserRole.ENGINEER, site_engineer=True, discipline="civil")
    elec_member = member(site_elec, UserRole.ENGINEER, site_engineer=True, discipline="electrical")
    # An external consultant is stored as ENGINEER globally and CONSULTANT on
    # the project. This divergence is what makes the project-role mapping in
    # the backfill delicate.
    member(reviewer, UserRole.CONSULTANT, discipline="mechanical")
    member(client, UserRole.OWNER)
    member(worker_a, UserRole.WORKER, discipline="civil")
    member(worker_b, UserRole.WORKER, discipline="electrical")
    db.flush()

    task = Task(
        project_id=project.id, name="Column pour, zone B", task_code=f"T-{suffix[:6]}",
        status=TaskStatus.IN_PROGRESS, created_by_id=manager.id, discipline="civil",
    )
    db.add(task)
    db.flush()

    documents = [
        Document(project_id=project.id, uploaded_by_id=architect.id,
                 title=f"Structural drawings {suffix}", document_type=DocumentType.DRAWING,
                 file_url="/x/a.pdf"),
        Document(project_id=project.id, uploaded_by_id=manager.id,
                 title=f"Main contract {suffix}", document_type=DocumentType.CONTRACT,
                 file_url="/x/b.pdf"),
    ]
    db.add_all(documents)
    db.flush()

    evidence = FieldSubmission(
        project_id=project.id, task_id=task.id, submitted_by_id=worker_a.id,
        description="Formwork complete", status=FieldSubmissionStatus.SUBMITTED,
    )
    db.add(evidence)
    db.flush()

    return {
        "suffix": suffix, "office": office, "contractor": contractor,
        "client_firm": client_firm, "project": project, "task": task,
        "admin": admin, "manager": manager, "architect": architect,
        "site_civil": site_civil, "site_elec": site_elec, "reviewer": reviewer,
        "client": client, "worker_a": worker_a, "worker_b": worker_b,
        "documents": documents, "evidence": evidence,
        "civil_member": civil_member, "elec_member": elec_member,
    }


@pytest.fixture()
def migrated(db, legacy_world):
    """`legacy_world` after the backfill, still inside the test transaction."""
    report = rbac_backfill.run(db, commit=False)
    db.flush()
    for person in (
        legacy_world["admin"], legacy_world["manager"], legacy_world["architect"],
        legacy_world["site_civil"], legacy_world["site_elec"], legacy_world["reviewer"],
        legacy_world["client"], legacy_world["worker_a"], legacy_world["worker_b"],
    ):
        db.refresh(person)
    return {**legacy_world, "report": report}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_backfill_changes_nobody_s_permissions(db, migrated):
    """The whole redesign in one assertion.

    Every account, every project it can reach, old resolution against new. A
    difference is allowed only when it matches a change declared in
    `INTENTIONAL_CHANGES`; anything else is a silent widening or a silent
    revocation, which is the failure mode this redesign most needed to avoid.
    """
    report = rbac_equivalence.run(db)

    assert report.unexpected == [], (
        "The configurable role model resolves differently from the retired one "
        "for accounts where no change was declared:\n"
        + "\n".join(item.render() for item in report.unexpected)
    )
    assert report.pairs_checked > 0


def test_the_only_expected_difference_is_worker_removal(db, migrated):
    """Declared changes are declared, not discovered after the fact."""
    report = rbac_equivalence.run(db)
    reasons = {item.explained_by for item in report.expected}
    assert reasons == {
        "worker_archived — Worker accounts hold no permissions",
        "consultant_document_scope_explicit — Consultant reviewers no longer "
        "carry project.view_all_disciplines",
        "external_party_office_authority — External participants hold none of "
        "the office's own authority",
    }

    # And the change is real, not a category nobody landed in: both worker
    # accounts must actually appear, having lost the permissions the retired
    # WORKER role held.
    worker_emails = {migrated["worker_a"].email, migrated["worker_b"].email}
    seen = {item.user_email for item in report.expected}
    assert worker_emails <= seen
    for item in report.expected:
        if item.user_email in worker_emails:
            assert item.gained == set()
            assert "task.view" in item.lost


def test_the_equivalence_gate_fails_when_a_role_is_widened(db, migrated):
    """A negative control.

    A gate that has never been seen to fail is not evidence of anything. This
    grants a role a permission the retired model did not give it and asserts
    the comparison reports it as *unexpected* — so a passing run elsewhere in
    this file means the check looked and found nothing, rather than not
    looking.
    """
    architect = migrated["architect"]
    assert rbac_equivalence.run(db).unexpected == []

    db.add(RolePermission(
        role_id=architect.org_role_id, permission_code="platform.create_project",
        allowed=True,
    ))
    db.flush()

    report = rbac_equivalence.run(db)
    offending = [
        item for item in report.unexpected if item.user_email == architect.email
    ]
    assert offending, "the gate did not notice a widened role"
    assert "platform.create_project" in offending[0].gained
    assert report.ok is False


def test_every_migration_target_template_matches_its_legacy_defaults(db, migrated):
    """A template people are migrated onto grants exactly what they held.

    This is the property that makes the gate above come out empty, checked
    directly so a future edit to a template is caught at the source rather than
    as a mysterious equivalence failure.
    """
    #: The one template that deliberately differs, and by exactly what. Listed
    #: here rather than allowed generically, so a second divergence introduced
    #: later fails this test instead of slipping through.
    declared = {"senior_engineer": {"project.view_all_disciplines"}}

    for (legacy_role, _affiliation), code in LEGACY_ROLE_MAP.items():
        template = BY_CODE_TEMPLATE[code]
        if template.inherits is None:
            # The archived field-staff template. Empty on purpose.
            assert template.permissions() == set()
            continue
        difference = role_defaults(legacy_role) ^ template.permissions()
        assert difference == declared.get(code, set()), (
            f"{code} would change what a {legacy_role.value} can do: {difference}"
        )


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
        organization_id=office.id, code=f"resident_engineer_{migrated['suffix']}",
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
    """The thing `role_on_project == user.role` used to forbid."""
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


def test_seed_roles_folds_configured_role_overrides(db, legacy_world):
    """An office that had customised permissions keeps its customisation."""
    db.add(RolePermissionOverride(
        role=UserRole.ENGINEER, permission_code="schedule.view", allowed=True,
        reason="this office lets engineers see the programme",
    ))
    db.flush()

    roles = rbac.seed_roles(
        db,
        organization_id=legacy_world["office"].id,
        role_overrides=rbac_backfill._legacy_role_overrides(db),
    )
    assert "schedule.view" in rbac.role_permission_codes(db, roles["engineer"].id)
    # And a role that does not inherit from ENGINEER is unaffected.
    assert "schedule.view" not in rbac.role_permission_codes(db, roles["office_staff"].id)


# ---------------------------------------------------------------------------
# Disciplines
# ---------------------------------------------------------------------------

def test_one_person_can_cover_two_disciplines(db, migrated):
    """The structure `EngineerProfile.discipline` could not express."""
    person = migrated["architect"]
    mechanical = rbac.role_by_code and db.query(Discipline).filter(
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
    rbac_backfill.run(db, commit=False)
    db.flush()
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
    unmigrated = db.query(User).filter(
        User.org_role_id.is_(None), User.status == UserStatus.ACTIVE,
    ).count()
    assert unmigrated == 0


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


# `test_unmigrated_accounts_keep_working` stood here and is gone. It asserted
# that an account with no `org_role_id` resolved through the retired enum —
# which was the fallback itself, and which the contract step removed. There is
# no such account any more: `resolved_permissions` raises `UnmigratedUser`, and
# `test_an_account_without_a_role_is_refused` below pins that instead.

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


def test_an_account_without_a_role_is_refused(db, legacy_world):
    """The contract, stated as a test.

    Every account holds a database role. `user_role_backstop` fills the column
    for anything written without one, so producing an unmigrated account takes
    a deliberate `UPDATE` — and resolving one raises rather than falling back
    to the retired enum. The fallback this replaces is what made a partial
    backfill survivable; it is not needed once nothing can create the state it
    tolerated, and keeping it would leave two answers to one question.
    """
    from app.services.rbac import UnmigratedUser

    architect = legacy_world["architect"]
    # The backstop gave it a role on the way in; take it away to construct the
    # state the fallback used to serve.
    assert architect.org_role_id is not None, "the backstop should have filled this"
    architect.org_role_id = None
    db.flush()

    with pytest.raises(UnmigratedUser):
        effective_permissions(db, architect)
