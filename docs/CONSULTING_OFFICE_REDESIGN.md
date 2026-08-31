# Consulting-Office Redesign — Impact Analysis and Proposal

**Status:** implemented through the *switch* step; the contract migration has
not run. What is actually in the code is described in [RBAC.md](RBAC.md) — read
that first. This document is kept as the analysis the implementation was built
from, and its "Open decisions" section at the end is still open: decisions 1, 2
and 4 there map onto the DECISIONS REQUIRED section of RBAC.md, and they are
what blocks the contract migration.
**Scope:** re-centre the platform on an *integrated engineering / consulting office*, with
configurable roles, disciplines independent of roles, internal staff vs. external parties,
no worker accounts — while preserving Phases 1–8 (AI agents, Voice, RAG, IFC, Site Reports,
proactive notifications).

---

## 0. Headline finding

**The foundation is in better shape than the brief assumes, and worse in three specific places.**

Phase 7 already left a written note anticipating this exact redesign
([docs/AGENTS.md](AGENTS.md), "Deferred: the Organization / RBAC redesign"). I verified every
claim in it against the code. It is accurate. What it says is:

Already flexible, needs **no** redesign:

| Thing | Evidence |
| --- | --- |
| Permissions are configurable per role and per user | `RolePermissionOverride`, `UserPermissionOverride` ([app/models/permission.py](../backend/app/models/permission.py)), resolved centrally in [app/services/authorization.py](../backend/app/services/authorization.py) |
| A named permission catalogue exists | 30 codes in [app/core/permission_catalogue.py](../backend/app/core/permission_catalogue.py) |
| Discipline is *already* separate from role | `ProjectMember.project_discipline`, `EngineerProfile.discipline` |
| Site Engineer is *already* an unbounded per-project flag | `ProjectMember.is_site_engineer`, indexed — any number per project |
| Per-project custom labels exist | `ProjectMember.assignment_title` |
| Per-project, per-person permission grants exist | `UserPermissionOverride.project_id` |
| Consultant authority is already project-scoped and discipline-or-centralized | `ProjectConsultantReviewer`, `ConsultantEngineerScope` |
| AI agents and the AI tool layer are role-independent | No agent, analyzer, orchestrator or tool branches on `UserRole`; everything goes through `has_permission` |

Genuinely rigid, and the real work:

| Constraint | Where | Effect |
| --- | --- | --- |
| `UserRole` is a 6-value PostgreSQL enum | `users.role`, `project_members.role_on_project`, `role_permission_overrides.role` | No Surveyor, BIM/CAD, MEP, Resident Engineer, Technical Director without a migration |
| `EngineerDiscipline` is a 4-value PG enum | `engineer_profiles.discipline` | No MEP, BIM, surveying; cannot express one engineer covering Mechanical *and* Electrical |
| `engineer_affiliation` is a free `String(40)` carrying the internal/external axis | `users.engineer_affiliation` — 40 call sites | The single most load-bearing undocumented column in the system |
| `Company` is a tenant that is deliberately **not** enforced | [app/api/projects.py:122-138](../backend/app/api/projects.py) | Company is a directory label, not an organization boundary |
| ~40 direct `UserRole.X` checks in API handlers | `projects.py` (51), `site_reports.py` (14), `tasks.py` (13), `documents.py` (12), `ifc_policy.py` (10) | The catalogue exists but a large fraction of endpoints still bypass it |
| Voice gates capabilities on 4 coarse role names | `Capability.roles` in [app/services/voice_capabilities.py](../backend/app/services/voice_capabilities.py) | Voice **is** the second role system §14 warns against — it already exists |
| Frontend has a full static duplicate role table | [src/utils/permissions.ts](../frontend/src/utils/permissions.ts), `MODULE_ACCESS`, `RoleGuard`, per-role route prefixes | Adding a role means editing 6+ frontend files |

**So the redesign is narrower than §9 implies.** We are not building an RBAC foundation from
nothing; we are (a) turning two enums into tables, (b) making the internal/external axis
explicit instead of a magic string, (c) making `Company` mean *consulting office*, (d) finishing
the migration of role checks onto the catalogue that Phase 6/7 started, and (e) deleting the
worker role. That is a real but bounded piece of work.

---

## 1. Current architecture — what the system assumes today

### 1.1 Identity and authorization

```
Company (weak, unenforced)
   └─ User (role: 6-value enum, engineer_affiliation: string, company_id)
         └─ EngineerProfile (discipline: 4-value enum, can_act_as_project_manager)

Project (company_id, owner_id, project_manager_id, consultant_approval_mode)
   ├─ ProjectMember (role_on_project: same 6-value enum, project_discipline: string,
   │                 is_site_engineer: bool, assignment_title: string)
   ├─ ProjectConsultantReviewer (user, discipline|NULL = centralized)
   └─ ConsultantEngineerScope (consultant → named engineers)

Permission resolution (app/services/authorization.py):
   role catalogue default
     → RolePermissionOverride (whole role, platform-wide)
       → UserPermissionOverride (person, everywhere)
         → UserPermissionOverride (person, this project)
   + inactive/suspended = no permissions at all
   + project-scoped permission additionally requires project access
   + admin_locked permissions can never be revoked from ADMIN
```

This resolution chain is good and should survive untouched.

### 1.2 The real role model in production

The declared `UserRole` enum has 6 values, but the *effective* role model has 8, because
`engineer_affiliation` sub-divides `ENGINEER`:

| Effective role | How it is represented |
| --- | --- |
| Admin | `role=ADMIN` |
| Project Manager | `role=PROJECT_MANAGER` |
| Internal Engineer | `role=ENGINEER`, `affiliation=internal_engineer` |
| Main Contractor Engineer | `role=ENGINEER`, `affiliation=main_contractor` |
| Consultant Engineer | `role=ENGINEER`, `affiliation=external_consultant` |
| Owner | `role=OWNER` |
| Worker | `role=WORKER` |
| Consultant (legacy, dead) | `role=CONSULTANT` — **unreachable**: `UserCreateByAdmin` rewrites any request for it into `ENGINEER` + `external_consultant` ([app/schemas/user.py:141-145](../backend/app/schemas/user.py)) |

`UserRole.CONSULTANT` is a **dead role on `User.role`** but is still a **live value on
`ProjectMember.role_on_project`** — an external consultant is stored as `role=ENGINEER` globally
and `role_on_project=CONSULTANT` on the project. That divergence is the clearest existing proof
that the product already needs org-role ≠ project-role.

### 1.3 The org model the system actually implements

The comment at [app/api/projects.py:122-138](../backend/app/api/projects.py) is explicit and
important:

> *"No `company_id` filter here, deliberately: cross-company collaboration is how this app is
> actually modelled, not an edge case. The seeded demo project is owned by one company while its
> Main Contractor engineers and reviewing consultants belong to two different companies
> entirely, joined only through `ProjectMember`; company_id is … not a project-visibility
> boundary."*

So today: **owner-company + contractor-company + consultant-company, meeting on a project.**
`app/db/seed_demo.py` seeds exactly that. This is the model §10 says to replace.

`Company` is used for only three things: scoping the user directory
([app/api/users.py:62,89,314](../backend/app/api/users.py)), `/company/settings`, and as a
denormalized label. Nothing enforces it. That makes repurposing it *cheap*.

