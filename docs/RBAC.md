# Roles, permissions and project parties

How the platform decides what somebody may do. The configurable model is the
only one: the retired role enum and its columns are gone from the schema. The proposal this implements is
[CONSULTING_OFFICE_REDESIGN.md](CONSULTING_OFFICE_REDESIGN.md); this document
describes what is actually in the code.

---

## The shape

```
Organization  (a consulting office — the `companies` table)
  │
  ├── Role                       configurable, org-owned or a shared template
  │     └── RolePermission       one row per permission the role grants
  │
  ├── Discipline                 professional specialization; grants nothing
  │     └── ifc_disciplines[]    the bridge to IFC classification names
  │
  └── OrganizationMembership     "I work for this office", and my role here

Project (owned by the office)
  ├── ProjectParty               the client, contractors, subcontractors
  │     └── parent_party_id      a subcontractor's main contractor
  │
  └── ProjectMember
        ├── project_role_id      may differ from the person's office role
        ├── party_id             NULL = office staff; set = external
        └── ProjectMemberDiscipline
```

**A party is scoped to one project and holds no link to an organization row.**
A contractor works with many offices and an office with many contractors; the
project is where they meet. Nothing in the schema joins one firm to another.

---

## The one authorization path

Everything asks `app.services.authorization.has_permission`. Voice, the AI tool
layer, the agents, document retrieval and the IFC workspace all arrive there;
none of them keeps a role table any more.

```
effective_permissions(user, project_id):
    1. office role's permissions  ∪  project role's permissions   (rbac.resolved_permissions)
         − every office_only permission, if the person is external   ← role default
    2. UserPermissionOverride, global
    3. UserPermissionOverride, this project
    ─────────────────────────────────────────────────────────────
    ∩ {} if the account is not ACTIVE
    − every non-project-scoped permission, if the person is external
    − every never_external permission, if the person is external      ← the wall
```

Union between office and project role, because "Senior Engineer in the office,
Project Manager on Project A" has to mean both. Narrowing is still available
through the per-person override layer.

Note the two strips are at *different* points and cover *different* sets, and
that is the whole of the `office_only` redesign — see *The two ceilings*. The
first is about what a role confers, and is wide, because inheritance is where a
mistake is silent. The second is about what an administrator deliberately
typed, and is narrow, because an office delegating work to its contractor is a
real arrangement rather than an error.

Rules no configuration can raise:

- a deactivated or suspended account holds nothing;
- an **external** participant never holds a permission that is not
  project-scoped;
- an **external** participant never holds the office's certification or access
  governance — refused at grant time in the API *and* stripped again at
  resolution time, so a mistake cannot become a breach.

`has_permission` additionally re-checks project access for every project-scoped
code, so granting a permission never smuggles in access to a project somebody
is not on.

---

## Roles

A role is a named bundle of permissions. `organization_id IS NULL` is a shared
template every office starts with; editing one **copies it into the office
first**, so one office renaming "Site Engineer" does not rename it elsewhere.

Seeded templates: `org_admin`, `office_director`, `technical_director`,
`project_manager`, `senior_engineer`, `engineer`, `site_engineer`,
`bim_engineer`, `cad_technician`, `surveyor`, `document_controller`,
`office_staff`, and the four external ones — `client_representative`,
`contractor_representative`, `subcontractor_representative`,
`external_reviewer`. Plus `archived_field_staff`, which retired worker accounts
sit on and which holds nothing.

Rules the API enforces:

| Rule | Why |
| --- | --- |
| A permission must exist in the catalogue | A role granting something no code checks is a promise the platform cannot keep |
| An external role cannot hold a non-project-scoped permission | A contractor must never reach office administration |
| The `org_admin` role cannot be deleted, and keeps its `admin_locked` permissions | Somebody must always be able to administer |
| A role in use cannot be deleted | Deleting authority out from under people should fail loudly |

