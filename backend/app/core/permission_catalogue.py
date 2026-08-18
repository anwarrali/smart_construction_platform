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
    # Wired, but not through a plain `require(...)` call like most of this
    # catalogue: `app.core.deps.user_has_project_access` / `accessible_project_ids`
    # (which `require`/`has_permission` themselves use to enforce every
    # project-scoped permission, this one included) and
    # `app.api.projects._scoped_projects_query` call
    # `app.services.authorization.can_view_all_projects_effective` directly as
    # their sole "sees everything" gate. That is safe from the
    # resolver-depends-on-itself cycle this used to be blocked on specifically
    # *because* this permission is `project_scoped=False` — see
    # `can_view_all_projects_effective`'s docstring for the full argument.
    # Deliberately not `admin_locked`: revoking it does not strip an
    # administrator's ability to administer (that is `platform.manage_users`
    # / `platform.manage_permissions`, both locked), only their bypass of
    # project membership — which they can always restore via Access Control.
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
    # Descriptive entry: `list_tasks` / `get_tasks_by_project` in app.api.tasks
    # do not gate on this code. Visibility is row-level, not role-level — an
    # Engineer sees only tasks they are assigned to, a Consultant Engineer sees
    # only tasks under active review in their discipline, a Worker sees only
    # their own assignments — computed with per-row query filters, not a single
    # boolean. A `require` gate answers "can this role see the list endpoint at
    # all", which every one of these roles already can; it cannot express which
    # rows they get back, so migrating it would just add a redundant check on
    # top of the filtering that actually does the work.
    _p("task.view", "tasks", "View tasks", "See the project task list.",
       {ADMIN, PM, ENGINEER, CONSULTANT, OWNER, WORKER}),
    _p("task.create", "tasks", "Create tasks", "Add new tasks to a project.", {ADMIN, PM}),
    _p("task.edit", "tasks", "Edit tasks", "Change task details and assignment.", {ADMIN, PM}),
    # Descriptive entry: `update_task_progress` in app.api.tasks gates on
    # "the assigned PM of this project OR the assignee of this specific task",
    # not on role membership. Routing this through `require` would let anyone
    # holding the role-level default edit the progress of tasks they are not
    # assigned to — a real widening, not a neutral refactor — so the ownership
    # check stays the enforcement and this entry stays descriptive.
    _p("task.update_progress", "tasks", "Update task progress",
       "Record progress and submit work for review.", {ADMIN, PM, ENGINEER, WORKER}),
    _p("task.review", "tasks", "Review submitted work",
       "Approve, reject or request rework on submitted task work.",
       {ADMIN, PM, CONSULTANT, ENGINEER}),
    # Investigated (not assumed) whether excluding ENGINEER here — and so a
    # real Consultant Engineer, whose `User.role` is ENGINEER — is a leftover
    # of the legacy CONSULTANT-role migration or the actual intended
    # architecture: it is the latter. The pre-catalogue hardcoded rule this
    # default reproduces already read "Engineers are blocked from the
    # portfolio view" with no affiliation carve-out (see
    # test_rbac_schedule_and_ai_insights.py's module docstring), the
    # frontend has never had a Gantt/critical-path route for either Engineer
    # variant (unlike every other Consultant-Engineer-facing feature, which
    # does have one), and a Consultant Engineer's actual review workflow —
    # task.review, design_change.approve, cost_validation.review, IFC
    # findings — is scoped to individual assigned items, never portfolio
    # schedule data. `CONSULTANT` here is therefore the literal, unreachable
    # legacy role (`UserCreateByAdmin` persists any request for it as unified
    # Engineer, so it grants nobody anything in practice) — not a stand-in
    # for real Consultant Engineers, who this default has always excluded
    # same as Main Contractor Engineers. See
    # test_a_consultant_engineer_is_intentionally_excluded_from_the_portfolio_schedule
    # for the full evidence chain. Still configurable per person/project
    # through Access Control if a specific case ever needs it.
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
    # Verification rests with the assigned Project Manager alone, same shape as
    # `design_change.approve` resting with the assigned consultant: the
    # catalogue default covers the whole PM role (matching the dashboard's
    # "site report awaiting your verification" prompt, which every Project
    # Manager sees), and `manageable_project` layers the "only your own
    # assigned project" restriction on top inside the endpoint — a grant here
    # can never let a PM verify a report on a project they do not manage.
    _p("site_report.verify", "field", "Verify site reports",
       "Approve or reject a submitted site report.", {PM}),
    _p("issue.create", "field", "Raise issues", "Open a project issue.",
       {ADMIN, PM, ENGINEER, CONSULTANT}),
    _p("issue.resolve", "field", "Resolve issues", "Close or resolve a project issue.",
       {ADMIN, PM}),

    # --- Client communication ----------------------------------------------
    _p("owner_request.create", "requests", "Submit client requests",
       "Raise a request on behalf of the client.", {ADMIN, PM, OWNER}),
    # Descriptive entry: `update_owner_request` in app.api.collaboration checks
    # "is admin/the project's PM" or "is the request's assigned engineer" (plus
    # a narrower requester-only path for re-opening from NEEDS_CLARIFICATION),
    # not role membership — different target states even require different
    # combinations of those three. A role-level `require` would let any
    # Engineer on the project answer a request assigned to a different
    # Engineer, which the assignment check exists specifically to prevent.
    _p("owner_request.review", "requests", "Answer client requests",
       "Respond to, accept or reject a client request.", {ADMIN, PM, ENGINEER}),
    _p("design_change.propose", "requests", "Propose design changes",
       "Turn an accepted request into a proposed design change.", {ADMIN, PM, ENGINEER}),
    # Official approval of a design change rests with the assigned consultant
    # alone. A Consultant Engineer's `User.role` is ENGINEER (with
    # `engineer_affiliation="external_consultant"`) — `UserCreateByAdmin`
    # persists any request for the legacy CONSULTANT role that way — so
    # `CONSULTANT` can never be a real `User.role` and was never actually
    # reachable as a default here. Default is ENGINEER, matching
    # `design_change.propose` and the `ifc.view`/`ifc.upload` shape below:
    # `approve_design_change`/`reject_design_change` (app.api.design_changes)
    # hold the real gate via `is_consultant_engineer` plus a discipline check,
    # same reason those two entries stay descriptive rather than routing the
    # finer-than-role restriction through `require` alone.
    _p("design_change.approve", "requests", "Approve design changes",
       "Give a design change its official approval.", {ENGINEER}),

    # --- Models and documents ----------------------------------------------
    # ifc.view / ifc.upload / ifc.manage_version are descriptive entries.
    # Enforcement for IFC endpoints is `can_ifc` in app.services.ifc_policy,
    # which is strictly richer than a role check: it also gates on the
    # IFC_FEATURE_ENABLED flag, restricts ENGINEER to the active
    # main-contractor/consultant-engineer affiliation (not the bare role), and
    # further gates UPLOAD behind the separate IFC_ENGINEER_UPLOAD_ENABLED
    # flag. Routing these through `require` would silently drop that
    # granularity down to a plain role check. Keep `can_ifc` as the source of
    # truth; these entries exist so the roles are visible in the admin matrix.
    _p("ifc.view", "models", "View IFC models", "Open models, hierarchy and properties.",
       {ADMIN, PM, ENGINEER, CONSULTANT, OWNER, WORKER}),
    _p("ifc.upload", "models", "Upload IFC models", "Add a new model revision.",
       {ADMIN, PM, ENGINEER}),
    _p("ifc.manage_version", "models", "Manage model versions",
       "Activate, supersede or remove a model revision.", {ADMIN, PM}),
    _p("document.upload", "models", "Upload documents", "Add drawings and documents.",
       {ADMIN, PM, ENGINEER}),

    # --- AI decision support ------------------------------------------------
    # The frontend has always routed Owner to the AI Intelligence page
    # (RoleGuard allows admin/owner/project_manager/engineer/consultant) and the
    # endpoint has always allowed it via the IFC "VIEW" verb; the catalogue entry
    # just never listed it. Recorded here to match what was already shipped, not
    # to grant anything new. Worker holds no route to this page today.
    _p("ai.view_insights", "ai", "View AI insights", "Read AI findings and suggestions.",
       {ADMIN, PM, ENGINEER, CONSULTANT, OWNER}),
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
