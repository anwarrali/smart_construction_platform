"""Who may destroy a project, and who must not.

`DELETE /projects/{id}` had no test of any kind. That is a poor thing for the
single most destructive endpoint in the platform to be missing: 42 columns carry
a foreign key to `projects.id` and 39 of them cascade, so this removes every
task, document, attachment, model revision, site report, finding and event
recorded against the project along with the row.

It was gated on `is_admin(user.role)` — the retired enum. It is now gated on
`project.delete`, a permission added specifically for it rather than borrowed
from a code that merely resolved the same way. `project.edit` measures zero
differences against `is_admin` on this database and would have been the
convenient reuse; the reason it was refused is the first test below.

The tests are written against the *behaviour*, not the code path, so they keep
their meaning if the implementation moves again.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.projects import delete_project
from app.core.permission_catalogue import BY_CODE
from app.core.role_templates import TEMPLATES
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.authorization import has_permission

CODE = "project.delete"


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
    suffix = uuid4().hex[:10]

    def user(name, role, affiliation=None):
        person = User(
            full_name=name, email=f"{name.lower()}-{suffix}@test.local",
            hashed_password="x", role=role, status=UserStatus.ACTIVE,
            engineer_affiliation=affiliation,
        )
        db.add(person)
        return person

    people = {
        "admin": user("DelAdmin", UserRole.ADMIN),
        "manager": user("DelPm", UserRole.PROJECT_MANAGER),
        "engineer": user("DelEngineer", UserRole.ENGINEER, "internal_engineer"),
        "contractor": user("DelContractor", UserRole.ENGINEER, "main_contractor"),
        "owner": user("DelOwner", UserRole.OWNER),
    }
    db.flush()

    project = Project(
        name=f"Deletable Project {suffix}", status=ProjectStatus.ACTIVE,
        owner_id=people["owner"].id, project_manager_id=people["manager"].id,
    )
    keep = Project(
        name=f"Untouched Project {suffix}", status=ProjectStatus.ACTIVE,
        owner_id=people["owner"].id, project_manager_id=people["manager"].id,
    )
    db.add_all([project, keep])
    db.flush()
    for person in (people["manager"], people["engineer"], people["contractor"]):
        db.add(ProjectMember(
            project_id=project.id, user_id=person.id,
            role_on_project=person.role, is_active=True,
        ))
    db.flush()
    people["project"] = project
    people["keep"] = keep
    people["db"] = db
    user_ids = [p.id for p in people.values() if isinstance(p, User)]
    project_ids = [project.id, keep.id]
    try:
        yield people
    finally:
        # `delete_project` commits, so a rollback is not enough.
        db.rollback()
        params = {"projects": project_ids, "users": user_ids}
        for statement in (
            "DELETE FROM user_permission_overrides WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
            "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
            "DELETE FROM projects WHERE id = ANY(:projects)",
            "DELETE FROM users WHERE id = ANY(:users)",
        ):
            db.execute(text(statement), params)
        db.commit()


# --- why this is its own permission -----------------------------------------

def test_deletion_is_not_implied_by_permission_to_edit(db):
    """The reuse that was available, and refused.

    `project.edit` resolves identically to the retired `is_admin` check on this
    database, so swapping it in would have passed every gate. It is a different
    capability: an office granting a role the ability to correct a project's
    start date must not thereby grant it the ability to delete the project and
    everything recorded against it.
    """
    assert CODE in BY_CODE, "project.delete must exist in the catalogue"
    assert CODE != "project.edit"
    assert BY_CODE[CODE].label.lower() != BY_CODE["project.edit"].label.lower()


def test_the_permission_says_what_it_does(db):
    """A destructive capability has to be legible in the Access Control list."""
    permission = BY_CODE[CODE]
    assert "delete" in permission.label.lower()
    assert "permanently" in permission.description.lower()


def test_deletion_is_project_scoped_office_only_and_never_external(db):
    """Three properties `is_admin` never had.

    `project_scoped` is the substantive one: `has_permission` also requires
    project access for a project-scoped code, so the grant cannot reach a
    project the holder is not on. The old check was a bare role comparison and
    had no such bound.
    """
    permission = BY_CODE[CODE]
    assert permission.project_scoped is True
    assert permission.office_only is True
    assert permission.never_external is True


# --- who holds it ------------------------------------------------------------

def test_only_roles_that_could_already_delete_hold_it(db):
    """The regression the dataset could not catch.

    `technical_director` inherits the administrator's catalogue defaults but
    provisions accounts whose retired role is PROJECT_MANAGER, so
    `is_admin(user.role)` has always answered False for it. No account holds
    that template, so an equivalence run over real data would have reported zero
    differences while the template silently gained the ability to delete every
    project in the office.
    """
    granting = {t.code for t in TEMPLATES if CODE in t.permissions()}
    assert granting, "no template grants project.delete"
    for template in TEMPLATES:
        if CODE in template.permissions():
            assert template.legacy_role == "ADMIN", (
                f"{template.code} grants {CODE} but provisions accounts whose "
                f"retired role is {template.legacy_role}, which could not delete "
                "a project before this change"
            )
    assert "technical_director" not in granting


# --- the endpoint ------------------------------------------------------------

def test_an_administrator_can_delete_a_project(world):
    db = world["db"]
    project_id = world["project"].id

    result = delete_project(project_id=project_id, db=db, current_user=world["admin"])

    assert "deleted" in result["message"].lower()
    assert db.query(Project).filter(Project.id == project_id).first() is None


@pytest.mark.parametrize("who", ["manager", "engineer", "contractor", "owner"])
def test_nobody_else_can_delete_a_project(world, who):
    """Including the project's own manager and its owner.

    The manager is the interesting case: they manage this project, and
    `get_manageable_project_or_403` — which still guards milestone editing —
    would admit them. Deleting the project is not managing it.
    """
    db = world["db"]
    project_id = world["project"].id

    with pytest.raises(HTTPException) as refusal:
        delete_project(project_id=project_id, db=db, current_user=world[who])

    assert refusal.value.status_code == 403
    assert db.query(Project).filter(Project.id == project_id).first() is not None


def test_a_missing_project_is_not_found_rather_than_forbidden(world):
    """Order matters: an administrator asking for a project that does not exist
    should be told so, not refused."""
    with pytest.raises(HTTPException) as refusal:
        delete_project(project_id=uuid4(), db=world["db"], current_user=world["admin"])
    assert refusal.value.status_code == 404


def test_a_grant_cannot_reach_a_project_the_holder_is_not_on(world):
    """The bound `is_admin` did not have.

    Granting `project.delete` to one person globally must not let them delete a
    project they have no part in: `has_permission` re-checks project access for
    every project-scoped code.
    """
    db = world["db"]
    engineer = world["engineer"]
    db.add(UserPermissionOverride(
        user_id=engineer.id, permission_code=CODE, allowed=True, project_id=None,
    ))
    db.flush()

    # `keep` is a project this engineer is not a member of.
    assert has_permission(db, engineer, CODE, world["keep"].id) is False
    with pytest.raises(HTTPException) as refusal:
        delete_project(project_id=world["keep"].id, db=db, current_user=engineer)
    assert refusal.value.status_code == 403
    assert db.query(Project).filter(Project.id == world["keep"].id).first() is not None


def test_an_external_participant_can_never_hold_it(world):
    """`never_external` re-applies after overrides, so a mistake in Access
    Control cannot hand a contractor the ability to delete the office's project."""
    db = world["db"]
    contractor = world["contractor"]
    db.add(UserPermissionOverride(
        user_id=contractor.id, permission_code=CODE, allowed=True,
        project_id=world["project"].id,
    ))
    db.flush()

    assert has_permission(db, contractor, CODE, world["project"].id) is False
    with pytest.raises(HTTPException) as refusal:
        delete_project(project_id=world["project"].id, db=db, current_user=contractor)
    assert refusal.value.status_code == 403
