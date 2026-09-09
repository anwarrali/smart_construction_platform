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
    #: Authority that belongs to the consulting office and to nobody outside
    #: it. Reviewing work, approving a design change, certifying a payment
    #: claim, verifying evidence, running the project team — these are what the
    #: office is engaged to do, so a contractor, subcontractor or client can
    #: never hold them however their role is configured.
    #:
    #: This replaces a scattering of `is_consultant_engineer(...)` guards that
    #: enforced the same thing by asking which side of the retired
    #: owner/contractor/consultant triangle somebody was on. Expressed here it
    #: holds everywhere at once — endpoints, Voice, the AI tool layer — instead
    #: of wherever a guard was remembered.
    #:
    #: `office_only` is a *default*, not a wall. It says an external role never
    #: **inherits** the permission — which is the rule that matters, because
    #: inheritance is where a mistake is silent. It does not stop an
    #: administrator deliberately granting the code to one named person on one
    #: named project, and it should not: an office that wants its main
    #: contractor to maintain the construction programme, or to raise and close
    #: tasks on their own scope, is describing a real arrangement, and a flag
    #: that forbade it would be the platform overruling the office about its
    #: own project.
    office_only: bool = False
    #: The wall. Authority an external participant never holds, at any price —
    #: no role, no override, no misconfiguration.
    #:
    #: Two kinds of thing qualify, and the test for each is concrete:
    #:
    #:   * **Certification.** Exercising it is the consulting office putting
    #:     its name to something: approving work, verifying a report,
    #:     approving a design change, certifying a payment claim, confirming
    #:     evidence, acting on the office's own review material. The office is
    #:     professionally answerable for these; a contractor signing off their
    #:     own work is the failure the whole arrangement exists to prevent.
    #:   * **Access governance.** Exercising it decides who else gets in —
    #:     project membership, parties, external invitations, document shares,
    #:     and the project settings that configure the review workflow itself.
    #:     Granting one of these to an outsider hands them the key to grant
    #:     themselves the rest.
    #:
    #: Everything else that is `office_only` is office *work*, and work can be
    #: delegated. See docs/RBAC.md, "The two ceilings".
    never_external: bool = False
    aliases: tuple[str, ...] = field(default=())