### 1.4 Where authorization is actually decided

Four parallel systems, in order of how modern they are:

1. **Catalogue + overrides** — `require(db, user, code, project_id)`. The intended path.
2. **`app/core/deps.py` helpers** — `is_main_contractor_engineer`, `is_consultant_engineer`,
   `is_worker`, `user_has_project_access`, `get_manageable_project_or_403`. Hardcoded role/affiliation.
3. **Per-feature policy modules** — `ifc_policy.can_ifc` (its own role→verb dict),
   `document_access.readable_documents_query` (owner scope + consultant-discipline scope),
   `messaging_policy`, `field_submission_policy`, `collaboration_policy`, `photo_archive_policy`.
4. **Inline `if current_user.role == …` in handlers** — ~40 sites, densest in `projects.py`.

Layers 2–4 are what must converge onto layer 1.

### 1.5 AI, Voice, RAG, IFC as they stand

- **Agents** ([app/services/agents/](../backend/app/services/agents/)) — 5 agents, each declaring
  `allowed_tools` + a single `permission_code`. `AgentContext` is the only path to data.
  **Zero role branches.** Verified.
- **AI tool layer** ([app/services/ai_tools/](../backend/app/services/ai_tools/)) — one `ToolSpec`
  row per operation, each with a catalogue permission code or an explicit reason for `None`.
  Reads role only to *display* it (`get_project_users`). **Zero role branches.**
- **Proactive analysis** ([agents/event_subscriber.py](../backend/app/services/agents/event_subscriber.py))
  — event-triggered runs borrow the **project manager's** authority, deliberately; a project
  with no active PM is skipped rather than escalated.
- **Voice** — `Capability.roles: frozenset[str]` over `{worker, contractor_engineer,
  external_consultant, project_manager}`, checked in three places: the capability registry, the
  rules engine, and `write_tools`. **This is a second authorization system**, exactly what §14
  forbids. It also silently drops `internal_engineer`, `owner` and `admin` — `voice_role()`
  returns the raw enum value for them, which matches no capability, so they get an empty
  capability list.
- **RAG** — retrieval is authorized *before* embedding search: `readable_document_ids` →
  `retrieval.search`. Two role-conditional scopes inside it: `OWNER` sees only
  contract/permit + evidence of approved-completed tasks; consultant engineers see only their
  own `EngineerProfile.discipline`. Both are role-hardcoded.
- **IFC** — `IFC_PERMISSIONS` dict maps 8 verbs → role sets, plus two feature flags and an
  affiliation check. Catalogue entries `ifc.view` / `ifc.upload` / `ifc.manage_version` exist but
  are explicitly **descriptive only** — `can_ifc` is the real gate.

---

## 2. Domain problems — every place the old assumptions live

Ordered by how much they block the new product direction.

### P1 — The organization is a construction-project consortium, not an office
`Company` is unenforced by design; project visibility deliberately crosses companies.
There is no concept of "the office I work for" that owns projects, staff, templates and branding.
`Project.company_id` is `ON DELETE SET NULL` and nullable — i.e. a project may belong to no
company at all.

### P2 — `UserRole` is a 6-value PG enum used by three tables
`users.role`, `project_members.role_on_project`, `role_permission_overrides.role` all bind the
PostgreSQL type `user_role`. Any new role is a DDL change plus a code change. `ROLE_HIERARCHY`
in the frontend even assigns numeric seniority to those six values.

### P3 — `EngineerDiscipline` has 4 values and is single-valued
`architectural | civil | electrical | mechanical`. Cannot express MEP, BIM, survey, geotechnical,
QS, or one engineer covering Mechanical **and** Electrical. `consultant_approval_policy.normalize_discipline`
already flattens `structural→civil`, `hvac/plumbing/firefighting→mechanical`, `mep_electrical→electrical`
— i.e. the product has already outgrown the enum and is coping with a lossy alias map.

### P4 — Two unrelated discipline vocabularies
`EngineerDiscipline` (4) vs. the IFC/agent set (`STRUCTURAL, MECHANICAL, ELECTRICAL, PLUMBING,
FIRE_PROTECTION, ARCHITECTURAL, SITE_CIVIL …`) used by `ifc_intelligence`, `IFCElement.discipline`,
`IFCCoordinationFinding.affected_disciplines_json`. They do not map. A consultant scoped to
`mechanical` cannot be matched against an IFC finding tagged `PLUMBING`.

### P5 — `engineer_affiliation` is an undeclared enum in a `String(40)`
Three magic values, validated only in `UserCreateByAdmin`, read in 40 places including
`deps.py`, `ifc_policy`, `document_access`, `projects.py`, `tasks.py`, `messaging_authorization`,
`voice_capabilities`, `field_submission_policy`, and the frontend (`EngineerAffiliation` type,
route prefixes, `MODULE_ACCESS` key derivation). It is doing the job of the internal/external
axis §11 asks for, badly.

### P6 — Contractor is modelled as an *employment attribute of a person*
`main_contractor` is a property of a `User`, not a relationship between an organization and a
project. Consequences: a project cannot have two contractors; a contractor firm has no record;
a subcontractor cannot be expressed at all; the same engineer cannot be a main-contractor
engineer on project A and a subcontractor engineer on project B.

### P7 — Worker is a first-class user role with real data behind it
`UserRole.WORKER` + `is_worker()` appear in: `field_submissions` (`worker_id` FK, `ondelete=RESTRICT`),
`field_submission_photos` → `photo_category_assignments`, photo archive, messaging groups
(`"WORKERS"`), `worker_recipient_ids`, `worker_can_message`, voice capability
`CREATE_FIELD_SUBMISSION`, `voice_command_service` suggestion filtering, `projects.py` team
filters, `tasks.py` visibility branches, `ifc_policy` VIEW set, catalogue defaults for
`task.view` / `task.update_progress` / `ifc.view`, the frontend sidebar/routes/permission table,
mobile `RoleConstants`, and ~29 backend test files.

### P8 — Owner is both a *user role* and a *project column*
`Project.owner_id` FK to `users`, `UserRole.OWNER`, `owner_document_scope`, `SEND_OWNER_UPDATE`
voice capability, `OwnerRequest` collaboration entity, `/owner-dashboard`, `ProjectViewState`
("what changed since I was last here" — built for the owner). Owner is deeply integrated as a
*client portal*, which is genuinely valuable and should not be discarded.

