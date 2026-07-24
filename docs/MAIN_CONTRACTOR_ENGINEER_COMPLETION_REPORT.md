# Main Contractor Engineer Completion Report

## Scope

This implementation completes the execution workspace for users with global role `Engineer`, organization side `main_contractor`, an active account, and an active project membership. Consultant Engineer approval UI and external notification channels are intentionally outside this scope.

## Audit outcome

The platform already had reusable project memberships, many-to-many task assignments, task dependencies, milestones, CPM scheduling, reviews, issues, reports, documents, notifications, audit logs, and upload storage. The existing Engineer dashboard was design/drawing-oriented, used company-wide task data, lacked project context, and relied on frontend permissions that did not prevent direct object access. Task execution actions, blocker handling, controlled progress, evidence submission, draft site reports, and discipline validation were incomplete.

The implementation reuses the existing models and Project Manager workflow. No parallel project context, task model, issue model, report model, review model, or notification system was introduced.

## Completed functionality

- Role/side/account guard for active Main Contractor Engineers.
- Active project membership and direct task-assignment checks on the backend.
- Project-scoped login navigation and a single reused project workspace context.
- Engineer-only sidebar: Dashboard, My Tasks, Site Reports, Issues, Documents, Notifications.
- Real database dashboard metrics, due/overdue/review/rework lists, activity, and notifications.
- Assigned-task list with search and status, priority, discipline, date, critical, overdue, review, and rework filters.
- Task detail with dependencies, milestone, assignees, review history, comments, attachments, issues, documents, blockers, and activity.
- Start, progress, work update, blocker, resume, submit-review, rework, and resubmission workflows.
- Progress range and non-decrease validation, with an explicit rework exception.
- Discipline/specialization validation for task assignments.
- Task evidence uploads with extension, MIME, binary signature, size, ownership, state, and project validation.
- Engineer-created issues and Project Manager-visible blockers using the existing Issue model.
- Draft/edit/submit own site reports; submitted reports cannot be silently overwritten.
- Internal structured notifications and audit/activity records.
- Engineer financial, project-team, company-task, schedule, Admin, and global management data restrictions.

## Permission matrix

| Capability | Main Contractor Engineer |
| --- | --- |
| View active assigned projects | Allowed |
| View assigned tasks in selected project | Allowed |
| Access another project/task by URL | Denied by backend |
| Start own To Do task | Allowed when dependencies/blockers permit |
| Update own In Progress task | Allowed with validation |
| Decrease progress | Denied except recorded rework/rejection |
| Add work update/comment/evidence | Allowed on own authorized task |
| Report blocker or issue | Allowed |
| Resolve major issue/blocker | Denied; Project Manager action |
| Submit execution for review | Allowed at 100% progress |
| Edit freely while Under Review | Denied |
| Approve/reject own work or mark it Done | Denied |
| Create projects/users or change roles | Denied |
| Manage the full project team | Denied |
| Access project financials/global schedule | Denied |

## API changes

New Engineer execution capabilities:

- `GET /dashboard/engineer/projects/{project_id}`
- `PUT /tasks/{task_id}/start`
- `PUT /tasks/{task_id}/start-rework`
- `PUT /tasks/{task_id}/progress`
- `POST /tasks/{task_id}/work-updates`
- `GET|POST /tasks/{task_id}/blockers`
- `PUT /tasks/{task_id}/resume-after-blocker`
- `GET /tasks/{task_id}/activity`

Existing APIs reused and secured include projects, task list/detail/comments/reviews/submit-review, issues, attachments, documents, site reports, notifications, milestones, memberships, audit logs, and Project Manager issue/review views.

## Database and migrations

No migration was required. The implementation uses existing normalized `ProjectMember`, task-assignee, `TaskReview`, `Issue`, `TaskComment`, `Attachment`, `SiteReport`, `Notification`, and `AuditLog` structures. Blockers are typed Issues, and work updates are typed task comments plus audit metadata, avoiding duplicate tables.

## Verification

- Python import and syntax checks: passed.
- Inclusive duration and dependency CPM regressions: 8/8 passed.
- Production frontend Docker build: passed (2,830 modules).
- Live Main Contractor Engineer workflow: passed all 18 grouped checks covering the requested 30 security/workflow cases.
- Frontend and backend health: HTTP 200.
- Browser smoke test: Engineer demo login, multi-project selection, scoped dashboard/sidebar, My Tasks filters/empty state, and route isolation passed with zero console errors.
- Docker services: database, backend, and frontend running.
- Temporary E2E projects remaining: 0.
- Hardcoded legacy Engineer dashboard data scan: no matches in the new Engineer pages.

The live test covers login, project/task isolation, URL IDOR, task start, progress validation, dashboard refresh, comments, work updates, valid/invalid files, blockers, Project Manager visibility, issues, review submission, self-approval denial, rework, resubmission history, RBAC, discipline validation, site report draft/submission, notifications, and audit logs.

## Files changed

Backend areas: `core/deps.py`; task model/schema/API; dashboard API; issues API; attachments API; documents API; projects API; notifications API; scheduling API; site report schema/API; file storage; notification service; Engineer E2E test.

Frontend areas: router and Main Contractor Engineer guard; project workspace context; dashboard selector and Engineer dashboard; sidebar; projects page; tasks list/detail; issues; reports; documents uploader; notifications; API endpoints/types; role/permission utilities.

## Known environment note

The running backend and live API tests are healthy. A clean backend image dependency-install layer cannot currently reach PyPI because Docker's network path rejects the issuer certificate (`CERTIFICATE_VERIFY_FAILED`). This is a workstation/corporate CA trust-chain issue, not an application failure. Do not disable TLS verification; install the organization CA in Docker's trust store or build through the approved package mirror. The frontend image builds reproducibly.

## Future Consultant Engineer phase

Add a Consultant-side guard and project-scoped review queue on top of the existing `TaskReview` records; authorize approve/reject with mandatory rejection details; expose versioned evidence and preserved review attempts; generate structured approval/rework notifications. Do not change Main Contractor Engineer submission semantics or allow self-review.