`Role.rank` is display order. The frontend's old `ROLE_HIERARCHY` was consulted
as seniority; nothing reads rank as authority now.

**The permission catalogue itself stays in code** (`app.core.permission_catalogue`).
Offices compose roles out of the permissions the application checks; they do not
invent permissions.

---

## Work scope — what you can see

`app.services.work_scope` holds the three ideas that replaced
`is_main_contractor_engineer` and `is_consultant_engineer` (78 call sites across
19 files). Each is written once and used everywhere:

| Concept | Question | Decided by |
| --- | --- | --- |
| **Task scope** | Which of a project's tasks do I see? | `task.view_all`, else *assigned to me* ∪ *I am the named reviewer* |
| **Discipline scope** | Which disciplines narrow my view? | `project.view_all_disciplines`, else my assigned disciplines |
| **Responsibility** | Do I carry the site? | `ProjectMember.is_site_engineer` |

The task narrowing is a **union**, and that is the point. The retired code asked
which side of the owner/contractor/consultant triangle you were on and gave you
one answer, so somebody who both held work and reviewed other work could not be
represented. Now they see both.

Nothing here is a new authorization system: every answer comes from
`has_permission` or from a relationship the platform already records — task
assignment, `ProjectConsultantReviewer`, the person's disciplines.

## Project reach — the record and the work

Reaching a project has two levels (QA-06B, 2026-10-17):

| Level | What it opens | Who reaches it without being on the team |
| --- | --- | --- |
| **Record** | the project in the list, its details and settings, its team and parties | `platform.view_all_projects` — the Office Administrator by default |
| **Work** | tasks, schedule, documents, models, issues, reports, messages, voice, agents | `platform.work_in_all_projects` — General Manager and Technical Director |

Owners, the assigned manager and active members reach both. The checks are
`user_can_see_project_record` and `user_has_project_access` in
`app.core.deps`. A catalogue permission marked `registry=True`
(`project.manage_members`, `project.edit`, `project.delete`,
`project.manage_parties`, `project.invite_external`) resolves its project
check at the record level; every other project-scoped permission needs the work
level. `effective_permissions(user, project_id)` applies the same rule, so
`GET /access-control/me?project_id=` tells the interface what the person can
open *in that project*, and the workspace uses that answer.

This is what keeps system administration from being project participation:
the administrator can staff any project, and opens its work only by joining the
team. Migration `i6f3a9c4d170` gave the new code to every role and override
that held `platform.view_all_projects`, except the seeded Office Administrator,
so no one else's reach changed.

## The two ceilings

Some permissions are the consulting office's own job. But "the office's job" is
two different things wearing one word, and collapsing them into a single
non-overridable flag turned a security guarantee into a barrier the office
could not reason about or lift.

They are separated now.

### The wall — `Permission.never_external`

Twelve codes an external participant never holds, at any price: no role, no
override, no misconfiguration. `rbac.NEVER_EXTERNAL` is the list, stripped in
`effective_permissions` **after** overrides, so a mistake in Access Control
cannot become a breach. Two kinds of thing qualify, and the test for each is
concrete:

**Certification** — exercising it is the office putting its name to something.
`task.review`, `site_report.verify`, `design_change.approve`,
`cost_validation.review`, `field_evidence.verify`, `ai.review_insight`,
`ai.promote_insight`. The office is professionally answerable for these, and a
contractor signing off their own work is the failure the whole arrangement
exists to prevent.

**Access governance** — exercising it decides who else gets in.
`project.manage_members`, `project.manage_parties`, `project.invite_external`,
`document.share_external`, `project.edit`. Hand one of these to an outsider and
they can grant themselves the rest.

### The default — `Permission.office_only`

Sixteen codes — the twelve above plus `task.create`, `task.edit`,
`schedule.edit`, `issue.resolve` — that an external **role** never inherits.
Stripped in `rbac.resolved_permissions`, which is the step that decides what a
*role* confers.

