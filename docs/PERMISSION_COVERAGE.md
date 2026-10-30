# Permission coverage

Audit of every registered permission, last revised 2026-10-23 (second pass).

## How this was produced

The raw inventory is generated from the code, never hand-edited:

```
cd backend
python scripts/permission_inventory.py --json ../docs/permission_inventory.json \
                                       --markdown ../docs/permission_inventory_table.md
```

For each catalogue code, [`permission_inventory.json`](permission_inventory.json) records the
label, scope, flags and default roles, plus:

- **`operations`**: every place the server actually checks the code, resolved to
  `METHOD /path (handler)` for a route or `module.function` for a helper. Comment
  lines are ignored. IFC routes, which name a verb (`can_ifc(..., "COMPARE")`),
  are followed through `ifc_policy.IFC_VERB_PERMISSION`.
- **`frontend`**: references in the web client.
- **Test files** that name the code.

A literal reference is not evidence. The first pass rated `document.share_external`
"enforced" because a *comment* named it, and rated the task codes "enforced"
while every task endpoint actually asked whether you were the project's assigned
manager. The statuses below come from reading each endpoint and from tests that
grant **and** revoke through the API.

## Summary — 59 permissions

| Status | Count | Meaning |
| --- | --- | --- |
| **A. Verified end to end via the API** | **49** | Its endpoint answers for a holder, refuses after a revoke (or opens after a grant), at the next request. 42 by this pass's tests, 7 IFC codes by the existing per-route matrix in `test_ifc_authorization.py` |
| Implemented; both-direction evidence not completed | 10 | Enforcement point identified and named by existing tests, but not re-exercised in both directions this pass. **Not claimed as A** |
| B. Wrongly wired — **fixed** | 0 open (13 fixed: 6 this pass — `task.create`, `task.edit`, `task.update_progress`, `task.review`, `schedule.edit`, `issue.resolve`; 7 in the first pass) | See *Fixed* |
| C. Partially implemented — **fixed** | 0 open (1 fixed) | Delete Project had no UI |
| D. Registered but unsupported — **fixed** | 0 open (2 fixed) | `document.share_external`, `project.invite_external` |
| E. Blocked by a policy decision | 0 permissions blocked; 3 open questions | See *Policy decisions still required* |

"End to end" here means **through the API**. The web controls are unit-tested
(see *Frontend*). The browser retests in `MANUAL_QA_TEST_PLAN.md` §9.8 have
**not** been run.

## Fixed in this pass

