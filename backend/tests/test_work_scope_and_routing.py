"""The three concepts the affiliation helpers used to encode, and their tests.

Stage 1 of the redesign replaced `is_main_contractor_engineer` and
`is_consultant_engineer` — 78 call sites across 19 files — with three ideas in
`app.services.work_scope`: what work you can see, which disciplines narrow your
view, and what responsibility you carry on a project. Stage 6 used the third to
route agent findings.

The tests here pin the properties that replaced the role names, and in
particular the two that are *stronger* than what they replaced:

  * an external participant holds none of the office's own authority, enforced
    in the resolution rather than by a guard each endpoint had to remember;
  * task visibility is a union — assigned work *and* reviewed work — where the
    retired code branched and gave you one or the other.

Everything runs in a transaction against the real database and is rolled back.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.company import Company
from app.models.enums import (
    ConsultantApprovalMode, ProjectStatus, TaskStatus, UserRole, UserStatus,
)
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectConsultantReviewer, ProjectMember
from app.models.rbac import (
    Discipline, ProjectMemberDiscipline, ProjectParty, UserDiscipline,
)
from app.models.site_report import SiteReport
from app.models.task import Task
from app.models.user import User
from app.services import rbac, work_scope
from app.services.authorization import effective_permissions, has_permission


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
def office(db):
    """An office project with staff of several disciplines and a contractor."""
    suffix = uuid4().hex[:10]
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    company = Company(name=f"Scope Office {suffix}", kind="CONSULTING_OFFICE", is_active=True)
    db.add(company)
    db.flush()

    def user(name, role_code, legacy=UserRole.ENGINEER):
        role = roles[role_code]
        person = User(
            full_name=name, email=f"{name.lower()}-{suffix}@test.local",
            hashed_password="x", role=legacy, status=UserStatus.ACTIVE,
            company_id=company.id, org_role_id=role.id,
            is_internal=role.is_internal_only,
        )
        db.add(person)
        db.flush()
        return person

    manager = user("Manager", "project_manager", UserRole.PROJECT_MANAGER)
    reviewer = user("Reviewer", "senior_engineer")
    site_civil = user("SiteCivil", "site_engineer")
    site_elec = user("SiteElec", "site_engineer")
    doer = user("Doer", "engineer")
    contractor_person = user("ContractorRep", "contractor_representative")

    project = Project(
        name=f"Scope Project {suffix}", status=ProjectStatus.ACTIVE,
        company_id=company.id, project_manager_id=manager.id,
        consultant_approval_mode=ConsultantApprovalMode.DISCIPLINE_BASED_REVIEW,
    )
    db.add(project)
    db.flush()

    contractor_party = ProjectParty(
        project_id=project.id, kind="MAIN_CONTRACTOR",
        display_name=f"Contractor {suffix}", is_primary=True,
    )
    db.add(contractor_party)
    db.flush()

    def member(person, role_code, *, party=None, site=False):
        row = ProjectMember(
            project_id=project.id, user_id=person.id, role_on_project=person.role,
            project_role_id=roles[role_code].id, is_active=True,
            is_site_engineer=site, party_id=party.id if party else None,
        )
        db.add(row)
        db.flush()
        return row

    manager_member = member(manager, "project_manager")
    reviewer_member = member(reviewer, "senior_engineer")
    civil_member = member(site_civil, "site_engineer", site=True)
    elec_member = member(site_elec, "site_engineer", site=True)
    doer_member = member(doer, "engineer")
    member(contractor_person, "contractor_representative", party=contractor_party)

    disciplines = {
        row.code: row for row in db.query(Discipline).filter(
            Discipline.organization_id.is_(None)
        ).all()
    }

    def assign_discipline(person, membership, code):
        db.add(UserDiscipline(user_id=person.id, discipline_id=disciplines[code].id,
                              is_primary=True))
        db.add(ProjectMemberDiscipline(project_member_id=membership.id,
                                       discipline_id=disciplines[code].id))

    assign_discipline(site_civil, civil_member, "civil")
    assign_discipline(site_elec, elec_member, "electrical")
    assign_discipline(reviewer, reviewer_member, "mechanical")
    db.flush()

    civil_task = Task(
        project_id=project.id, name="Slab pour", task_code=f"C-{suffix[:5]}",
        status=TaskStatus.IN_PROGRESS, created_by_id=manager.id, discipline="civil",
        review_required=True,
    )
    elec_task = Task(
        project_id=project.id, name="Cable tray", task_code=f"E-{suffix[:5]}",
        status=TaskStatus.IN_PROGRESS, created_by_id=manager.id, discipline="electrical",
        review_required=True,
    )
    mech_task = Task(
        project_id=project.id, name="Ductwork", task_code=f"M-{suffix[:5]}",
        status=TaskStatus.IN_PROGRESS, created_by_id=manager.id, discipline="mechanical",
        review_required=True,
    )
    db.add_all([civil_task, elec_task, mech_task])
    db.flush()
    civil_task.assignees.append(doer)
    db.flush()

    # The reviewer is the named mechanical reviewer on this project.
    db.add(ProjectConsultantReviewer(
        project_id=project.id, user_id=reviewer.id, discipline="mechanical",
    ))
    db.flush()

    return {
        "suffix": suffix, "company": company, "project": project, "roles": roles,
        "disciplines": disciplines, "manager": manager, "reviewer": reviewer,
        "site_civil": site_civil, "site_elec": site_elec, "doer": doer,
        "contractor_person": contractor_person, "contractor_party": contractor_party,
        "civil_task": civil_task, "elec_task": elec_task, "mech_task": mech_task,
        "civil_member": civil_member, "elec_member": elec_member,
    }


# ---------------------------------------------------------------------------
# The office-authority ceiling
# ---------------------------------------------------------------------------

OFFICE_AUTHORITY = (
    "task.review", "design_change.approve", "cost_validation.review",
    "field_evidence.verify", "site_report.verify", "issue.resolve",
    "project.manage_members", "task.create", "task.edit", "schedule.edit",
)


def test_an_external_participant_holds_none_of_the_office_authority(db, office):
    """The rule the retired `is_consultant_engineer` guards were protecting.

    A contractor's engineer used to *hold* `design_change.approve` — the
    catalogue gave it to every Engineer — and was stopped only by a guard
    repeated at each endpoint. Any endpoint that forgot the guard was a hole.
    Now they do not hold it at all.
    """
    granted = effective_permissions(db, office["contractor_person"], office["project"].id)
    for code in OFFICE_AUTHORITY:
        assert code not in granted, code


def test_an_override_cannot_give_an_external_participant_certification(db, office):
    """The wall: approving work is the office putting its name to it.

    `issue.resolve` used to be asserted here alongside these two, on the
    reasoning that everything `office_only` was equally unreachable. It is not
    on the wall any more — closing an issue is office *work*, and an office that
    wants its main contractor to close issues on their own scope is describing
    a real arrangement rather than a mistake. What must never move is
    certification, which is what this asserts.
    """
    person = office["contractor_person"]
    for code in ("design_change.approve", "task.review"):
        db.add(UserPermissionOverride(
            user_id=person.id, permission_code=code, allowed=True,
            project_id=office["project"].id, reason="deliberate mistake, for the test",
        ))
    db.flush()
    for code in ("design_change.approve", "task.review"):
        assert not has_permission(db, person, code, office["project"].id), code


def test_office_work_reaches_an_external_participant_only_by_decision(db, office):
    """The default and the delegation, asserted together.

    Nothing on the delegable list arrives through a role — that is what stops a
    re-permissioned template quietly handing a contractor the office's work.
    An explicit, project-scoped grant does reach them, because refusing it
    would be the platform overruling the office about its own project.
    """
    person = office["contractor_person"]
    project_id = office["project"].id

    assert not has_permission(db, person, "issue.resolve", project_id), (
        "not inherited from a role"
    )

    db.add(UserPermissionOverride(
        user_id=person.id, permission_code="issue.resolve", allowed=True,
        project_id=project_id, reason="the office delegated this deliberately",
    ))
    db.flush()
    assert has_permission(db, person, "issue.resolve", project_id), (
        "a deliberate grant takes effect"
    )
    # And it carries nothing else with it.
    assert not has_permission(db, person, "task.review", project_id)


def test_office_staff_keep_that_authority(db, office):
    """The ceiling narrows outsiders and nobody else."""
    granted = effective_permissions(db, office["manager"], office["project"].id)
    assert "task.review" in granted
    assert "issue.resolve" in granted
    assert "project.manage_members" in granted


def test_a_pre_backfill_contractor_account_is_already_external(db, office):
    """The migration window is not a hole.

    An account the backfill has not reached has no role row, so the retired
    affiliation is the only externality signal it carries. If that were ignored
    there would be a period in which a contractor's engineer could approve the
    office's design changes — which is exactly what the retired guards
    prevented.
    """
    unmigrated = User(
        full_name="Unmigrated", email=f"unmigrated-{office['suffix']}@test.local",
        hashed_password="x", role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
        engineer_affiliation="main_contractor",
    )
    db.add(unmigrated)
    db.flush()
    assert rbac.is_external_participant(db, unmigrated, None) is True
    assert "design_change.approve" not in effective_permissions(db, unmigrated)


def test_a_pre_backfill_office_account_is_not_external(db, office):
    """And the bridge does not sweep up the office's own people."""
    for affiliation in (None, "internal_engineer"):
        person = User(
            full_name="Staff", email=f"staff-{affiliation}-{office['suffix']}@test.local",
            hashed_password="x", role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
            engineer_affiliation=affiliation,
        )
        db.add(person)
        db.flush()
        assert rbac.is_external_participant(db, person, None) is False, affiliation