### P9 — Site Engineer status is correct but under-powered
`ProjectMember.is_site_engineer` is right. But `add_project_member` refuses it unless the user
is `role=ENGINEER` **and not** `external_consultant` ("Only contractor-side Engineers can be
assigned as Site Engineers") — which in the new model is exactly backwards: site engineers will
be *consulting-office* staff.

### P10 — Project-role must equal global-role
`add_project_member` enforces `data.role_on_project == user.role` (with one hardcoded exception
for external consultants). This forbids the very thing §11 asks for: a Senior Engineer acting as
Project Manager on one project.

### P11 — `get_manageable_project_or_403` is hardcoded to ADMIN or the assigned PM
It ignores the catalogue entirely. `manageable_project()` (the configurable version) exists and
is used in some places; the hardcoded one is still used in others.

### P12 — Voice has its own role model
See §1.5. Four coarse roles, three enforcement points, and an unreachable branch for
`internal_engineer` / `owner`.

### P13 — Frontend duplicates the whole role table
`ROLE_PERMISSIONS` (static, 6 roles × ~40 actions), `ROLE_HIERARCHY`, `DASHBOARD_ROUTES`,
`ROLES_OPTIONS`, `MODULE_ACCESS`, `RoleGuard allowedRoles=[…]` (11 route groups),
`portfolioProjectsPath` (per-role URL prefixes: `/engineer/projects`, `/consultant-engineer/projects`,
`/project-manager/projects`), `ConsultantEngineerGuard`, `MainContractorEngineerGuard`.
`resolvePermission` is the bridge — but only 14 of ~40 actions are mapped to catalogue codes.

### P14 — Documents/IFC have no notion of *who a file was shared with*
Document visibility is `project + role scope`. There is no per-party scope, so an external
contractor participant would see every project document the moment they were made a member.
This is the single largest **security** consequence of introducing external users.

---

## 3. Proposed domain model

Deliberately conservative: **five new tables, two repurposed, two enums retired.** Nothing
speculative. Every entity below exists because a stated requirement needs it.

```
Organization                         (repurposed Company)
  kind: CONSULTING_OFFICE | CONTRACTOR | CLIENT | OTHER
  is_tenant: bool                    ← exactly one CONSULTING_OFFICE per deployment (v1)
  branding_json                      ← §17 PDF template/branding
     │
     ├── Role                        (org-owned, configurable)          ← NEW
     │      code, name_en, name_ar, scope: ORG|PROJECT|BOTH,
     │      is_internal_only, is_system, rank (for display only)
     │      └── RolePermission(role_id, permission_code, allowed)       ← NEW
     │
     ├── Discipline                  (org-owned or global)              ← NEW
     │      code, name_en, name_ar, ifc_disciplines: text[]
     │
     └── OrganizationMembership(user, organization, role_id, is_active) ← NEW
              (a user's *home* org and their org-level role)

User
  org_role_id  → Role                ← replaces UserRole enum
  legacy_role  → user_role enum      ← kept, read-only, for N releases
  is_internal  → bool                ← derived from home org kind; replaces engineer_affiliation
  UserDiscipline(user, discipline, is_primary)                          ← NEW, many-to-many

Project
  organization_id  → the consulting office that owns it (NOT NULL)
  client_party_id  → ProjectParty(kind=CLIENT)
  project_manager_id (kept)
  owner_id (kept during transition, then derived from client_party)
     │
     ├── ProjectParty                                                   ← NEW
     │      kind: CLIENT | MAIN_CONTRACTOR | SUBCONTRACTOR | CONSULTANT | SUPPLIER | AUTHORITY | OTHER
     │      organization_id (nullable — a party may be a name only)
     │      display_name, parent_party_id (subcontractor → its main contractor)
     │      is_primary (the *one* main contractor, if there is one)
     │
     └── ProjectMember  (extended, not replaced)
            project_role_id → Role      ← replaces role_on_project enum
            party_id        → ProjectParty | NULL   NULL = internal office staff
            is_site_engineer (kept)
            assignment_title (kept)
            ProjectMemberDiscipline(member, discipline)  ← replaces project_discipline string
```

### Why these and not more

- **No `Permission` table.** The catalogue stays code-owned (`permission_catalogue.py`). An
  administrator composes roles out of existing permissions; they do not invent permissions,
  because a permission that no code checks is a lie. This is the §20 line.
- **No separate `ExternalParticipant` table.** External-ness is `ProjectMember.party_id IS NOT NULL`
  plus `Role.is_internal_only`. One membership table, one query path.
- **No org hierarchy / departments / teams.** Not asked for, not needed.
- **`ProjectParty` is one table, not four.** "Contractor" and "Subcontractor" are not separate
  entities — §5 asks us to investigate, and the answer from the code is clear: the only structural
  difference is that a subcontractor points at its main contractor. `parent_party_id` expresses
  that in one column. Multiple main contractors are then naturally supported (several rows with
  `kind=MAIN_CONTRACTOR`), and `is_primary` handles the common single-contractor case without
  forbidding the other.

---

## 4. Role model — exactly how configurable roles work

**A role is a named bundle of permissions, owned by an organization, usable at org level, project
level, or both.**

```
effective_permissions(user, project_id) =
    org_role.permissions                       # from OrganizationMembership.role_id
  ∪ project_role.permissions (if member)       # from ProjectMember.project_role_id
  Δ RolePermissionOverride                     # unchanged, keyed by role_id instead of enum
  Δ UserPermissionOverride(project_id IS NULL) # unchanged
  Δ UserPermissionOverride(project_id = this)  # unchanged, narrowest wins
  ∩ {} if user.status != ACTIVE                # unchanged
  ∩ project access for project_scoped codes    # unchanged
  ∪ admin_locked if role.is_system_admin       # unchanged in spirit
```

Union, not override, between org and project role — because "Senior Engineer in the office,
Project Manager on Project A" must mean *both*, and the narrower `UserPermissionOverride` layer
already exists to subtract when needed.

**Seeded system role templates** (created per organization at signup, then freely renamed,
edited or deleted):

| Template code | Scope | Internal only | Notes |
| --- | --- | --- | --- |
| `org_admin` | ORG | yes | holds `admin_locked` permissions; cannot be deleted |
| `general_manager` | BOTH | yes | broad org authority; renameable to Managing Director / Senior Consultant |
| `technical_director` | BOTH | yes | |
| `project_manager` | BOTH | yes | |
| `senior_engineer` | BOTH | yes | |
| `engineer` | BOTH | yes | |
| `site_engineer` | PROJECT | yes | pairs with `ProjectMember.is_site_engineer` |
| `bim_engineer` | BOTH | yes | |
| `surveyor` | BOTH | yes | |
| `admin_staff` | ORG | yes | |
| `client_representative` | PROJECT | **no** | replaces `UserRole.OWNER` on a project |
| `contractor_representative` | PROJECT | **no** | |
| `subcontractor_representative` | PROJECT | **no** | |
| `external_reviewer` | PROJECT | **no** | external consultant brought in by the office |

Rules the code enforces regardless of configuration:
1. A role with `is_internal_only=true` cannot be assigned to a `ProjectMember` with a `party_id`.
2. An external member can never hold a `project_scoped=False` permission
   (`platform.view_all_projects`, `platform.manage_users`, `platform.create_project`,
   `platform.manage_permissions`). Enforced at grant time *and* in `effective_permissions`.
3. At least one non-deletable role holds every `admin_locked` permission.
4. Deleting a role is refused while any membership references it (`ON DELETE RESTRICT`).

**Explicitly not built:** role inheritance, role hierarchies, ABAC condition expressions,
per-field permissions. `ROLE_HIERARCHY` in the frontend becomes a display-order integer with no
authorization meaning.

---

## 5. Discipline model — independent of roles

**A discipline is a professional specialization. It never grants anything. It narrows what a
permission applies to.**

```
Discipline(id, organization_id|NULL, code, name_en, name_ar, ifc_disciplines: text[], is_active)
UserDiscipline(user_id, discipline_id, is_primary)                 -- many-to-many
ProjectMemberDiscipline(project_member_id, discipline_id)          -- many-to-many, per project
```

Global seeded set (org-editable, and offices may add their own):
`architectural, structural, civil, geotechnical, mechanical, electrical, plumbing,
fire_protection, mep, hvac, bim, survey, quantity_surveying, landscape, infrastructure`.

`ifc_disciplines` is the bridge that fixes **P4**: `mep` maps to
`['MECHANICAL','ELECTRICAL','PLUMBING','FIRE_PROTECTION']`, `structural` maps to `['STRUCTURAL']`,
`civil` to `['SITE_CIVIL','STRUCTURAL']`. This makes "one engineer covers Mechanical and
Electrical" (Office B/C in §19) expressible two ways — a single `mep` discipline, or two rows in
`UserDiscipline` — and both resolve to the same IFC set. `normalize_discipline`'s lossy alias map
becomes a data table.

Where discipline is *used* (all of it read-only filtering, never authorization):
document scope for reviewers, consultant review routing (`ProjectConsultantReviewer.discipline`),
task/issue filtering, IFC finding routing, agent evidence tagging, notification targeting.

Where discipline must **not** be used: any `require()` call. If a check today reads
"is an electrical engineer", it becomes "holds `design_change.approve` **and** their disciplines
intersect the item's discipline" — permission first, discipline second.

---

## 6. Internal vs. external users

| | Internal (consulting office staff) | External (contractor, subcontractor, client) |
| --- | --- | --- |
| Home organization | `kind=CONSULTING_OFFICE`, `is_tenant=true` | their own `Organization` row, or none |
| `ProjectMember.party_id` | `NULL` | points at a `ProjectParty` |
| Role | any `is_internal_only` role | only `is_internal_only=false` roles |
| Project visibility | may hold `platform.view_all_projects` | **never**; strictly per-membership |
| Org-level permissions | yes | none — all their permissions are project-scoped |
| Document access | office scope (see §12) | party scope: deny-by-default, explicit share |
| Directory visibility | full office directory | only participants of shared projects |
| Can be a Site Engineer | yes | no (`is_site_engineer` requires `party_id IS NULL`) |
| Voice | full capability set per permissions | reduced set (report/message/issue), same engine |

`User.is_internal` is derived, stored denormalized for query speed, and recomputed whenever
`OrganizationMembership` changes. It replaces every current read of `engineer_affiliation`:

| Today | Becomes |
| --- | --- |
| `is_main_contractor_engineer(u)` | `member.party_id` → party `kind IN (MAIN_CONTRACTOR, SUBCONTRACTOR)` |
| `is_consultant_engineer(u)` | holds `design_change.approve` / `task.review` on the project (permission, not identity) |
| `internal_engineer` | `user.is_internal` |

Note the middle row: **"consultant engineer" stops being an identity and becomes an authority.**
That is the single change that makes §2's "role ≠ discipline, offices differ" requirement
actually work, because in the new product the *consulting office itself* is the consultant — the
reviewing authority is a permission its own staff hold, not a foreign affiliation.

---

## 7. Worker removal plan

**Decision: remove the account type, keep the evidence.** Three tiers.

### Tier 1 — Remove (role and access)
- `UserRole.WORKER` enum value → not carried into the `Role` table; no `worker` system role template.
- `is_worker()` in `deps.py`; `worker_can_message`, `worker_recipient_ids`; the `"WORKERS"`
  messaging group; `worker_dashboard` endpoint; `WORKER` from `voice_capabilities`;
  `voice_command_service`'s worker suggestion filter; `WORKER` from every catalogue default
  (`task.view`, `task.update_progress`, `ifc.view`); worker branches in `tasks.py`, `projects.py`,
  `attachments.py`, `photo_archive.py`, `ai.py`; frontend `worker` entries in `ROLE_PERMISSIONS`,
  `MODULE_ACCESS`, `Sidebar.globalByRole`, `ROLES_OPTIONS`, `DashboardSelectorPage`;
  mobile `RoleConstants.worker`.

### Tier 2 — Keep and re-point (the evidence primitive)
`FieldSubmission` is **not** a worker feature — it is *the* structured field-evidence record
(photos with direction, AI metadata, category assignments, verification workflow, voice origin).
In a consulting-office product a Site Engineer produces exactly this. So:

- `field_submissions.worker_id` → **rename** to `submitted_by_id` (column rename, data intact).
- Author gate changes from `is_worker()` to a new catalogue permission
  `field_evidence.submit`, defaulted to roles that hold `site_report.submit`.
- The two-step *submit → engineer verifies* loop is **retained but made optional per project**:
  a site engineer's own evidence needs review by the office (report review), not verification by
  a peer. Proposed: `verification_required` on the project; when false, submissions land
  `VERIFIED` with `reviewed_by = submitter` and the audit trail says so.
- `FieldSubmissionPhoto`, `PhotoCategory`, `PhotoCategoryAssignment`, the photo archive, and
  `EvidencePhotoDirection` are untouched — they are already author-agnostic.
- Voice `CREATE_FIELD_SUBMISSION` survives, re-gated on `field_evidence.submit`.

### Tier 3 — Keep as data
- `SiteReport.workers_count` stays. Optionally extend to a structured
  `workforce_json` (`[{trade, count, party_id}]`) later — **not in this redesign**; §17 does not
  require it and §20 forbids speculative structure.

### Migration risks (ranked)

| Risk | Detail | Mitigation |
| --- | --- | --- |
| **High** — existing worker accounts | `field_submissions.worker_id` is `ON DELETE RESTRICT`; deleting worker users is impossible while evidence exists | Never delete. Convert each worker account to `status=INACTIVE` + a new `Role` named "Field Staff (archived)" with zero permissions. Evidence, photos and audit trail stay attributable. |
| **High** — `permanently_delete_user` | [app/api/users.py:503](../backend/app/api/users.py) already blocks deletion when field submissions exist | Keep that block. It is correct. |
| **Medium** — 29 backend test files | Every worker fixture and RBAC assertion | Rewrite as site-engineer fixtures; keep the *behaviour* assertions (evidence submit/verify/reject), change only the actor. |
| **Medium** — messaging groups | `"WORKERS"` group code appears in API responses and i18n | Remove the code; the group list is already dynamic per project. |
| **Low** — mobile app | `RoleConstants.worker`, `role_dashboard_screen` | Mobile already gates Voice on "everyone except admin"; only the dashboard branch needs removal. |
| **Low** — seed data | `worker1/2/3` in `seed_demo.py` | Reseed as site engineers of differing disciplines — which also gives §6 ("multiple site engineers per project") a demo. |

**Do not** drop the `WORKER` value from the PG `user_role` type during the migration — see §16.

---

## 8. Project membership model

| Question | Organization membership | Project membership |
| --- | --- | --- |
| What it means | "I work for this office" | "I am on this project" |
| Table | `OrganizationMembership` | `ProjectMember` |
| Role | `org_role_id` (e.g. Senior Engineer) | `project_role_id` (e.g. Project Manager) |
| Cardinality | one home org per user (v1) | many projects per user |
| External users | may have none, or their own contractor org | always have one, always with a `party_id` |
| Grants | org-level, non-project-scoped permissions | project-scoped permissions on that project only |

Rules:
1. Every project belongs to exactly one `Organization` with `kind=CONSULTING_OFFICE` (**NOT NULL** —
   tightened from today's nullable `company_id`).
2. `project_role_id` need **not** equal `org_role_id`. This deletes P10.
3. A member with `party_id IS NOT NULL` is external and inherits none of their home org's
   permissions on this project.
4. `is_site_engineer` requires `party_id IS NULL` (office staff only) — inverting today's
   "contractor-side engineers only" rule (P9).
5. Any number of site engineers per project, each with their own disciplines. Already supported.

---

## 9. Permission model

Unchanged in structure, extended in inputs. Resolution order stays exactly as documented in
`authorization.py`; only the first step changes from "the role enum's catalogue default" to
"the union of the org role's and project role's `RolePermission` rows".

New catalogue permissions required by this redesign (additions only — no existing code removed):

| Code | Group | Why |
| --- | --- | --- |
| `org.manage_roles` | platform | create/rename/delete roles, assign permissions — `admin_locked` |
| `org.manage_disciplines` | platform | manage the office's discipline list |
| `org.manage_settings` | platform | branding, report templates (§17) |
| `project.manage_parties` | project | add/remove contractors, subcontractors, client |
| `project.invite_external` | project | grant an external person access to this project |
| `field_evidence.submit` | field | replaces `is_worker()` |
| `field_evidence.verify` | field | replaces the main-contractor-engineer reviewer gate |
| `document.share_external` | models | expose a document to a `ProjectParty` |

Existing codes whose *defaults* change: every `WORKER` entry is removed; `CONSULTANT` entries
resolve to the `external_reviewer` / office reviewer templates.

Two invariants added to `effective_permissions`:
- external members (`party_id IS NOT NULL`) have every `project_scoped=False` permission stripped;
- a permission granted at org level is still subject to the existing project-access check.

---

## 10. AI impact — the five agents

**Verdict: no agent code changes.** Verified by inspection, not assumed.

| Agent | Its `permission_code` | Change needed |
| --- | --- | --- |
| Site Report Agent | `site_report.submit` | none |
| Document Consistency Agent | `task.view` | none |
| Revision Impact Agent | `ifc.view` | none — **but see below** |
| RFI Agent | `design_change.propose` | none |
| Schedule Risk Agent | `schedule.view` | none |

What *does* change around them:

1. **`ifc.view` must become enforcing.** It is currently descriptive; `can_ifc` is the real gate.
   Once `IFC_PERMISSIONS`'s role dict is deleted (§13), `ifc.view` becomes the actual check and
   the Revision Impact Agent's declared permission finally means what it says. This is a
   *strengthening*, and it is why the IFC work must land before the agent work is declared done.
2. **The analysis principal.** `event_subscriber._analysis_principal` uses the project's assigned
   PM. That reasoning holds and improves: a PM is now an office role with configurable
   permissions, so an office that concentrates authority in a Technical Director can express it.
   **Recommended refinement:** fall back from `project_manager_id` to *the internal member holding
   the broadest project permission set*, still refusing to run if none exists. Optional; the
   current behaviour is safe.
3. **Two user-facing strings** in `analyzers.py` say "check whether your role can read them" —
   reword to "your permissions". Cosmetic.
4. **Discipline in findings.** `analyzers.py` reads discipline for tagging only; it will read the
   new `Discipline.code` instead of `EngineerDiscipline`. Its IFC-side vocabulary is unaffected
   because IFC classification derives disciplines from IFC classes, not from the org model.

**Agents must not gain role awareness.** No agent should ever ask "is this person a site
engineer". If a finding needs to reach site engineers, that is a *notification routing* decision
(§15), not an agent decision.

---

## 11. Voice impact

**This is the largest AI-side change, and §14 is right to call it out.** Voice today *is* a second
role system.

| Voice component | Today | Proposed |
| --- | --- | --- |
| `Capability.roles: frozenset[str]` | 4 coarse role names | **deleted** |
| `voice_role(user)` | maps user → one of 4 names | **deleted** |
| `is_available()` | role check + PM-of-project check + affiliation check + permission + membership flag | permission + membership flag + project-scope only |
| `VoiceRulesEngine.validate` role gate | `voice_role(actor) not in capability.roles` | `has_permission(capability.permission_code)` |
| `write_tools.py:40` role gate | same | same replacement |
| `voice_action_service._role_may` | maps 5 strings onto 4 registry roles | **deleted** |

Every capability must therefore carry a real `permission_code`. Four currently have `None`
(`ADD_TASK_NOTE`, `SEND_PROJECT_MESSAGE`, `SEND_OWNER_UPDATE`, `CREATE_TASK_MESSAGE`) and were
relying on the role set as their only gate. They need codes:
`task.add_note`, `message.send`, `message.send_client`, `task.comment` — or an explicit,
documented delegation to the messaging service's own per-recipient decision (which
`messaging_authorization.can_message_user` already makes properly).

`CREATE_TASK` / `UPDATE_TASK_SCHEDULE` / etc. currently carry `roles={MANAGER}` *and* a
"manager of **this** project" check. The permission layer already expresses this correctly:
`manageable_project(db, user, project_id, "task.edit")`. Use it.

**§14's example works after the change:** "عيّن المهمة لأحمد" resolves via
`voice_entity_resolution.assignable_people` (project membership) and validates via `task.edit` —
no role names involved. One caveat: `_ROLE_WORDS` in `voice_entity_resolution.py` matches spoken
words like "استشاري", "مقاول", "عامل" onto `Person.role`. That map must be rebuilt from the
`Role` table's `name_ar` / `name_en` (so a renamed role is still speakable) and from
`ProjectParty.kind` (so "المقاول" resolves to the contractor's representative). Drop "عامل".

**Voice must keep working during migration** — see §16 phase 4.

---

## 12. RAG / knowledge impact

**Retrieval architecture is not rebuilt.** `readable_document_ids → retrieval.search` stays; the
rule that authorization is resolved *before* embedding search stays. What changes is
`document_access.py`, which currently has two hardcoded role scopes.

| Layer | Today | Proposed |
| --- | --- | --- |
| project access | `user_has_project_access` | unchanged |
| owner scope | `role == OWNER` → contracts/permits + approved-completed evidence | `party.kind == CLIENT` → same rule, now expressed as a **party scope** |
| consultant scope | `is_consultant_engineer` → own `EngineerProfile.discipline` | `discipline scope`: applies to any member whose role lacks `document.view_all`, narrowed to `ProjectMemberDiscipline` |
| **party scope (new)** | — | external members see only documents explicitly shared with their party, plus documents they uploaded |

Ownership answers §15 asks for:
- **Which organization owns a document?** The project's consulting office. Documents are
  project-owned; the project is org-owned. No `Document.organization_id` column is needed.
- **Who can read them?** The four layers above, composed.
- **How are external users scoped?** Deny-by-default via the party scope. This is the change
  that makes external accounts safe (P14).
- **How do agents access them?** Unchanged — `search_documents` / `get_document` /
  `query_project_knowledge` already delegate to `readable_document_ids`, and the `AgentContext`
  runs as a real principal.
- **Project-level authorization?** Unchanged.

`DocumentChunk` and the vector store need no changes: filtering is by `document_id` list, which
is computed by the layers above.

`knowledge_router` needs no changes — it routes by topic, not by role.

---

## 13. IFC / BIM impact

**Nothing about IFC parsing, geometry, interference, comparison, or knowledge changes.** The
change is authorization only.

Delete `IFC_PERMISSIONS` (the role→verb dict) and make `can_ifc` compose:

```
can_ifc(db, user, project_id, verb) =
    settings.IFC_FEATURE_ENABLED
    and user.status == ACTIVE
    and has_permission(db, user, IFC_VERB_PERMISSION[verb], project_id)
    and (verb != "UPLOAD" or settings.IFC_ENGINEER_UPLOAD_ENABLED or user holds ifc.manage_version)
```

Requires four new catalogue codes to cover verbs that have none today:
`ifc.compare`, `ifc.review_finding`, `ifc.review_suggestion`, `ifc.download`
(`ifc.manage_link` maps to the existing `ifc.manage_version`). The two feature flags stay — they
are operational kill-switches, not authorization.

Consequences:
- The three descriptive catalogue entries become enforcing. **This is a behaviour change** and
  needs its own test pass (§21).
- `WORKER` leaves the `VIEW` set with worker removal.
- The affiliation gate (`is_main_contractor_engineer or is_consultant_engineer`) disappears —
  replaced by ordinary project membership + permission.
- External participants get IFC access only when explicitly granted, per project.

**Do not add DWG/BIM ingestion in this redesign.** §16 says so and I agree: `file_intelligence`
already detects DWG as a format and files it; extending it is orthogonal work that would tangle
with the migration.

---

## 14. Site Report impact

Site Reports become the *primary* internal engineering workflow rather than a
contractor-reporting artifact. Model changes are small; workflow changes are real.

| Concern | Today | Proposed |
| --- | --- | --- |
| Who may file | `site_report.submit` = `{PM, ENGINEER}` — plus `is_site_engineer` flag for the voice draft path | `site_report.submit`, defaulted to `site_engineer`, `engineer`, `project_manager` templates; still requires `is_site_engineer` for the voice draft |
| Who may verify | `site_report.verify` = `{PM}` + assigned-PM-only via `manageable_project` | unchanged in shape; the office decides which role holds it |
| Multiple site engineers | already supported | keep; add "my reports" vs "project reports" views |
| Report ↔ discipline | not recorded | add `SiteReport.discipline_id` (nullable) so a multi-discipline project's reports can be filtered and routed |
| External visibility | n/a | a report is internal by default; sharing with a contractor party is an explicit action |
| PDF export (§17) | not built | new: `Organization.branding_json` + a report template; **out of scope for this redesign**, but the schema above is what it will need |
| `workers_count` | stays | stays (§7 tier 3) |

`FieldSubmission` and `SiteReport` remain distinct: a field submission is *evidence attached to
one task*; a site report is *a dated narrative of a visit*. `SiteReport.site_visit_id` already
links reports to visits. That split is correct and should not be merged.

---

## 15. Notification / proactive AI impact

The chain **Domain Event → agent analysis → AIInsight → Notification** is preserved exactly.
The redesign *improves* the weakest link, which is recipient selection.

Today: `event_subscriber.notify_for_findings` notifies **one person — the analysis principal
(the PM)**. That is honest but narrow: a coordination finding in the electrical model reaches the
PM and nobody else.

Proposed routing, in this order, all derived from the new model:

1. **Eligibility** — a person may receive a finding only if they hold the agent's
   `permission_code` on that project (so notification can never leak what the app would refuse).
2. **Relevance** — narrow by discipline: intersect the finding's `affected` disciplines
   (via `Discipline.ifc_disciplines` for IFC findings) with each candidate's
   `ProjectMemberDiscipline`.
3. **Accountability** — always include the analysis principal, so nothing is unowned.
4. **Externals** — never notified by an agent. External participants receive only what a person
   explicitly shares. (Agent findings are internal review material.)
5. **Band** — `decide_notification` is unchanged; confidence/severity/certainty still decide
   *whether* and *how loudly*.

Who may **see, review, promote and act on** findings maps cleanly onto existing catalogue codes
(`ai.view_insights`, `ai.review_insight`, `ai.promote_insight`) — those need no change beyond
losing their `CONSULTANT`/`WORKER` defaults.

---

## 16. Database migration plan

**Expand → migrate → contract, over four releases. No destructive step until the last.**

### R1 — Expand (additive only; zero behaviour change)
```
CREATE TABLE roles, role_permissions, organization_memberships,
             disciplines, user_disciplines,
             project_parties, project_member_disciplines
ALTER organizations (rename from companies) ADD kind, is_tenant, branding_json
ALTER users            ADD org_role_id NULL, is_internal BOOL DEFAULT true
ALTER project_members  ADD project_role_id NULL, party_id NULL
ALTER projects         ADD organization_id (already exists as company_id — rename)
ALTER site_reports     ADD discipline_id NULL
ALTER field_submissions RENAME worker_id TO submitted_by_id
```
`role_permission_overrides.role` (enum) is kept; a parallel nullable `role_id` is added.

### R2 — Backfill (idempotent data migration, reversible)
1. Create the tenant `Organization` (`kind=CONSULTING_OFFICE`) from the existing admin's company.
   Other companies become `kind=CONTRACTOR` / `CLIENT` per their users' `engineer_affiliation`.
2. Seed the 14 system role templates and the 15 global disciplines.
3. Map every user: `(role, engineer_affiliation)` → `org_role_id`, per the table in §1.2.
   `WORKER` → `Field Staff (archived)`, zero permissions, `status=INACTIVE`.
4. `EngineerProfile.discipline` → one `UserDiscipline` row (`is_primary=true`).
5. `ProjectMember.role_on_project` → `project_role_id`; `project_discipline` →
   `ProjectMemberDiscipline`.
6. For each project: create `ProjectParty(kind=CLIENT)` from `owner_id`; create
   `ProjectParty(kind=MAIN_CONTRACTOR, is_primary=true)` if any member has
   `affiliation=main_contractor`, and set those members' `party_id`. Consultant-affiliated members
   become internal reviewers of the tenant office (they are the consulting office in the new
   model) **unless** their company differs from the tenant, in which case
   `ProjectParty(kind=CONSULTANT)`.
7. Recompute `users.is_internal`.
8. Copy every `RolePermissionOverride` onto the corresponding `role_id`.

**Verification gate:** a script asserts that for every (user, project) pair,
`effective_permissions` computed the old way == computed the new way. R3 does not ship until it
is clean. This is the single most important safety measure in the plan.

### R3 — Switch reads
`effective_permissions` reads `role_permissions`; `deps.py` helpers are replaced;
`ifc_policy`, `document_access`, `voice_capabilities` migrate. The old enum columns become
read-only (`legacy_role`), still written for rollback.

### R4 — Contract
Drop `users.role` / `project_members.role_on_project` / `role_permission_overrides.role`
enum columns; drop `engineer_affiliation`; drop `engineer_profiles.discipline`;
**then** drop the `user_role` and `engineer_discipline` PG types.

### PostgreSQL-specific hazards
- The `user_role` type is bound by **three** tables. It cannot be dropped until all three are
  migrated — hence R4 as a single step.
- `ALTER TYPE … DROP VALUE` does not exist in PostgreSQL. `WORKER` cannot be removed from the enum
  incrementally; only the whole type can be dropped at R4. Any interim attempt will fail.
- `field_submissions.submitted_by_id` is `ON DELETE RESTRICT`. Renaming is safe; deleting users is
  not, and must stay blocked.
- Existing enum-case handling (`d5e8c3a20f22_fix_enum_case.py`, `e6f9d4b31a33_normalize_engineer_roles.py`)
  shows this codebase has been bitten by enum migrations before. Treat R4 as a maintenance window.

---

## 17. Frontend migration plan

| File / area | Change |
| --- | --- |
| `src/types/auth.ts` | `UserRole` union → `Role { id, code, nameEn, nameAr, scope, isInternalOnly }`; `EngineerDiscipline` union → `Discipline[]`; delete `EngineerAffiliation` |
| `src/utils/permissions.ts` | delete `ROLE_PERMISSIONS`; `resolvePermission` reads the backend list only; map the remaining ~26 unmapped actions to catalogue codes or delete them |
| `src/utils/roleMapper.ts` | `ROLE_LABELS` / `ROLE_LABELS_AR` come from the API; `ROLE_HIERARCHY` becomes display order; `DASHBOARD_ROUTES` becomes one route driven by permissions |
| `src/app/router/RoleGuard.tsx` | → `PermissionGuard permission="…"`; 11 route groups rewritten |
| `ConsultantEngineerGuard`, `MainContractorEngineerGuard` | deleted |
| `src/utils/projectRoutes.ts` | **collapse the per-role URL prefixes** (`/engineer/projects`, `/consultant-engineer/projects`, `/project-manager/projects`) into one `/projects/:id/…`; `MODULE_ACCESS` becomes permission-derived |
| `src/components/shared/Sidebar` | `globalByRole` → permission-driven nav sections |
| `src/hooks/useRole.ts` | keep `hasCapability`; delete `isMainContractorEngineer` / `isConsultantEngineer` / `isEngineer` |
| `features/admin/AccessControlPage.tsx` | `ROLES` const → fetched roles; add role CRUD |
| **New** `features/admin/RolesPage` | create/rename/delete roles, assign permissions |
| **New** `features/admin/DisciplinesPage` | manage the office's discipline list |
| **New** `features/projects/ProjectPartiesPage` | contractors, subcontractors, client, external people |
| `ProjectTeamPage` | role select from API; discipline multi-select; internal/external split; site-engineer toggle for office staff |
| `UserForm` | org role select; multi-discipline; no affiliation field |
| Worker UI | removed from Sidebar, `DashboardSelectorPage`, `ProjectTeamPage` filters, `TaskForm` |
| `EvidencePhotoArchivePage`, `VoiceReportsPage`, `EngineerTaskDetailPage` | "worker" labels → "submitted by" |
| i18n `en/ar` | new role/discipline keys; roles become data so `t("roles.x")` falls back to the API name |
| Mobile (`mobile_app`) | `RoleConstants` deleted; `role_dashboard_screen` permission-driven; `canUseVoice` unchanged (already permission-agnostic) |

The URL-prefix collapse is the largest single frontend change and the one most likely to break
deep links; `replaceProjectInPath` and `projectEntityPath` both encode the prefixes, and push
notifications produce those URLs.

---

## 18. Backward compatibility

**Unchanged:**
- The permission resolution *order* and its two hard rules (inactive = nothing; project-scoped
  requires project access).
- `AIInsight`, `AgentRun`, `DomainEvent`, all agent contracts, `Certainty`, confidence ceilings.
- The AI tool registry and every `ToolSpec` handler.
- RAG chunking, embeddings, vector store, retrieval, answering, citations.
- IFC parsing, geometry, interference, comparison, knowledge, `IFCElement.discipline`.
- Notification bands, `decide_notification`, push/FCM, realtime SSE.
- Task, Issue, Milestone, DesignChange, CostValidation, Message, Attachment schemas.
- Site report and field submission *workflows* (submit → review → verify/reject).

**Must change:**
- `UserRole` / `EngineerDiscipline` enums and the three columns bound to them.
- `engineer_affiliation` and all 40 read sites.
- `deps.py` role helpers and every caller.
- `ifc_policy.IFC_PERMISSIONS`, `document_access` role scopes.
- Voice capability role sets and the three enforcement points.
- The frontend role table, guards and per-role URL prefixes.
- API response shape for role fields (`role: "engineer"` → `role: {id, code, name}`) — a
  **breaking API change**; the mobile app must ship in step, or the backend must emit both
  (`role` legacy string + `orgRole` object) for one release.

---

## 19. Risks

| # | Risk | Severity | Mitigation |
| --- | --- | --- | --- |
| R1 | Silent permission widening during backfill — an office user ends up with more access than before | **Critical** | The R2 verification gate: old vs. new `effective_permissions` diff must be empty for every (user, project) pair before R3 ships |
| R2 | External participants see internal documents the moment party support lands | **Critical** | Ship the deny-by-default party document scope (§12) *before* any external-invite UI exists |
| R3 | Making `ifc.view` enforcing changes who can open the IFC workspace | High | Dedicated test pass; set catalogue defaults to exactly reproduce today's `IFC_PERMISSIONS` sets, then let admins change them |
| R4 | Voice breaks for a role mid-migration (empty capability list = "I can't do anything") | High | Migrate Voice **after** permissions switch (§20 step 6); the four `permission_code=None` capabilities are the trap |
| R5 | The `user_role` PG type cannot be partially dropped; a half-migration leaves the DB unmigratable | High | Single R4 window; rehearse on a restored production dump |
| R6 | `field_submissions.worker_id` `ON DELETE RESTRICT` blocks worker cleanup | Medium | Never delete; deactivate. Already enforced by `permanently_delete_user` |
| R7 | Frontend URL-prefix collapse breaks push-notification deep links | Medium | Keep permanent redirects from the old prefixes for two releases |
| R8 | `normalize_discipline`'s alias map is lossy (`structural→civil`, `hvac→mechanical`); backfill inherits the loss | Medium | Backfill from the *original* string where available (`ProjectMember.project_discipline`, `Task.discipline`), not from the normalized enum |
| R9 | 29 worker test files + 58 `UserRole` test files churn; regressions hide in the noise | Medium | Migrate tests per phase, not in one commit; keep behavioural assertions, change only actors |
| R10 | Mobile app and backend role-shape mismatch | Medium | Dual-emit `role` + `orgRole` for one release |
| R11 | Two site engineers of different disciplines on one project — untested path | Low | Add to seed data; it becomes the demo for §6 |
| R12 | Over-engineering pressure (role inheritance, ABAC, dynamic permissions) | Low but real | Explicitly out of scope; the catalogue stays code-owned |

---

## 20. Implementation order

Each step is independently shippable and independently revertible. Nothing after step 3 begins
until the R2 verification gate is clean.

| # | Step | Ships | Gate |
| --- | --- | --- | --- |
| 1 | **Catalogue completion.** Add the ~12 new permission codes; convert the remaining ~40 inline role checks to `require()` / `manageable_project()` with defaults identical to today | R1 | Full test suite green, zero behaviour change |
| 2 | **Schema expand.** All new tables + nullable columns. No reads switched | R1 | Migration up/down clean on a prod dump |
| 3 | **Backfill + verification gate.** Roles, disciplines, memberships, parties; old-vs-new permission diff | R2 | **Diff empty. Hard gate.** |
| 4 | **Switch authorization reads.** `effective_permissions` from `role_permissions`; `deps.py` helpers replaced | R3 | Diff still empty at runtime; RBAC test suite green |
| 5 | **Feature-policy convergence.** `ifc_policy`, `document_access` (incl. party scope), `messaging`, `field_submission`, `photo_archive`, `collaboration` | R3 | Per-feature access tests |
| 6 | **Voice migration.** Delete `Capability.roles`, `voice_role`, `_role_may`; give all capabilities permission codes; rebuild `_ROLE_WORDS` from role/party names | R3 | Voice acceptance suite (`test_voice_*`) green in ar + en |
| 7 | **Worker removal.** Tier 1 + tier 2 rename + account conversion | R3 | No `is_worker` in `app/`; evidence workflow green with site-engineer actors |
| 8 | **Notification routing.** Eligibility + discipline relevance + accountability (§15) | R3 | New routing tests; no external recipients |
| 9 | **Frontend.** Types → guards → route collapse → admin role/discipline/party UI → worker removal → i18n | R3 | E2E per role template |
| 10 | **Mobile.** Role constants, dashboards | R3 | |
| 11 | **Contract.** Drop legacy enum columns and types | R4 | Maintenance window; rehearsed |
| 12 | **Docs.** Rewrite the deferred-redesign section of `AGENTS.md`; new `RBAC.md`, `ORGANIZATION.md`; update `RAG.md`, `IFC_INTELLIGENCE.md`, voice docs | — | |

Deferred beyond this redesign (explicitly): PDF site-report templates and branding, structured
workforce data, DWG/Revit ingestion, multi-tenant hosting of many offices in one database,
role inheritance.

---

## 21. Acceptance criteria

Measurable, testable, and mapped to the requirements they prove.

**Configurable roles (§9, §19)**
1. An org admin creates a role "Resident Engineer", grants it `site_report.submit` +
   `field_evidence.submit`, assigns a user — and that user can file a report, with **no code
   deployment**.
2. Renaming a role changes every UI label, the Voice prompt catalogue, and
   `voice_entity_resolution`'s spoken matching, with no restart.
3. Deleting a role that has members is refused with a clear error.
4. `admin_locked` permissions cannot be removed from the org-admin role by any API call.
5. Offices A, B and C from §19 are each expressible as fixtures with zero application-code
   difference between them.

**Role ≠ discipline (§2, §5)**
6. One user holds disciplines `mechanical` **and** `electrical`; they appear in both discipline
   review queues and match IFC findings tagged `PLUMBING` (via `mep`) and `ELECTRICAL`.
7. Two users with the same role and different disciplines get different document scopes and
   different notification sets.
8. No `require()` call anywhere takes discipline as an input. (Static check.)

**Internal vs. external (§4, §6, §11)**
9. An external contractor representative on project A: sees only project A; cannot list users;
   cannot hold `platform.*`; sees zero documents until one is shared with their party; receives
   no agent-generated notification.
10. A project has one main contractor and three subcontractors, each with its own people;
    a subcontractor's `parent_party_id` points at the main contractor.
11. Assigning an `is_internal_only` role to an external member returns 4xx.

**Site engineers (§6, §17)**
12. Three site engineers of three disciplines on one project all file reports the same day; each
    sees their own reports; the office reviewer sees all three.
13. `is_site_engineer` cannot be set on a member with a `party_id`.

**Worker removal (§3, §7)**
14. `grep -rn "is_worker\|UserRole.WORKER" backend/app` returns nothing.
15. Every pre-migration field submission is still readable, attributable and photo-complete.
16. `SiteReport.workers_count` still round-trips through the API and the report view.
17. A site engineer submits field evidence via voice and the workflow completes end to end.

**AI agents (§13)**
18. All five agents produce identical findings on a fixture project before and after migration
    (byte-comparable `AIInsight` rows modulo ids/timestamps).
19. `grep -rn "UserRole\|EngineerDiscipline" backend/app/services/agents backend/app/services/ai_tools`
    returns nothing outside display strings.
20. Proactive analysis still runs under the accountable principal and still refuses when there is
    none.

**Voice (§14)**
21. `Capability.roles`, `voice_role` and `_role_may` no longer exist.
22. Every capability has a non-null `permission_code`, asserted by a test over the registry.
23. The full ar/en voice acceptance suite passes for each of the 14 role templates, and a role
    with no permissions gets the "answer questions only" catalogue rather than an error.
24. "عيّن المهمة لأحمد" resolves by project membership + `task.edit`, with no role name involved.

**RAG (§15)**
25. Retrieval authorization is still resolved before embedding search (test asserts the call order).
26. A client-party user asking about an unapproved draft gets no passage from it.
27. An external member with no shared documents gets an empty, non-erroring answer.

**IFC (§16)**
28. IFC upload → parse → geometry → interference → findings is unchanged on the existing fixtures.
29. `IFC_PERMISSIONS` no longer exists; `can_ifc` resolves through `has_permission`.
30. Pre-migration IFC access for every existing user is unchanged (per-verb, per-user diff test).

**Migration safety (§16, §19)**
31. The old-vs-new `effective_permissions` diff is empty for every (user, project) pair on a
    restored production dump.
32. R1→R2→R3 migrations are reversible; R4 is rehearsed on a dump before the window.
33. No orphaned `ProjectMember`, `OrganizationMembership` or `ProjectParty` after backfill.

---

## Open decisions I need from you before implementation

These change the work materially; I have recommended a default for each.

1. **Multi-tenancy.** One consulting office per deployment (recommended: `is_tenant` flag, roles
   org-owned but effectively global) — or many offices sharing one database from day one?
   The recommendation keeps the schema multi-tenant-ready without paying for isolation testing now.
2. **Do external participants get logins in v1?** Recommended: **the model, yes; the invite UI,
   no.** Ship `ProjectParty` + party document scope first so contractors are *recorded*; enable
   external accounts in a later phase once the deny-by-default scope has been in production.
3. **Owner / client.** Recommended: keep the client portal (it is well built — owner dashboard,
   `ProjectViewState`, `OwnerRequest`), but re-express it as
   `ProjectParty(kind=CLIENT)` + `client_representative` project role, not a global `UserRole`.
4. **Consultant Engineer identity.** Recommended: dissolve it (§6). The consulting office *is*
   the consultant now, so review authority becomes a permission its own staff hold. Confirm — this
   is the one place where the redesign changes an existing product behaviour rather than
   generalizing it, and `docs/CONSULTANT_ENGINEER_COMPLETION_REPORT.md` describes real shipped work.
5. **Field submission verification loop.** Recommended: keep it, make it per-project optional
   (§7 tier 2). Alternative: collapse field submissions into site-report evidence entirely —
   simpler, but discards the photo-direction/category/AI-metadata work.
