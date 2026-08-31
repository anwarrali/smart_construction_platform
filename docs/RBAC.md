# Roles, permissions and project parties

How the platform decides what somebody may do, after the consulting-office
redesign. The proposal this implements is
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
    2. RolePermissionOverride       (pre-backfill fallback path only)
    3. UserPermissionOverride, global
    4. UserPermissionOverride, this project
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

## Legacy dependency audit — final

The redesign began with 78 legacy `user.role` comparisons. **Six remain, and
none of them decides anything.**

| What is left | Count | Why |
| --- | --- | --- |
| `authorization.legacy_effective_permissions` | 1 | The retired resolution, preserved verbatim. It is the equivalence gate's other half — the only evidence the migration was safe. It is never called by the application. |
| Writes to `users.role` / `engineer_affiliation` | 3 | Both columns are still `NOT NULL`, so provisioning still fills them. Derived from the office role (`Role.legacy_role`), never read back to decide anything. |
| Comments | 2 | Prose recording what was removed and why. |

Everything else went. In particular:

- **Project scope** no longer has a `PROJECT_MANAGER` early return.
  `user_has_project_access`, `accessible_project_ids` and `manageable_project`
  resolve one union — owner, assigned manager, or active member — then the
  permission. Declared as `project_manager_membership_honoured`.
- **The client** is a `ProjectParty(kind=CLIENT)`, asked through
  `rbac.is_client_participant`, not `UserRole.OWNER`.
- **Who may be staffed** is `rbac.staffable_filter` / `is_staffable`: active,
  and not parked on a role that exists only to hold history. One predicate,
  used by the candidate list, the assignment endpoint and the user search, so
  they cannot disagree.
- **The retired helpers are gone**: `require_roles`,
  `is_main_contractor_engineer`, `is_consultant_engineer` and their two
  `require_*` wrappers had no callers.
- **Two account-creation endpoints are gone**: `POST /users/engineers` and
  `POST /users/owners` each hardcoded one identity and neither client called
  them. `POST /users` takes `orgRoleId` and `disciplineIds`.

## The contract step

**Done.** `RBAC_REQUIRE_DB_ROLES` has been retired, not merely enabled.

It gated the pre-backfill fallback in `rbac.resolved_permissions`. That fallback
is removed, and with it the three bridges that depended on the state it
tolerated: `work_scope.sees_all_disciplines`' affiliation branch,
`document_access._pre_migration_scope`, and the unmigrated-admin clause in
`effective_permissions`. An account without a role now raises `UnmigratedUser`.

Nothing can create such an account. `create_provisioned_user` assigns a role on
both paths, and `app.db.user_role_backstop` — now unconditional — fills the
column for any `User` written anywhere else, moving `is_internal` with it. A
setting whose only remaining effect would be to break the system is worse than
no setting, so it is gone rather than defaulted to true.

`legacy_effective_permissions` and `RolePermissionOverride` survive as the
equivalence gate's evidence. `PUT /access-control/roles` writes *through* to the
configured roles that provision the legacy value being edited, so the older
Access Control screen still changes what it says it changes; without that it
would have returned 200 and done nothing.

## Migration state

Expand → backfill → switch → contract. Currently **switched**; the contract step
has not run.

- `app.db.rbac_backfill` — idempotent, `--dry-run` supported. Maps every account
  onto a role, seeds disciplines, creates parties from existing memberships, and
  writes explicit document shares reproducing the access contractors already had.
- `app.db.rbac_equivalence` — compares the retired resolution against the live
  one for every (user, project) pair. Differences are allowed only when they
  match a declared change in `INTENTIONAL_CHANGES`.

A user with no `org_role_id` resolves through the catalogue defaults for their
legacy `User.role`. That fallback is keyed off the column rather than a feature
flag, so a half-finished backfill locks nobody out.
`RBAC_REQUIRE_DB_ROLES=true` turns such an account into a hard error instead.

### Is `RBAC_REQUIRE_DB_ROLES` safe to enable?