# ---------------------------------------------------------------------------
# Task scope: a union, not a branch
# ---------------------------------------------------------------------------

def test_somebody_who_both_holds_and_reviews_work_sees_both(db, office):
    """The case the retired either/or branching could not express.

    A reviewer given a task of their own used to see the review queue *or*
    their assignments depending on which affiliation branch they fell into.
    """
    reviewer = office["reviewer"]
    office["civil_task"].assignees.append(reviewer)
    db.flush()

    visible = work_scope.narrow_to_own_work(
        db.query(Task).filter(Task.project_id == office["project"].id),
        db, reviewer, office["project"].id,
    ).all()
    ids = {task.id for task in visible}
    assert office["civil_task"].id in ids, "their own assignment"
    assert office["mech_task"].id in ids, "the work they review"
    assert office["elec_task"].id not in ids, "neither theirs nor reviewed by them"


def test_somebody_doing_work_sees_only_their_own(db, office):
    visible = work_scope.narrow_to_own_work(
        db.query(Task).filter(Task.project_id == office["project"].id),
        db, office["doer"], office["project"].id,
    ).all()
    assert {task.id for task in visible} == {office["civil_task"].id}


def test_whoever_runs_the_project_sees_the_whole_list(db, office):
    assert work_scope.sees_all_tasks(db, office["manager"], office["project"].id)
    visible = work_scope.narrow_to_own_work(
        db.query(Task).filter(Task.project_id == office["project"].id),
        db, office["manager"], office["project"].id,
    ).all()
    assert len(visible) == 3