The strip is wider there than in `effective_permissions`, and deliberately.
Role inheritance is where a mistake is silent: the seeded contractor template
inherits an Engineer's permissions, so an office renaming or re-permissioning a
role could otherwise hand a contractor authority nobody decided to give. The
role editor refuses it outright, with a message pointing at the alternative.

### Why the four are delegable

An office that wants its main contractor to maintain the construction
programme, or to raise and close tasks on their own scope, is describing a real
arrangement. A flag that forbade it would be the platform overruling the office
about its own project — and the office would work around it by making the
contractor internal, which is far worse than the thing being prevented.

So those four are office work by *default* and grantable by *decision*: one
named person, one named project, through Access Control, which is an act
somebody performs and signs rather than a property a role quietly carries. The
grant endpoint refuses a `never_external` code on an external participant and
says why, so an administrator learns the rule at the moment they meet it rather
than by watching a grant silently do nothing.

What never travels with delegation is approval authority. `test_7d` asserts
both halves in one breath: the contractor can now do the work, and still cannot
sign it off.

## Disciplines

A discipline is a specialization. It grants nothing — it narrows what a
permission applies to: which documents, which review queue, which findings,
which notifications.

Many-to-many on both `users` and `project_members`, so one engineer can cover
Mechanical *and* Electrical — which `EngineerProfile.discipline` could not
express — and can be brought onto a project for one of their specialisms.

`ifc_disciplines` maps an office's vocabulary onto the IFC classification names
(`STRUCTURAL`, `PLUMBING`, `FIRE_PROTECTION`, `SITE_CIVIL`…). `mep` covers four
of them, so a reviewer scoped to MEP matches a coordination finding tagged
`PLUMBING`. The two vocabularies had no relationship before, which made that
match impossible.

**Discipline is never an input to `require()`.** A check that used to read "is
an electrical engineer" reads "holds the permission *and* their disciplines
intersect the item's". Permission first, discipline second.

---

## Internal vs external

|  | Office staff | External (contractor, subcontractor, client) |
| --- | --- | --- |
| `ProjectMember.party_id` | NULL | points at a `ProjectParty` |
| Role | any `is_internal_only` role | only non-internal roles |
| Office-wide permissions | yes | never |
| Certification / access governance | yes | **never**, at any price |
| Office *work* (`task.create`, `task.edit`, `schedule.edit`, `issue.resolve`) | yes | not inherited, but delegable per person per project |
| Documents | discipline scope, or `project.view_all_disciplines` | **deny by default** — explicit share only |
| Site Engineer flag | yes | no |
| Agent notifications | yes | never |

A contractor or subcontractor is a participant in the project, not a member of
the office. They can be given real capabilities — updating their own work,
filing evidence, raising issues, uploading documents, messaging, and by
explicit delegation raising and closing tasks or maintaining the programme —
and none of it makes them internal. What they cannot acquire, by any route, is
the office's professional sign-off or the ability to widen their own access.

### Document access

`app.services.document_access` is the one implementation; the documents API,
RAG retrieval, entity sharing and the AI tool layer all narrow through it.
Layers, first match wins:

1. project access
2. **party scope** — an external participant reads what was shared with their
   party, plus their own uploads
3. `project.view_all_disciplines` — office staff who hold it see everything
4. discipline scope — office staff who do not

The party check comes **first**, and that ordering is the whole security
property: the seeded contractor template inherits an Engineer's permissions,
which include `project.view_all_disciplines`, so checking that first would hand a
contractor the entire project.

The client is the one external party with a rule of its own, and it is the rule
the client portal already had: official project files plus evidence of approved,
completed work. Sharing adds to it; nothing takes it away.

---

## Field evidence