def _p(code, group, label, description, roles, *, project_scoped=True,
       admin_locked=False, office_only=False, never_external=False):
    return Permission(code, group, label, description, frozenset(roles),
                      project_scoped=project_scoped, admin_locked=admin_locked,
                      office_only=office_only,
                      # Certification and access governance are always both.
                      # Nothing is `never_external` without also being
                      # `office_only`: the wall implies the default.
                      never_external=never_external or False)


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
       "Add or remove people from a project and set their role on it.", {ADMIN, PM},
       office_only=True, never_external=True),
    # Editing project setup was administrator-only at the endpoint. The default
    # records that, rather than widening access as a side effect of making the
    # check configurable; an administrator can grant it to managers in one click.
    _p("project.edit", "project", "Edit project details",
       "Change project information, dates and settings.", {ADMIN}, office_only=True, never_external=True),
    _p("project.manage_reminders", "project", "Configure reminders",
       "Set reminder intervals, quiet hours and escalation.", {ADMIN, PM}),
    # Deletion is its own code because it is its own act. `delete_project` was
    # gated on `is_admin(user.role)`, and the tempting migration was to reuse a
    # code that happened to resolve identically — `project.edit` measures 0
    # differences against it on this database. But `project.edit` means "change
    # project information, dates and settings", and an office that granted a
    # role the ability to correct a start date would have silently granted it
    # the ability to destroy the project: 42 tables carry a foreign key to
    # `projects.id` and 39 of them cascade, so this removes every task,
    # document, attachment, model revision, site report and finding along with
    # the row. A permission whose label does not say that is a trap.
    #
    # `project_scoped=True` adds something `is_admin` never had: `has_permission`
    # also requires project access for a project-scoped code, so the grant
    # cannot reach a project the holder is not on.
    #
    # Not `admin_locked`: an office should be able to withhold deletion from
    # itself. Defaulting to {ADMIN} alone keeps today's answer — see
    # `role_templates`, where `technical_director` explicitly declines it.
    _p("project.delete", "project", "Delete a project",
       "Permanently delete a project and everything recorded against it.",
       {ADMIN}, office_only=True, never_external=True),

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
    _p("task.create", "tasks", "Create tasks", "Add new tasks to a project.", {ADMIN, PM},
       office_only=True),
    _p("task.edit", "tasks", "Edit tasks", "Change task details and assignment.", {ADMIN, PM},
       office_only=True),
    # Descriptive entry: `update_task_progress` in app.api.tasks gates on
    # "the assigned PM of this project OR the assignee of this specific task",
    # not on role membership. Routing this through `require` would let anyone
    # holding the role-level default edit the progress of tasks they are not
    # assigned to — a real widening, not a neutral refactor — so the ownership
    # check stays the enforcement and this entry stays descriptive.
    _p("task.update_progress", "tasks", "Update task progress",
       "Record progress and submit work for review.", {ADMIN, PM, ENGINEER, WORKER}),
    # "See the whole task list", as opposed to seeing the work you hold or
    # review. The default is exactly the set that got no filter before: an
    # administrator, a project manager, the legacy consultant role and the
    # client, whose portal shows project progress. Engineers are narrowed —
    # and what they are narrowed *to* is decided by data, not by a role: the
    # work assigned to them, plus the work they are the named reviewer for.
    _p("task.view_all", "tasks", "See every task",
       "See the project's whole task list, not only your own work.",
       {ADMIN, PM, CONSULTANT, OWNER}),
    _p("task.review", "tasks", "Review submitted work",
       "Approve, reject or request rework on submitted task work.",
       {ADMIN, PM, CONSULTANT, ENGINEER}, office_only=True, never_external=True),
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
       "Shift planned dates and cascade the effect downstream.", {ADMIN, PM},
       office_only=True),

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
       "Approve or reject a submitted site report.", {PM}, office_only=True, never_external=True),
    _p("issue.create", "field", "Raise issues", "Open a project issue.",
       {ADMIN, PM, ENGINEER, CONSULTANT}),
    _p("issue.resolve", "field", "Resolve issues", "Close or resolve a project issue.",
       {ADMIN, PM}, office_only=True),

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
    # Reviewing a client-facing cost validation. `app.api.cost_validations`
    # gated this on `is_consultant_engineer`; the authority it was reaching for
    # is the same one that approves a design change, so it gets a code of its
    # own and the same default.
    _p("cost_validation.review", "requests", "Review cost validations",
       "Approve or reject a submitted cost validation.", {ADMIN, PM, ENGINEER},
       office_only=True, never_external=True),
    _p("design_change.approve", "requests", "Approve design changes",
       "Give a design change its official approval.", {ENGINEER}, office_only=True, never_external=True),

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
       "Acknowledge, dismiss or resolve an AI insight.", {ADMIN, PM, ENGINEER, CONSULTANT},
       office_only=True, never_external=True),
    _p("ai.promote_insight", "ai", "Turn an AI insight into work",
       "Create a formal issue or task from an AI insight.", {ADMIN, PM, ENGINEER},
       office_only=True, never_external=True),

    # --- Office administration (RBAC v2) ------------------------------------
    # The consulting office configures itself: roles, disciplines and its own
    # settings. Defaults reproduce what the endpoints these replace already
    # required — `/company/settings` was `require_admin`, so is this.
    _p("org.manage_roles", "platform", "Manage roles",
       "Create, rename and delete roles, and choose what each one may do.",
       {ADMIN}, project_scoped=False, admin_locked=True),
    _p("org.manage_disciplines", "platform", "Manage disciplines",
       "Maintain the office's list of engineering disciplines.", {ADMIN},
       project_scoped=False),
    _p("org.manage_settings", "platform", "Manage office settings",
       "Change office details, branding and report templates.", {ADMIN},
       project_scoped=False),

    # --- External parties (RBAC v2) -----------------------------------------
    # A project's client, main contractor and subcontractors are recorded on
    # the project, not in the office's staff directory. Managing them is the
    # same authority that already manages the project team.
    _p("project.manage_parties", "project", "Manage project parties",
       "Record the client, contractors and other external parties on a project.",
       {ADMIN, PM}, office_only=True, never_external=True),
    _p("project.invite_external", "project", "Give external people access",
       "Grant someone outside the office access to this project.", {ADMIN, PM},
       office_only=True, never_external=True),
    _p("document.share_external", "models", "Share documents externally",
       "Make a document readable by an external party on this project.",
       {ADMIN, PM}, office_only=True, never_external=True),
    # One permission for one idea: "your view of this project is not narrowed
    # to your own disciplines". It governs documents, site reports and issues,
    # because the platform applied the *same* rule to all three and expressed
    # it three times — as `is_consultant_engineer(...)` plus a comparison
    # against `EngineerProfile.discipline`. Three copies of a rule is how they
    # drift; this is the rule, named once.
    #
    # The default reproduces what the affiliation checks decided: an
    # administrator, a project manager and an ordinary Engineer saw everything
    # on the project, while a consultant-side reviewer was narrowed to their
    # own discipline. The `senior_engineer` template — where those reviewers
    # land — withholds it, which is how they keep the narrower view they had.
    #
    # It has no bearing on external participants. What an outsider reads is
    # decided by what was shared with their party, checked first, so this can
    # never widen one.
    _p("project.view_all_disciplines", "models", "See work in every discipline",
       "Read the project's documents, reports and issues without discipline narrowing.",
       {ADMIN, PM, ENGINEER}),

    # --- Field evidence (RBAC v2) -------------------------------------------
    # These replace `is_worker()` and the main-contractor-engineer reviewer
    # gate. Both are INTENTIONAL behaviour changes — worker accounts are being
    # removed and site engineers take over the submitting side — so the
    # defaults name the roles that inherit the work rather than reproducing
    # the old ones. See docs/CONSULTING_OFFICE_REDESIGN.md §7.
    _p("field_evidence.submit", "field", "Submit field evidence",
       "Record photos, notes and voice observations from site.", {PM, ENGINEER}),
    _p("field_evidence.verify", "field", "Verify field evidence",
       "Confirm or reject a submitted field evidence package.", {PM, ENGINEER},
       office_only=True, never_external=True),

    # --- IFC verbs that had no catalogue entry ------------------------------
    # `can_ifc` used to hold these as a private role dict. The defaults below
    # are copied from that dict verbatim so switching the gate over changes
    # nobody's access; an administrator can then configure them.
    _p("ifc.compare", "models", "Compare model versions",
       "Open a comparison between two revisions of a model.",
       {ADMIN, PM, ENGINEER, CONSULTANT}),
    _p("ifc.review_finding", "models", "Review coordination findings",
       "Act on a clash or coordination finding.", {ADMIN, PM, ENGINEER, CONSULTANT}),
    _p("ifc.review_suggestion", "models", "Review model suggestions",
       "Accept or dismiss a suggestion raised against the model.",
       {ADMIN, PM, ENGINEER}),
    _p("ifc.download", "models", "Download model files",
       "Download the original IFC file.", {ADMIN, PM, ENGINEER, CONSULTANT}),
    # Its own code rather than an alias for `ifc.manage_version`: the retired
    # dict gave MANAGE_LINK to engineers and MANAGE_VERSION only to
    # administrators and managers, so folding them together would have
    # narrowed what engineers can do.
    _p("ifc.manage_link", "models", "Link model elements to work",
       "Connect a model element to a task, issue or document.",
       {ADMIN, PM, ENGINEER}),

    # --- Opening a project module (RBAC v2) ---------------------------------
    # Four codes that name a question the platform never wrote down: "may this
    # person open the Documents / Site Reports / Issues / Design Changes part
    # of a project at all".
    #
    # It was answered, until now, by the frontend's per-role URL table — which
    # is why an office's own internal engineer could `document.upload` but had
    # no documents page to upload from, and why the same page existed at four
    # URLs with four different role lists. **No list endpoint behind these has
    # ever gated on role.** `list_documents`, `list_site_reports`, `list_issues`
    # and `list_design_changes` all check project access and then scope rows —
    # by party, by discipline, by assignment. So these codes do not narrow or
    # widen any *data*; they name the navigation decision that was being made
    # in a route table, and put it where an office can change it: a role that
    # should not see the Issues tab can now have it taken away, which was
    # previously impossible without a release.
    #
    # Defaults are every role that can be on a project, because that is exactly
    # what the endpoints already allow. External participants hold them too and
    # must: a contractor opening Documents sees what was shared with their
    # party, and nothing else — `document_access` decides that, first, before
    # any permission is consulted.
    _p("document.view", "models", "Open project documents",
       "See the project's document library, scoped to what you may read.",
       {ADMIN, PM, ENGINEER, CONSULTANT, OWNER}),
    _p("site_report.view", "field", "Open site reports",
       "See the project's site reports, scoped to what you may read.",
       {ADMIN, PM, ENGINEER, CONSULTANT, OWNER}),
    _p("issue.view", "field", "Open project issues",
       "See the project's issue register, scoped to what you may read.",
       {ADMIN, PM, ENGINEER, CONSULTANT, OWNER}),
    _p("design_change.view", "requests", "Open design changes",
       "See the project's design changes, scoped to what you may read.",
       {ADMIN, PM, ENGINEER, CONSULTANT, OWNER}),

    # The client portal — the executive project view the owner dashboard
    # renders. `get_owner_dashboard` gated it on `role in {OWNER, ADMIN}`; this
    # is that check, named, with the same holders. Deliberately **not**
    # `office_only`: the client is an external party and this is the one view
    # that exists for them, so the ceiling that strips the office's own
    # authority must not strip this too.
    _p("client_portal.view", "requests", "Open the client portal",
       "See the executive project overview prepared for the client.",
       {ADMIN, OWNER}),

    # --- Operations Voice performed with no catalogue permission ------------
    # Four voice capabilities carried `permission_code=None` and were gated by
    # the registry's own role set alone — the second authorization system this
    # redesign removes. Defaults mirror the role sets they replace
    # (`_ALL_ENGINEERS` = project manager + engineer).
    _p("task.add_note", "tasks", "Add notes to tasks",
       "Record a note against a task.", {ADMIN, PM, ENGINEER}),
    _p("task.comment", "tasks", "Post on a task discussion",
       "Write in a task's discussion thread.", {ADMIN, PM, ENGINEER}),
    _p("message.send", "requests", "Send project messages",
       "Message another participant on the project.", {ADMIN, PM, ENGINEER, CONSULTANT}),
    _p("message.send_client", "requests", "Send client updates",
       "Send an update to the project's client.", {ADMIN, PM, ENGINEER}),
)

BY_CODE: dict[str, Permission] = {item.code: item for item in CATALOGUE}
GROUPS: tuple[str, ...] = tuple(dict.fromkeys(item.group for item in CATALOGUE))


def role_defaults(role: UserRole) -> set[str]:
    """Every permission the role holds before any configuration is applied."""
    return {item.code for item in CATALOGUE if role in item.default_roles}


def is_known(code: str) -> bool:
    return code in BY_CODE