def test_an_external_participant_is_narrowed_to_their_own_work(db, office):
    assert not work_scope.sees_all_tasks(
        db, office["contractor_person"], office["project"].id
    )
    visible = work_scope.narrow_to_own_work(
        db.query(Task).filter(Task.project_id == office["project"].id),
        db, office["contractor_person"], office["project"].id,
    ).all()
    assert visible == []


# ---------------------------------------------------------------------------
# Discipline scope
# ---------------------------------------------------------------------------

def test_a_reviewer_is_narrowed_to_the_disciplines_they_cover(db, office):
    codes = work_scope.scoped_discipline_codes(
        db, office["reviewer"], office["project"].id
    )
    assert codes == {"mechanical"}


def test_office_staff_with_the_permission_are_not_narrowed(db, office):
    assert work_scope.scoped_discipline_codes(
        db, office["manager"], office["project"].id
    ) is None


def test_covering_two_disciplines_widens_the_scope(db, office):
    """The structure `EngineerProfile.discipline` could not express."""
    reviewer = office["reviewer"]
    rbac.set_user_disciplines(
        db, user=reviewer,
        discipline_ids=[office["disciplines"]["mechanical"].id,
                        office["disciplines"]["electrical"].id],
        primary_id=office["disciplines"]["mechanical"].id,
    )
    # Clear the project-level assignment so the profile-wide one answers.
    for row in db.query(ProjectMemberDiscipline).filter(
        ProjectMemberDiscipline.project_member_id.in_(
            db.query(ProjectMember.id).filter(
                ProjectMember.project_id == office["project"].id,
                ProjectMember.user_id == reviewer.id,
            )
        )
    ).all():
        db.delete(row)
    db.flush()
    codes = work_scope.scoped_discipline_codes(db, reviewer, office["project"].id)
    assert codes == {"mechanical", "electrical"}