`FieldSubmission` was built when workers were platform users. It is not a worker
feature — it is the structured field-evidence primitive (photos with direction,
categories, AI metadata, voice origin), and a Site Engineer produces exactly
that. The author column is `submitted_by_id`; who may fill it is
`field_evidence.submit`, and who may confirm it is `field_evidence.verify`.

`Project.field_evidence_verification_required` lets an office turn the second
step off per project: the handshake exists because a worker's report of their
own progress needed a qualified person to confirm it, and when the qualified
person is the one filing, an office may decide the report is the record.
Defaults to true.

---

## Site reports and site responsibility

Site Engineer is a **project responsibility**, not a role and not a discipline.
A project may have any number of them, of any disciplines, and the same person
may carry it on one project and not another — `ProjectMember.is_site_engineer`.

`SiteReport.discipline_id` records which discipline a visit covered, resolved
most-specific-first: the linked task's discipline, else the reporter's single
discipline on that project, else left open. Somebody covering several
disciplines with no task attached leaves it open on purpose — guessing which
visit it was would be worse than saying nothing. Without the column a project
with three site engineers produces three reports a day that cannot be told
apart or routed.

## Notification routing

`app.services.agents.finding_routing` decides who hears about an agent finding,
from permission, discipline and project responsibility:

1. the accountable principal, always — an unrouted finding is worse than an
   imprecise one;
2. anybody whose disciplines intersect the finding's;
3. site engineers, for a finding with no discipline, or one about a specialism
   they have not been narrowed to;
4. never an external participant — agent findings are the office's own review
   material.

Eligibility is checked first: a recipient must hold `ai.review_insight` on the
project, so routing can never notify somebody about a page they would be
refused. A finding tagged with an IFC class (`PLUMBING`) matches an office
discipline (`mep`) through `Discipline.ifc_disciplines`.

The decision to notify *at all* is unchanged — `decide_notification` still
weighs confidence, severity and certainty, and `dedupe_key` still means one
notification per finding, ever.

## One source of authority

```
User ──org_role_id──▶ Role ──▶ RolePermission ──▶ effective_permissions
```

That is the whole model. `users.org_role_id` is `NOT NULL`, so every account
holds an office role, and nothing else about an account — no enum, no
affiliation string, no project-role label, no claim in a token — is an input
to any decision.

**Retired-model dependencies in runtime code: 0.** Counted over code tokens in
`backend/app` (comments and docstrings excluded): no read of `users.role`,
`engineer_affiliation`, `role_on_project`, `legacy_role`,
`legacy_affiliation`, `RolePermissionOverride` or `UserRole`. Those names
survive in exactly one place, the offline legacy migration tool
(`app.db.legacy_rbac` and `app.db.rbac_backfill`), which nothing at runtime
imports — see *Upgrading a legacy database*.

What replaced each retired decision, so nobody has to rediscover it:

