"""The canonical list of things a person can be allowed to do.

This catalogue does not invent a second authorization system. It names the
checks the application already performs and records, for each one, the roles
that hold it today. `app.services.authorization` resolves an effective answer by
starting from these defaults and then applying whatever the administrator has
configured on top.

Keeping the defaults identical to the previous hardcoded behaviour is
deliberate: installing this layer must not change who can do what until an
administrator actually changes something.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import UserRole

ADMIN = UserRole.ADMIN
PM = UserRole.PROJECT_MANAGER
ENGINEER = UserRole.ENGINEER
CONSULTANT = UserRole.CONSULTANT
OWNER = UserRole.OWNER
WORKER = UserRole.WORKER


@dataclass(frozen=True)
class Permission:
    code: str
    group: str
    label: str
    description: str
    #: Roles that hold this permission when nothing has been configured.
    default_roles: frozenset[UserRole]
    #: True when the permission is meaningful inside a single project, so an
    #: administrator can grant it for one project rather than everywhere.
    project_scoped: bool = True
    #: Permissions that must never be taken away from an administrator,
    #: otherwise an administrator could lock the platform out of itself.
    admin_locked: bool = False
    aliases: tuple[str, ...] = field(default=())


def _p(code, group, label, description, roles, *, project_scoped=True, admin_locked=False):
    return Permission(code, group, label, description, frozenset(roles),
                      project_scoped=project_scoped, admin_locked=admin_locked)


CATALOGUE: tuple[Permission, ...] = (
    # --- Platform administration -------------------------------------------
    _p("platform.manage_users", "platform", "Manage user accounts",
       "Create, edit, activate and deactivate accounts.", {ADMIN},
       project_scoped=False, admin_locked=True),
    _p("platform.manage_permissions", "platform", "Manage permissions",
       "Change what roles and people are allowed to do.", {ADMIN},
       project_scoped=False, admin_locked=True),
    _p("platform.create_project", "platform", "Create projects",
       "Open a new project on the platform.", {ADMIN}, project_scoped=False),
    _p("platform.view_all_projects", "platform", "See every project",
       "Read any project without being a member of it.", {ADMIN}, project_scoped=False),

    # --- Project setup ------------------------------------------------------
    _p("project.manage_members", "project", "Manage the project team",
       "Add or remove people from a project and set their role on it.", {ADMIN, PM}),
    # Editing project setup was administrator-only at the endpoint. The default
    # records that, rather than widening access as a side effect of making the
    # check configurable; an administrator can grant it to managers in one click.
    _p("project.edit", "project", "Edit project details",
       "Change project information, dates and settings.", {ADMIN}),
    _p("project.manage_reminders", "project", "Configure reminders",
       "Set reminder intervals, quiet hours and escalation.", {ADMIN, PM}),

    # --- Tasks and scheduling ----------------------------------------------
    _p("task.view", "tasks", "View tasks", "See the project task list.",
       {ADMIN, PM, ENGINEER, CONSULTANT, OWNER, WORKER}),
    _p("task.create", "tasks", "Create tasks", "Add new tasks to a project.", {ADMIN, PM}),
    _p("task.edit", "tasks", "Edit tasks", "Change task details and assignment.", {ADMIN, PM}),
    _p("task.update_progress", "tasks", "Update task progress",
       "Record progress and submit work for review.", {ADMIN, PM, ENGINEER, WORKER}),
    _p("task.review", "tasks", "Review submitted work",
       "Approve, reject or request rework on submitted task work.",
       {ADMIN, PM, CONSULTANT, ENGINEER}),
    _p("schedule.view", "schedule", "View the schedule",
       "Open the Gantt, critical path and delay analysis.", {ADMIN, PM, CONSULTANT, OWNER}),
    _p("schedule.edit", "schedule", "Change the schedule",
       "Shift planned dates and cascade the effect downstream.", {ADMIN, PM}),

    # --- Site work ----------------------------------------------------------
    _p("site_visit.schedule", "field", "Schedule site visits",
       "Book a site visit and notify its participants.", {ADMIN, PM, ENGINEER}),
    # Filing a report is field work: the endpoint accepted the Project Manager
    # and contractor-side Engineers, and not administrators.
    _p("site_report.submit", "field", "Submit site reports",
       "File a daily or visit site report.", {PM, ENGINEER}),
    _p("issue.create", "field", "Raise issues", "Open a project issue.",
       {ADMIN, PM, ENGINEER, CONSULTANT}),
    _p("issue.resolve", "field", "Resolve issues", "Close or resolve a project issue.",
       {ADMIN, PM}),

    # --- Client communication ----------------------------------------------
    _p("owner_request.create", "requests", "Submit client requests",
       "Raise a request on behalf of the client.", {ADMIN, PM, OWNER}),
    _p("owner_request.review", "requests", "Answer client requests",
       "Respond to, accept or reject a client request.", {ADMIN, PM, ENGINEER}),
    _p("design_change.propose", "requests", "Propose design changes",
       "Turn an accepted request into a proposed design change.", {ADMIN, PM, ENGINEER}),
    # Official approval of a design change rested with the assigned consultant
    # alone, and the discipline restriction still applies on top of this.
    _p("design_change.approve", "requests", "Approve design changes",
       "Give a design change its official approval.", {CONSULTANT}),

    # --- Models and documents ----------------------------------------------
    _p("ifc.view", "models", "View IFC models", "Open models, hierarchy and properties.",
       {ADMIN, PM, ENGINEER, CONSULTANT, OWNER, WORKER}),
    _p("ifc.upload", "models", "Upload IFC models", "Add a new model revision.",
       {ADMIN, PM, ENGINEER}),
    _p("ifc.manage_version", "models", "Manage model versions",
       "Activate, supersede or remove a model revision.", {ADMIN, PM}),
    _p("document.upload", "models", "Upload documents", "Add drawings and documents.",
       {ADMIN, PM, ENGINEER}),

    # --- AI decision support ------------------------------------------------
    _p("ai.view_insights", "ai", "View AI insights", "Read AI findings and suggestions.",
       {ADMIN, PM, ENGINEER, CONSULTANT}),
    _p("ai.review_insight", "ai", "Act on AI insights",
       "Acknowledge, dismiss or resolve an AI insight.", {ADMIN, PM, ENGINEER, CONSULTANT}),
    _p("ai.promote_insight", "ai", "Turn an AI insight into work",
       "Create a formal issue or task from an AI insight.", {ADMIN, PM, ENGINEER}),
)

BY_CODE: dict[str, Permission] = {item.code: item for item in CATALOGUE}
GROUPS: tuple[str, ...] = tuple(dict.fromkeys(item.group for item in CATALOGUE))


def role_defaults(role: UserRole) -> set[str]:
    """Every permission the role holds before any configuration is applied."""
    return {item.code for item in CATALOGUE if role in item.default_roles}


def is_known(code: str) -> bool:
    return code in BY_CODE