def test_somebody_with_no_discipline_recorded_is_not_narrowed(db, office):
    """Hiding the whole project from staff the office assigned is the worse failure."""
    assert work_scope.scoped_discipline_codes(
        db, office["doer"], office["project"].id
    ) is None


# ---------------------------------------------------------------------------
# Site responsibility and site reports
# ---------------------------------------------------------------------------

def test_a_project_can_have_several_site_engineers_of_different_disciplines(db, office):
    ids = work_scope.site_engineer_ids(db, office["project"].id)
    assert ids == {office["site_civil"].id, office["site_elec"].id}

    civil_only = work_scope.site_engineer_ids(
        db, office["project"].id, discipline_codes={"civil"},
    )
    assert civil_only == {office["site_civil"].id}


def test_site_engineer_is_a_project_responsibility_not_a_role(db, office):
    """The same role, one carrying site responsibility and one not."""
    assert work_scope.is_site_engineer(db, office["site_civil"], office["project"].id)
    assert not work_scope.is_site_engineer(db, office["doer"], office["project"].id)


def test_a_report_about_a_task_takes_that_task_s_discipline(db, office):
    resolved = work_scope.report_discipline_id(
        db, office["site_civil"], office["project"].id, office["elec_task"],
    )
    assert resolved == office["disciplines"]["electrical"].id


def test_a_report_with_no_task_takes_the_reporter_s_single_discipline(db, office):
    resolved = work_scope.report_discipline_id(
        db, office["site_civil"], office["project"].id, None,
    )
    assert resolved == office["disciplines"]["civil"].id


def test_a_report_from_somebody_covering_several_disciplines_is_left_open(db, office):
    """Guessing which visit it was would be worse than saying nothing."""
    rbac.set_user_disciplines(
        db, user=office["site_civil"],
        discipline_ids=[office["disciplines"]["civil"].id,
                        office["disciplines"]["architectural"].id],
    )
    for row in db.query(ProjectMemberDiscipline).filter(
        ProjectMemberDiscipline.project_member_id == office["civil_member"].id
    ).all():
        db.delete(row)
    db.flush()
    assert work_scope.report_discipline_id(
        db, office["site_civil"], office["project"].id, None,
    ) is None