| Was | Is |
| --- | --- |
| "is the Project Manager" (`role == PROJECT_MANAGER`) on create/update | `authorization.can_run_project` — staffable and holds `project.manage_members` |
| "is the owner" (`role == OWNER`) | `authorization.can_be_project_client` — active, external, holds `client_portal.view`; on a project, `rbac.is_client_participant` (a CLIENT party) |
| "is an administrator" (`role == ADMIN`) | the permission the endpoint needs; for "who administers the office", `rbac.holds_office_admin_role` (the undeletable role) |
| who may hold a task (`role in {ENGINEER, CONSULTANT, PM}`) | `task_assignment.assignee_refusal` — active member holding `task.update_progress` |
| who may review (`external_consultant`) | `task_assignment.reviewer_refusal` — active office member holding `task.review` |
| broadcasts and group conversations (ADMIN/PM) | `message.broadcast` (office-only) |
| photo categories ("PM or Admin") | `project.manage_members` on the project |
| AI-proposed actions by role | one permission per action (`app.ai.action_rules.ACTION_PERMISSIONS`) |
| the tenant office (an ADMIN's company) | the company of the undeletable role's holder |
| labels shown to people and models | `rbac.role_code` / `rbac.member_role_code` / `rbac.role_label_for` |

## Roles are data

The 18 seeded templates are defined in `app.core.role_templates` with
**explicit** permission sets — named bases (`OFFICE_ADMINISTRATION`,
`PROJECT_LEADERSHIP`, `ENGINEERING`, `CLIENT`) plus per-template additions and
withholdings — never derived from a retired role.
`tests/test_role_templates.py` pins every template's exact grant set.

`rbac.seed_roles` is idempotent: it creates a missing template and adds a
template's missing permissions, and never removes a permission or touches an
office's own role. An office customizes by editing a role on the Office roles
page (`PUT /organization/roles/{id}/permissions`); editing a shared template
copies it into the office first. The retired role-by-permission matrix
(`/access-control/roles`) and its write-through table are gone.

From then on the copy *is* that role for the office: the role list shows it in
the template's place, and `rbac.office_role_id` resolves the permissions of
anyone in the office who still points at the template through the copy (their
office is their company, else the tenant). Before 2026-10-22 accounts kept the
template's permissions, so an office's edit reached nobody — a grant of
`platform.create_project` to Engineers showed on screen and applied to no
engineer. Deleting the copy hands its holders back to the template.

## Customizing permissions, end to end

What an administrator configures is what the server enforces, at the next
request. Pinned by `tests/test_rbac_customization.py`.

### Three layers, one resolver

| Layer | Stored in | Edited on | Applies to |
| --- | --- | --- | --- |
| **Role** | `role_permissions` | Office roles page — `PUT /organization/roles/{id}/permissions` | everyone the role *governs* |
| **Person, everywhere** | `user_permission_overrides`, `project_id` NULL | Access Control › People — `PUT /access-control/users/{id}` | one person |
| **Person, one project** | `user_permission_overrides`, `project_id` set | the same, with a project selected | one person, one project |

An override row is **tri-state**: `allowed = true` grants, `allowed = false`
denies, and *no row* inherits from the role. "Use role default" deletes the
row; an absent override is never read as a denial. No migration was needed —
the table always had this shape.

`authorization.effective_permissions(user, project_id)` is the only resolver.
Its precedence, as implemented:

1. **Inactive account → nothing.** Not overridable.
2. Governing office role ∪ project role (`rbac.resolved_permissions`); an
   external participant's role contributes nothing office-wide or office-only.
3. Person override, everywhere — grant adds, deny removes.
4. Person override, this project — wins over 3.
5. Office administrator: `admin_locked` codes restored (cannot be denied).
6. External participant: everything office-wide and every `never_external`
   code stripped **after** overrides — a grant cannot cross the wall.
7. In a project's context, a project-scoped code survives only where the
   person reaches the project (work level, or record level for `registry`
   codes). **A grant never brings project membership with it**;
   `has_permission` re-checks the same.
8. Anything else: denied.

### Which role governs

Editing a shared template copies it into the office (`_editable_role`), and
accounts keep pointing at the template. `rbac.office_role_id` resolves such an
account through the office's copy, so the role the editor shows is the role
that applies. The role list marks a role `isTemplate` until its first edit,
and counts the template holders a copy governs. Another office's accounts keep
the template.

### Why, per permission

`GET /access-control/users/{id}[?project_id=]` returns, besides the effective
set, `decisions[]` — for every catalogue code `held`, `reason`, `roleGrants`
and the explicit `override` at that scope — and `governingRoleName` /
`governedByOfficeCopy`. `held` is membership of `effective_permissions`, not a
recomputation; only the reason is derived (`explain_permissions`), and a test
asserts the two agree for every code. Reasons: `granted_by_role`,
`granted_by_project_role`, `granted_to_user`, `granted_on_project`,
`admin_locked`, `denied_for_user`, `denied_on_project`, `blocked_external`,
`blocked_project_access`, `account_inactive`, `not_granted`.

### When a change takes effect

- **Server:** at the affected person's next request. Nothing caches effective
  permissions beyond one request (`office_role_id` and the two
  `*_all_projects_effective` answers are memoized on the request's `User`
  object). No restart, no re-login.
- **Web client:** the permission snapshot is re-read when the tab regains
  focus and whenever the server answers 403 (`permission.store.revalidate`,
  throttled to once per 5 s), keeping the previous answer while it loads. An
  administrator editing their own account or a role is refreshed at once.
  A stale snapshot can only hide or show a control — the endpoint re-checks.

### Module view permissions are enforced by the API

Until 2026-10-23 `task.view`, `site_report.view`, `issue.view` and
`design_change.view` guarded routes only: revoking one hid the page and the
API kept answering. Each module's read endpoints now `require` it, and the
cross-project lists narrow through `authorization.projects_with_permission`.
`project.invite_external` was registered and checked nowhere; adding a member
for an outside party (`partyId` set) now requires it. `message.send` (starting
a conversation), `message.send_client` (writing to the client) and
`task.comment` (posting on a task) were checked by voice only and are now
enforced on the REST endpoints too. Default holders of both
are unchanged, so no default behaviour moved. The full inventory is
[PERMISSION_COVERAGE.md](PERMISSION_COVERAGE.md).

### No identity shortcuts in front of a permission

Until the second pass of 2026-10-23, most task operations asked "is this caller
`project.project_manager_id`?" and treated the permission as a second gate at
best. A grant to anybody else showed the control and failed — Rana, granted
`task.create`, got "Only the assigned Project Manager can create project
tasks". The rule now is the permission and project access:

| Operation | Permission | Plus |
| --- | --- | --- |
| Create a task (also from an IFC suggestion or an AI insight) | `task.create` | project access |
| Edit, assign, delete, reorder tasks | `task.edit` | project access |
| Start, update, submit, complete your work | `task.update_progress` | assigned to the task |
| Review submitted work | `task.review` | named reviewer, or also `task.edit` |
| Task dependencies, milestones, shifts | `schedule.edit` | project access |
| Edit or reassign someone else's issue | `issue.resolve` | project access |
| Delete a project | `project.delete` | project record access; permanent |
| Share a document with an outside party | `document.share_external` | can read the document; party on the same project |

`project_manager_id` is still read for *routing* — who is notified, whose
authority an automatic agent run borrows — never as an authorization answer in
these paths. A handful of checks still read "permission **or** assigned
manager"; they are listed under *Policy decisions* in
[PERMISSION_COVERAGE.md](PERMISSION_COVERAGE.md).

Each permission's extra conditions are in `permission_catalogue.PREREQUISITES`
and shown next to it in both editors, so an administrator sees, for instance,
that `task.update_progress` only applies to tasks assigned to the person.

### Verification codes when editing permissions

Production: changing one person's permissions (`admin.change_permissions`,
one code covers a sitting of `STEP_UP_VALIDITY_MINUTES`) and changing
somebody's role (`admin.change_user_role`) ask for an e-mailed code. Editing a
role's permission set does not — that was already so, and is recorded under
*Open policy questions*.