**Yes.** The suite passes with it on, the equivalence gate passes with it on,
and nothing can create an account it would reject.

The flag gates one thing: whether an account **without** `org_role_id` resolves
through the fallback or raises. It has nothing to do with the legacy role
comparisons listed below — those read `users.role` directly and would keep
working with the flag either way. Conflating the two is the easiest mistake to
make here.

| Condition | State |
| --- | --- |
| No existing active account lacks `org_role_id` | **Yes** — `active_users_missing_roles` reports 0, asserted by a test |
| No API creation path can produce one | **Yes** — `create_provisioned_user` assigns a role on both paths |
| No *other* code path can produce one | **Yes** — `app.db.user_role_backstop`, a `before_flush` listener, fills the column and `is_internal` for any account that arrives without them |
| Suite passes with the flag on | **Yes** — 1820 passed, 17 skipped, 0 failed |
| Equivalence gate passes with the flag on | **Yes** — 0 unexpected differences |

The 17 skipped tests are the ones that describe the fallback itself: twelve
configure a role through `RolePermissionOverride`, which `effective_permissions`
consults only while an account has no `org_role_id`, and one asserts that an
unmigrated account keeps working. They are skipped rather than deleted because
the fallback is still load-bearing production code until the contract migration
removes it, and until then it needs a test. The behaviour they cover —
an administrator can change what a role may do — is covered on the *new*
mechanism by `test_organization_api.py` and by `test_7b` in the security
regression suite.

Getting here surfaced a live bug worth recording. On the migrated path,
`admin_locked` codes were restored by `resolved_permissions` **before** the
per-person override layer ran, so a `UserPermissionOverride` could strip
`platform.manage_users` off the office administrator — the exact lockout the
lock exists to prevent. The legacy path re-applied them after overrides, so the
asymmetry was invisible until every account had a role. Both paths now restore
them last.

The flag is left **off** in the committed configuration. Turning it on is an
operator decision about a specific database: it converts a silent fallback into
a loud failure, which is worth having, but it should be switched deliberately
rather than shipped flipped.

### Contract-step preconditions, as of this pass