def test_reports_from_several_site_engineers_are_distinguishable(db, office):
    """The point of the column: one project, one day, three visits."""
    reports = []
    for person, task in (
        (office["site_civil"], office["civil_task"]),
        (office["site_elec"], office["elec_task"]),
    ):
        report = SiteReport(
            project_id=office["project"].id, task_id=task.id,
            submitted_by_id=person.id, report_date=date(2026, 3, 2),
            summary_text="Visit record", review_status="submitted",
            discipline_id=work_scope.report_discipline_id(
                db, person, office["project"].id, task,
            ),
        )
        db.add(report)
        reports.append(report)
    db.flush()
    assert reports[0].discipline_id == office["disciplines"]["civil"].id
    assert reports[1].discipline_id == office["disciplines"]["electrical"].id
    assert reports[0].discipline_id != reports[1].discipline_id


# ---------------------------------------------------------------------------
# Finding routing
# ---------------------------------------------------------------------------

class _Insight:
    """The two fields routing reads. A real AIInsight has many more."""

    def __init__(self, affected):
        self.affected_json = affected


def test_a_finding_reaches_the_people_whose_discipline_it_is_about(db, office):
    from app.services.agents import finding_routing

    recipients = finding_routing.resolve(
        db, project_id=office["project"].id,
        insight=_Insight({"disciplines": ["electrical"]}),
        principal=office["manager"],
    )
    assert office["site_elec"].id in recipients.user_ids
    assert office["site_civil"].id not in recipients.user_ids
    assert office["manager"].id in recipients.user_ids, "the accountable person, always"


def test_an_ifc_tagged_finding_is_matched_through_the_discipline_mapping(db, office):
    """`PLUMBING` is not an office discipline; `mechanical` covers it."""
    from app.services.agents import finding_routing

    recipients = finding_routing.resolve(
        db, project_id=office["project"].id,
        insight=_Insight({"disciplines": ["PLUMBING"]}),
        principal=office["manager"],
    )
    assert office["reviewer"].id in recipients.user_ids
    assert recipients.reasons[office["reviewer"].id].startswith("covers")


def test_a_finding_about_no_particular_discipline_reaches_site_and_project(db, office):
    from app.services.agents import finding_routing

    recipients = finding_routing.resolve(
        db, project_id=office["project"].id, insight=_Insight({}),
        principal=office["manager"],
    )
    assert {office["site_civil"].id, office["site_elec"].id} <= recipients.user_ids
    assert office["doer"].id not in recipients.user_ids


def test_an_external_participant_is_never_told_about_a_finding(db, office):
    """Agent findings are the office's own review material."""
    from app.services.agents import finding_routing

    for affected in ({}, {"disciplines": ["civil"]}, {"disciplines": ["PLUMBING"]}):
        recipients = finding_routing.resolve(
            db, project_id=office["project"].id, insight=_Insight(affected),
            principal=office["manager"],
        )
        assert office["contractor_person"].id not in recipients.user_ids, affected


def test_routing_never_reaches_somebody_who_could_not_open_the_finding(db, office):
    """Eligibility first: a notification you would be refused is noise."""
    from app.services.agents import finding_routing

    for user_id in finding_routing.resolve(
        db, project_id=office["project"].id,
        insight=_Insight({"disciplines": ["civil"]}), principal=office["manager"],
    ).user_ids:
        person = db.get(User, user_id)
        assert has_permission(db, person, "ai.review_insight", office["project"].id)


def test_the_accountable_principal_is_included_even_when_nobody_matches(db, office):
    """An unrouted finding is worse than an imprecise one."""
    from app.services.agents import finding_routing

    recipients = finding_routing.resolve(
        db, project_id=office["project"].id,
        insight=_Insight({"disciplines": ["quantity_surveying"]}),
        principal=office["manager"],
    )
    assert recipients.user_ids == {office["manager"].id}
    assert recipients.reasons[office["manager"].id] == "accountable for this project"