Development and QA: set

```
ENVIRONMENT=development        # or local, test, qa
STEP_UP_PERMISSION_EDIT_BYPASS=true
```

and those two purposes no longer ask. What does not change: sign-in, the
`platform.manage_permissions` / `platform.manage_users` checks, the catalogue
and wall validations, and every other step-up purpose (password change,
password reset, deactivate, delete). Each skipped challenge writes a
`step_up_bypassed_development` audit row. No code is generated or echoed, and
`OTP_DEV_ECHO_ENABLED` stays off.

Safeguards: the settings **refuse to load** with the switch on unless
`ENVIRONMENT` is `development`, `local`, `test` or `qa` (staging is excluded
on purpose), and `step_up_service.permission_edit_bypass_active` re-checks the
environment on every call. The test suite runs production-like by default
(`conftest._step_up_as_in_production`), whatever a developer's `.env` says.

### Adding a permission

1. Add it to `app.core.permission_catalogue.CATALOGUE` with the right flags
   (`project_scoped`, `registry`, `office_only`, `never_external`,
   `admin_locked`).
2. Give it to the templates that should hold it by default in
   `app.core.role_templates`, and update `tests/test_role_templates.py`. For an
   existing database, a data migration grants it to existing roles (see
   `h5e2f8b3c069`, `i6f3a9c4d170`).