| Code | Was | Now | Where |
| --- | --- | --- | --- |
| `task.create` | **Defect A.** `POST /tasks` refused anyone but `project.project_manager_id` ("Only the assigned Project Manager can create project tasks"), so Rana's grant showed the button and failed | `task.create` + project access is the whole rule | `api/tasks.py create_task` |
| `task.create` | IFC suggestion → task, insight → task: assigned-manager id | `task.create` | `api/ifc.py _create_task_from_suggestion`, `api/ai_intelligence.py insight_to_task`, `AIIntelligencePage` |
| `task.edit` | Edit, assign, delete and reorder: assigned-manager id (delete also required `task.edit`; edit never did) | `task.edit` | `api/tasks.py update_task, delete_task, reorder_tasks` |
| `task.update_progress` | Start, rework, work updates, blockers, resume, progress, submit, complete and respond: only *assigned to the task* was checked | Assigned **and** `task.update_progress` (`_require_task_work`) | `api/tasks.py`, `services/task_progress_service.py` |
| `task.review` | The manager half of review was the assigned-manager id | `task.edit` **and** `task.review`; named reviewers unchanged | `api/tasks.py _can_review_task` |
| `schedule.edit` | Task dependencies: assigned-manager id. IFC milestone suggestion: same | `schedule.edit` (as milestones already were); the web dependency editor follows it | `api/tasks.py`, `api/ifc.py`, `TaskDetailPage` |
| `issue.resolve` | Editing someone else's issue: assigned-manager id | `issue.resolve` | `api/issues.py update_issue` |
| `project.delete` | **Defect B.** `DELETE /projects/{id}` worked, but no screen called it and it wrote no audit row | Projects page: *Delete* per project (`canDelete` from the server, per project), dialog with impact counts and a typed-name confirmation; `GET /projects/{id}/deletion-impact`; `project_deleted` audit row that survives the delete | `api/projects.py`, `ProjectsPage`, `DeleteProjectDialog` |
| `document.share_external` | **Registered, checked nowhere.** External document access is deny-by-default through `DocumentPartyShare`, and only the offline legacy backfill could write one | `GET/POST/DELETE /documents/{id}/party-shares` (party must be active on the document's project, the sharer must be able to read it, both actions audited); *Parties* action on each document | `api/documents.py`, `DocumentPartySharing` |
| `site_visit.schedule` | Its 409 conflict answered **500** (raw datetimes in the error detail) | ISO strings; the conflict reaches the user | `api/collaboration.py _conflict_detail` |

Fixed in the first pass: `task.view`, `site_report.view`, `issue.view`, `design_change.view`
(UI-only), `project.invite_external` (unused), `message.send`, `message.send_client`,
`task.comment` (voice-only).

**Defaults did not move.** The assigned Project Manager holds `task.create`,
`task.edit`, `schedule.edit` and `issue.resolve` through the Project Manager
role. What changed:
- A grant now reaches someone who isn't the assigned manager.
- A revoke now stops the assigned manager too.
- Anyone else who holds these codes by role can now use them on projects they
  reach. That means the Office Director and Technical Director (work in every
  project), and a second Project Manager on a team.

## Status per permission

A = verified both ways through the API this pass; A* = verified by the existing
IFC route matrix; I = implemented, both-direction evidence not completed.

| Code | Operation it governs (main endpoints) | Extra conditions the server checks | Status | Evidence |
| --- | --- | --- | --- | --- |
| `platform.manage_users` | `/users…`, reset password, activate/deactivate | admin-locked | A | read matrix |
| `platform.manage_permissions` | `/access-control/*` | admin-locked | A | read matrix; editor refusal test |
| `platform.create_project` | `POST /projects` | — | A | role grant → create → revoke; person grant |
| `platform.view_all_projects` | project record without membership | — | A | read matrix (`GET /projects/{elsewhere}`) |
| `platform.work_in_all_projects` | project work without membership | — | A | read matrix (`GET /tasks/project/{elsewhere}`) |
| `project.manage_members` | `/projects/{id}/members` add/remove/transfer/assignment | never external | A | read matrix |
| `project.edit` | `PUT /projects/{id}`, approval workflow, deleting documents/attachments, creating cost validations | never external | A | write matrix |
| `project.manage_reminders` | reminder rules, run, scheduler status | assigned manager may also run (policy 1) | A | read matrix |
| `project.delete` | `DELETE /projects/{id}`, deletion impact | permanent | A | disposable-project tests |
| `project.manage_parties` | `/projects/{id}/parties` | never external | A | write matrix |
| `project.invite_external` | adding a member with `partyId` | also `project.manage_members` | A | first-pass test |
| `project.view_all_disciplines` | discipline narrowing of tasks, issues, reports, documents | — | A | narrowing test |
| `task.view` | task reads | — | A | read matrix |
| `task.create` | `POST /tasks`, suggestion/insight → task | — | A | Defect A tests |
| `task.edit` | edit, assign, delete, reorder | — | A | engineer grant edits/deletes; manager revoke stops |
| `task.update_progress` | start … complete (assignee side) | assigned to the task | A | revoke stops start |
| `task.view_all` | whole task list, project dashboard | — | A | read matrix |
| `task.review` | approve / reject / clarification | named reviewer, or also `task.edit` | I | existing reviewer tests |
| `task.comment` | `POST /tasks/{id}/comments` | also `task.view` | A | first pass |
| `task.add_note` | voice-confirmed note | — | A | capability refused after deny |
| `schedule.view` | Gantt, critical path, delays | — | A | read matrix |
| `schedule.edit` | milestones, dependencies, shifting | — | A | manager revoke stops a dependency |
| `site_visit.schedule` | `POST/PATCH /site-visits` | others' visits need `task.view_all` | A | write matrix |
| `site_report.submit` | `POST /site-reports/submit` | — | I | existing tests |
| `site_report.verify` | review / verify a report | not the author | I | `test_site_report_verification.py` |
| `site_report.view` | report reads | — | A | read matrix |
| `issue.create` | `POST /issues`, finding → issue | — | A | first pass |
| `issue.resolve` | close, reassign, edit others' issues, delete | office only | A | engineer grant edits Omar's issue |
| `issue.view` | issue reads | — | A | read matrix |
| `owner_request.create` | `POST /owner-requests` | — | A | write matrix |
| `owner_request.review` | `PATCH /owner-requests/{id}` | assigned manager keeps it (policy 1) | I | — |
| `design_change.propose` | `POST /design-changes`, request → change | — | A | write matrix |
| `design_change.approve` | approve / reject | never external | I | existing tests |
| `design_change.view` | change reads | — | A | read matrix |
| `cost_validation.review` | review endpoint; budget figures in project payloads | — | A | budget hidden after deny, never written |
| `ifc.view` | model, findings, comparisons reads | — | A | read matrix + IFC matrix |
| `ifc.upload` | models, versions, geometry | below `ifc.manage_version`, a feature switch | A* | IFC matrix |
| `ifc.manage_version` | update/archive model, activate version | — | A* | IFC matrix |
| `ifc.compare` | build comparisons, impact analysis | — | A* | IFC matrix |
| `ifc.review_finding` | review finding, finding → issue | — | A* | IFC matrix |
| `ifc.review_suggestion` | review suggestion/impact, run intelligence | — | A* | IFC matrix |
| `ifc.download` | download model / file | — | A* | IFC matrix |
| `ifc.manage_link` | create/delete element links | — | A* | IFC matrix |
| `document.upload` | `POST /documents/upload`, ingest | — | I | existing tests |
| `document.view` | project files | — | A | read matrix |
| `document.share_external` | `/documents/{id}/party-shares` | sharer reads it; never external | A | share opens, unshare closes, revoke refuses, foreign party refused |
| `ai.view_insights` | insights | — | A | read matrix |
| `ai.review_insight` | review insight, revert AI action | — | I | existing tests |
| `ai.promote_insight` | insight → issue | — | I | existing tests |
| `agents.view` | `/projects/{id}/agents` | — | A | read matrix |
| `org.manage_roles` | role CRUD and permissions | — | A | write matrix |
| `org.manage_disciplines` | discipline create/update | — | A | write matrix |
| `org.manage_settings` | `/company/settings` | — | A | read matrix |
| `field_evidence.submit` | field submissions | — | I | existing tests |
| `field_evidence.verify` | verify submissions | never external | I | existing tests |
| `client_portal.view` | `/projects/{id}/owner-dashboard` | — | A | read matrix |
| `message.send` | starting any conversation | replies need nothing | A | first pass |
| `message.send_client` | conversations with a client recipient | also `message.send` | A | first pass |
| `message.broadcast` | announcements, group conversations | — | A | write matrix |

Default roles per code are in the generated JSON. The tests named above live in
`tests/test_permission_capabilities.py` (this pass) and
`tests/test_rbac_customization.py` (first pass).

## Policy decisions still required

1. **The assigned manager as a second route.** These checks read "permission
   OR is `project.project_manager_id`", so a grant works but revoking the
   permission from the assigned manager does not:
   - answering client requests (`owner_request.review`)
   - running reminders (`project.manage_reminders`)
   - deleting a document (`project.edit`)
   - deleting a site report (`site_report.verify`)
   - converting a request to a design change (`design_change.propose`)
   - the AI actions page (`ai.view_insights`)
   - viewing field submissions
   - voice's "manages this project"

   They were written as deliberate accountability ("the assigned manager keeps
   it by virtue of the assignment"), so they were left as they are. Decide
   whether a revoke should beat the assignment.
2. **Files on project deletion.** Rows cascade; stored files (documents, IFC,
   photos) are not removed from storage. No lifecycle policy exists for them, so
   none was invented. The dialog says the deletion is permanent.
3. **Role edits take no verification code in production** while a single
   person's override does (unchanged since the first pass).

## Frontend

- **Unit tests:**
  - `DeleteProjectDialog.test.tsx`: impact shown; disabled until the name is
    typed; cancel sends nothing; success only after a 2xx; a 403 keeps the
    project; a failed impact load blocks deletion.
  - `AccessControlPage.test.tsx`: effective answer, override state and reason
    per row; failed save keeps state.
  - `permission.store.test.ts`: revalidation on focus and after a 403.
- **Editors:** both show each code's server-checked prerequisite
  (`PREREQUISITES` in the catalogue, served by `/access-control/permissions`),
  and the person editor adds "Takes effect only on projects the person can open"
  for every project-scoped code.