| Precondition | State |
| --- | --- |
| Account creation off the legacy enum | **Yes** — `orgRoleId` + `disciplineIds`; the enum path survives only as a compatibility shim |
| All frontend callers migrated | **Yes** — `RoleGuard` and both affiliation guards are deleted; every route is behind `PermissionGuard` |
| Deep links preserved | **Yes** — retired prefixes redirect, asserted per prefix in `projectRoutes.test.ts` |
| All tests migrated | **Yes** — no fixture treats Worker as an active role |
| No API creation path leaves an unmigrated account | **Yes** — asserted by `test_the_legacy_creation_path_still_assigns_a_database_role` |
| Suite passes with `RBAC_REQUIRE_DB_ROLES=true` | **Yes** — 1820 passed, 17 skipped (the fallback's own tests), 0 failed |
| Project membership UI free of the legacy role select | **Yes** |
| Worker no longer an active product role | **Yes** — no provisioning path, no business logic, no vocabulary, no fixture |
| Authorization equivalence holds | **Yes** — 0 unexpected differences |
| **All production callers of `users.role` migrated** | **No — 78 remain.** This is the one outstanding blocker. |

**Still to do (contract step):** drop `users.role`,
`project_members.role_on_project`, `role_permission_overrides.role`,
`users.engineer_affiliation`, `engineer_profiles.discipline`, then the
`user_role` and `engineer_discipline` PostgreSQL types. `ALTER TYPE … DROP VALUE`
does not exist, so the `WORKER` value can only go when the whole type does —
which is why all three tables must be migrated in one window.

---

## Legacy role checks still in production code

Seventy-two `user.role == UserRole.X` comparisons remain outside the migration
machinery, down from seventy-eight. None is reached through `has_permission`;
they read the retired column directly, which is why the contract migration
cannot drop `users.role` yet. They fall into five shapes, and the shape decides
what each needs:

| Cat. | Shape | Count | What it needs |
| --- | --- | --- | --- |
| **A** | `role == ADMIN`, used as a sees-everything bypass | 15 | Mostly duplicates `platform.view_all_projects`. Mechanical, one endpoint at a time. |
| **B** | `role == PROJECT_MANAGER and project.project_manager_id == user.id` | 10 | An **ownership** check wearing a role check. Six were removed this pass: both write paths validate `project_manager_id` to be an active PROJECT_MANAGER, so the role half was always implied by the id comparison. The rest are negative forms (`... != user.id`) where dropping it would refuse everybody, and they need reading individually. |
| **C** | `role == OWNER`, narrowing what the client sees | 9 | Should read the CLIENT party (`membership_context(...).party.kind`). `document_access` already does, keeping the role check only as the pre-backfill bridge. |
| **D** | `role == ENGINEER`, narrowing to own work | 23 | Most are shadowed by `work_scope`; the rest need a per-endpoint decision about which permission expresses the narrowing. |
| **F** | `role == PROJECT_MANAGER` without an ownership test | 13 | Each is a distinct product question and is not safe to answer mechanically. |
| **E** | `role == CONSULTANT` | 1 | Unreachable on `User.role`. One was removed as dead code; the survivor is inside a set membership where removing it changes nothing. |

The one in `authorization.manageable_project` deserves naming separately. It
reads "a project manager may only act on the project they are assigned to", and
translating it needs a decision rather than a refactor: under configurable
roles, *who* is confined to their own projects? Everybody without
`platform.view_all_projects` is the obvious answer and would narrow an engineer
who has been granted `project.manage_members` — which may be right, but it is a
behaviour change in the most central helper in the system and should be made
deliberately.

**None of these blocks `RBAC_REQUIRE_DB_ROLES`** — see above. They block the
*contract* step only.

## Decisions, answered

Three of the four questions that blocked this work have been answered by the
confirmed product direction, and the answers are now in the code:

| Question | Answer | Where it landed |
| --- | --- | --- |
| How is an account created? | Under the office's own configured role, with its own disciplines. | `UserCreateByAdmin.org_role_id` / `discipline_ids`, `Role.legacy_role`, the rewritten `UserForm` |
| One workspace URL or four? | One, `/projects/:projectId/…`, with the retired prefixes kept as redirects. | `LegacyProjectPrefixRedirect`, the rewritten router, `projectRoutes.ts` |
| Is a consultant-side account office staff? | **Yes.** The office *is* the consultant; review authority is a permission its own roles hold. | `add_project_member` site-responsibility rule, `LEGACY_ROLE_MAP` → `senior_engineer` |

The fourth is a release question rather than a code one:

### `/field-submissions/worker-dashboard`

The mobile source calls `/my-field-work`; the alias exists for builds already
on somebody's phone. It is the last Worker-shaped string reachable at runtime,
and it is deliberately kept: removing it 404s an app somebody is still using.
Delete it once a build carrying the rename has shipped — a one-line change.

## What still has to be decided before the contract step

### The 78 legacy role checks

Categorised in the table above. Groups **B** (ownership checks wearing a role
check) and **A** (admin bypasses that duplicate `platform.view_all_projects`)
are mechanical and low-risk. Groups **D** and **F** are not: each is a distinct
product question, and answering them in bulk would be inventing rules rather
than migrating them. Examples of the questions in **F**:

- *May a project manager add anyone the office employs to their project, or
  only engineers?* (`add_project_member`, `remove_project_member`)
- *May anyone other than the assigned manager submit a cost validation?*
  (`cost_validations.py:66`)
- *Should the field assistant answer for somebody who is neither an engineer
  nor a manager — a surveyor, say?* (`field_assistant.py:44-58`)

Each of those is a sentence of product intent, not a refactor.

### `EngineerProfile.discipline`

Still read by `disciplines_for_user` as the pre-backfill source. Its
replacement (`user_disciplines`) is populated for every migrated account, so
this is removable once the fallback goes — but the two must go together.