3. Enforce it **on the server** at every endpoint it governs — `require(db,
   user, code, project_id)` — and narrow cross-project lists with
   `projects_with_permission`.
4. Then the client: `PermissionGuard` on the route, `hasCapability` on the
   action, the sidebar entry in `navigation.ts`.
5. Test both outcomes through the API, including a revoke by override: add a
   row to `READ_MATRIX` / `WRITE_MATRIX` in `tests/test_permission_capabilities.py`.
   If the operation has an extra condition, add it to `PREREQUISITES`. Never
   gate on `project_manager_id` or a role name.
6. Regenerate the inventory: `python scripts/permission_inventory.py
   --json ../docs/permission_inventory.json --markdown
   ../docs/permission_inventory_table.md` (from `backend/`). A new code must
   not land as `ui-only` or `unused`.

### Open policy questions

- **Role edits take no verification code** in production, while a single
  person's override does. Requiring one would change the production policy,
  so it was left as it was; it is the product owner's call.
- **`message.send` covers starting a conversation, not replying.** A client
  (who does not hold it by default) can still answer a conversation the office
  opened. Gating replies too would be a new rule.
- **Legacy Consultant accounts** no longer post task comments or write to the
  client through REST (2026-10-23). That matches the retired Consultant policy
  the role was frozen from — intentional, not a regression; grant per person
  or move the account to Senior Engineer if the office wants otherwise. See [PERMISSION_COVERAGE.md](PERMISSION_COVERAGE.md).

## How accounts are written

Every path assigns the role **before** the row is written, through
`rbac.apply_org_role`, which sets `org_role_id` and `is_internal` together.
Nothing fills the column during a flush, and the schema refuses a row without
one.

| Path | Role |
| --- | --- |
| `POST /users` → `create_provisioned_user` | the requested `orgRoleId` (required); refuses an archived role and refuses no role |
| `bootstrap_admin` | `org_admin`, through `rbac.apply_template_role`; refuses rather than write an administrator without it |
| `seed_demo` | the template named by each demo account's `role_code` |
| `rbac_backfill` (legacy databases only) | the template `legacy_rbac.template_for_legacy` maps the retired pair to |

## A fresh deployment

1. `alembic upgrade head` — **schema only**. No migration seeds roles; a
   migration must not import application constants.
2. `python -m app.db.bootstrap_admin --if-configured` — takes a PostgreSQL
   advisory lock (`BOOTSTRAP_LOCK_KEY`), so concurrent replicas serialize;
   seeds disciplines and role templates through `rbac.seed_fresh_database`
   (only on a database with no roles and no accounts); creates the first
   administrator on `org_admin` when the `BOOTSTRAP_ADMIN_*` variables are
   set. With none set it still seeds the roles (`initialize_rbac`), so a
   database is never left without them. Re-running changes nothing.
3. The demo seed, if enabled, after that.

These are steps of the image's `CMD`, the one start sequence every
environment runs — Docker Compose included (`tests/test_start_sequence.py`).

No manual RBAC step exists. `tests/test_fresh_deployment_rbac.py` runs this
against a database migrated from nothing on the test server.

## Upgrading a legacy database

A database whose accounts still carry the retired `users.role` /
`engineer_affiliation` columns is carried across once, offline:

```
alembic upgrade c84d6e2f1a37        # the last revision with the legacy columns
python -m app.db.rbac_backfill      # --dry-run to preview
alembic upgrade head                # e1a9c3d5f720 removes the legacy schema
```

- The contract migration **refuses** while any account lacks an office role:
  on such a database the retired columns are the only record of what those
  people may do.
- The backfill is one transaction. An `engineer_affiliation` it does not
  recognise raises `UnknownAffiliation` and **rolls the whole run back** —
  guessing high would hand an outsider internal access, guessing low would
  strip a legitimate account. Fix the row and re-run.
- It is idempotent, folds the retired role-keyed overrides into the seeded
  roles, creates the CLIENT and contractor parties, and writes the document
  shares that preserve the access contractors already had.
- On a fresh or already-contracted database it changes nothing and says so.

`tests/test_fresh_deployment_rbac.py` and `tests/test_rbac_redesign.py` run
this path end to end on throwaway databases at the pre-contract revision.

### What the contract migration removed

`e1a9c3d5f720` dropped `users.role`, `users.engineer_affiliation`,
`project_members.role_on_project`, `roles.legacy_role`,
`roles.legacy_affiliation`, the `role_permission_overrides` table and the
`user_role` PostgreSQL type, and made `users.org_role_id` `NOT NULL`. Its
downgrade restores the schema (nullable) and fills `users.role` from each
account's office role; affiliations, project-role labels and override rows
are not reconstructed — restore those from a backup taken before upgrading.

## The API

- **Tokens carry identity only** (`sub`, `email`, expiry, type). No role
  claim; login and refresh responses carry no role either. Authorization is
  resolved from the database on every request.
- `GET /access-control/me` — the caller's effective permissions; what the web
  and mobile clients decide everything from.
- `GET /access-control/permissions` — the catalogue, with `projectScoped`,
  `adminLocked`, `officeOnly`, `neverExternal`.
- `GET /users/eligible?purpose=project_owner|project_manager` and
  `GET /projects/{id}/eligible-members?purpose=task_assignee|reviewer` — the
  candidates the server itself would accept, by the same rule the assigning
  endpoint applies, so a picker never offers somebody who is then refused.
- `POST /users` requires `orgRoleId`; user and member payloads carry
  `orgRole` / `projectRoleName`, never a role enum.

## The clients

The web app and the mobile app decide every access question with a catalogue
code from `/access-control/me` (`useRole().hasCapability`, `Capabilities.has`)
and show the office's own role name from `orgRole`. There is no static role
table, no role mapper and no role-named landing logic: the dashboard is chosen
by capability, and every route sits behind `PermissionGuard`.
`frontend/src/utils/noRetiredRoles.test.ts` fails if any frontend source reads
a retired role field again.

## Out of scope, recorded

- **`EngineerProfile.discipline`** still exists and is read by
  `rbac.disciplines_for_user` as a fallback for an account with no
  `user_disciplines` rows. It is a discipline, which narrows and never grants,
  so it is not part of the authorization model this document closes.
- **`/field-submissions/worker-dashboard`** is an alias kept for mobile builds
  already installed; delete it once a build carrying `/my-field-work` has
  shipped.

## Decisions, answered

| Question | Answer | Where it landed |
| --- | --- | --- |
| How is an account created? | Under the office's own configured role, with its own disciplines. | `UserCreateByAdmin.org_role_id` (required) / `discipline_ids`, the `UserForm` |
| One workspace URL or four? | One, `/projects/:projectId/…`, with the retired prefixes kept as redirects. | `LegacyProjectPrefixRedirect`, `projectRoutes.ts` |
| Is a consultant-side account office staff? | **Yes.** The office *is* the consultant; review authority is `task.review`, held by its own roles. | `reviewer_refusal`, `legacy_rbac.LEGACY_ROLE_MAP` → `senior_engineer` |
