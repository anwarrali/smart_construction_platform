# Consultant Engineer Completion Report

Date: 2026-07-15

## Outcome

The Consultant Engineer side is now implemented as the existing global `Engineer` role with:

- `engineer_affiliation = external_consultant`
- specialization/discipline = Civil, Architectural, Electrical, or Mechanical
- active membership in the selected project with project role `Consultant`

It is integrated with the same projects, tasks, submissions, documents, attachments, issues, site reports, notifications, audit logs, and Project Workspace context already used by the rest of the platform. No Consultant-only task copy, fake frontend dataset, external notification API, AI feature, or replacement project was added.

## Audit summary

### Already present and reused

- Unified user and engineer-profile data, including discipline and affiliation.
- Project membership and project-level roles.
- Task dependencies, CPM scheduling, milestones, comments, attachments, issues, documents, site reports, notifications, and audit logs.
- Main Contractor Engineer execution flow and `Under Review`/`Rework Required` task states.
- A basic `TaskReview` record.
- Existing authentication, project context, frontend design system, route structure, and API client.

### Gaps found

- Consultant access still depended on the legacy global `Consultant` role in several places.
- Review-required behavior was effectively universal and was not configurable per task.
- The existing review record could not preserve complete submissions, clarification, corrective actions, or resubmission lineage.
- Consultant access was not consistently project- and discipline-scoped across supporting modules.
- There was no project-specific Consultant dashboard, pending-review list, review detail workflow, or history page backed by dedicated queries.
- Final review actions lacked sufficient concurrency protection and complete mandatory-field validation.
- Review approval was not consistently represented as the dependency approval gate.

## Implementation summary

### Identity and authorization

- Added centralized Consultant Engineer detection: active `Engineer` + `external_consultant`.
- Added backend checks for authentication, active account, exact global role, organization side, project membership, project role, task project, review eligibility, and discipline.
- Direct task/project URL access is denied when membership, discipline, or submission authorization does not match.
- Legacy Consultant users are migrated to the unified Engineer identity without changing their project memberships.

### Review data and workflow

- Added per-task `review_required` and optional `review_due_date`.
- Extended `TaskReview` with submission number/timestamps, completion note, evidence snapshot, reviewer/timestamp, corrective action, clarification lifecycle, and resubmission link.
- Contractor evidence is snapshotted at submission and old attempts are preserved.
- Added start review, clarification request/response, approve, reject/request rework, comments, and review attachments.
- Approval and rejection use row locking and active-submission validation to prevent conflicting or repeated final decisions.
- Consultant identity is always derived from the authenticated session.

### Consultant workspace

- Project selection uses the existing Project Workspace context.
- Added project-specific Dashboard, Pending Reviews, Review Detail, and Review History pages.
- Added supervision-only sidebar navigation to working modules: Dashboard, Pending Reviews, Review History, Documents, Site Reports, Issues, and Notifications.
- Dashboard and lists use database-backed API values with loading, error, and empty states.
- Filters include priority, decision/review status, critical, overdue, resubmission, dependency-blocking, and text search where applicable.

### Supporting modules

- Documents and Site Reports are read-only for Consultant Engineers and project scoped.
- Task-linked records are discipline scoped.
- Consultant Engineers can add review attachments, review comments, and permitted issue observations without altering contractor evidence or submitted reports.
- Internal notifications are generated for submission, clarification, rejection/rework, resubmission, and approval events.
- Important review actions create audit/activity records.

## Consultant Engineer permissions matrix

| Capability | Allowed | Enforcement |
|---|---:|---|
| View assigned projects | Yes | Active project membership |
| View submitted review-required tasks | Yes | Project + Consultant project role + discipline + active submission |
| View project progress summary | Yes, read-only | Backend project-scoped aggregation |
| Start/review a submission | Yes | Valid active review state |
| Add review comment/attachment | Yes | Project, discipline, and active review validation |
| Request clarification | Yes | Task remains `Under Review` |
| Approve | Yes | Row lock, active submission, specialization, and state checks |
| Reject/request rework | Yes | Mandatory reason, comments, and corrective action |
| View documents/site reports/issues | Yes | Assigned project; task-linked data is discipline scoped |
| Update execution progress | No | Backend returns 403 |
| Start contractor execution task | No | Backend organization-side authorization |
| Create execution tasks | No | Backend role/side authorization |
| Change schedule, dates, priority, dependencies, or assignment | No | Planning endpoints remain PM-only |
| Manage contractor team/users/projects | No | Backend RBAC and project-role checks |
| Review another discipline | No by default | Backend discipline validation |
| Approve the same/superseded submission twice | No | Active review validation, locking, and unique active-submission constraint |

## Approval-gate logic

Approval is task- and dependency-specific:

1. The Project Manager decides whether a task requires Consultant review.
2. A review-required task at 100% is submitted and becomes `Under Review`; it is not complete yet.
3. Only dependent tasks whose dependency chain includes that task remain unstartable.
4. Rejection moves the task to `Rework Required` and keeps those dependent tasks blocked.
5. Resubmission creates a new numbered review attempt and preserves the previous decision/evidence.
6. Consultant approval marks the valid active review approved and changes the task to `Done`.
7. Existing dependency checks then allow eligible dependent tasks to start.
8. Unrelated parallel tasks are never frozen by this review.

Tasks with `review_required = false` use the contractor execution-completion action and do not receive a fake Consultant approval.

## Database migration

- `backend/alembic/versions/s20b3f8d05c75_consultant_engineer_reviews.py`
  - Converts legacy global Consultant identities to Engineer/external-consultant.
  - Adds task review requirement and due date.
  - Extends review submission/history fields.
  - Adds review indexes, self-reference, and a partial unique constraint for one active submission per task.

Verified database revision: `s20b3f8d05c75 (head)`.

## API additions and modifications

### Consultant queries

- `GET /api/v1/consultant/projects/{project_id}/dashboard`
- `GET /api/v1/consultant/projects/{project_id}/reviews`
- `GET /api/v1/consultant/projects/{project_id}/reviews/{review_id}`
- `GET /api/v1/consultant/projects/{project_id}/history`

### Review workflow

- Existing task create/update/read/list endpoints now carry and enforce review settings.
- Contractor submission endpoint creates immutable numbered review attempts.
- Added/updated actions for start review, approve, reject/rework, clarification request, clarification response, review history, and non-review execution completion.
- Existing comment, attachment, document, site-report, issue, project, and notification APIs were reused with Consultant authorization added.

## Files changed

### Backend

- `backend/app/core/deps.py`
- `backend/app/models/task.py`
- `backend/app/schemas/task.py`
- `backend/app/api/tasks.py`
- `backend/app/api/consultant_reviews.py`
- `backend/app/api/__init__.py`
- `backend/app/api/projects.py`
- `backend/app/api/attachments.py`
- `backend/app/api/documents.py`
- `backend/app/api/site_reports.py`
- `backend/app/api/issues.py`
- `backend/app/api/notifications.py`
- `backend/app/schemas/user.py`
- `backend/app/api/users.py`
- `backend/app/services/user_service.py`
- `backend/app/db/seed.py`
- `backend/alembic/versions/s20b3f8d05c75_consultant_engineer_reviews.py`
- `backend/tests/live_consultant_engineer_workflow.ps1`

### Frontend

- `frontend/src/app/router/ConsultantEngineerGuard.tsx`
- `frontend/src/App.tsx`
- `frontend/src/utils/constants.ts`
- `frontend/src/components/shared/Sidebar/Sidebar.tsx`
- `frontend/src/features/dashboard/DashboardSelectorPage.tsx`
- `frontend/src/features/dashboard/consultant/pages/ConsultantDashboard.tsx`
- `frontend/src/features/dashboard/consultant/pages/ConsultantReviewsPage.tsx`
- `frontend/src/features/dashboard/consultant/pages/ConsultantReviewDetailPage.tsx`
- `frontend/src/features/projects/context/ProjectWorkspaceContext.tsx`
- `frontend/src/features/projects/pages/ProjectsPage.tsx`
- `frontend/src/features/projects/pages/ProjectTeamPage.tsx`
- `frontend/src/features/tasks/components/TaskForm.tsx`
- `frontend/src/features/tasks/pages/EngineerTaskDetailPage.tsx`
- `frontend/src/features/users/components/UserForm.tsx`
- `frontend/src/features/documents/pages/DocumentsPage.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/services/endpoints.ts`
- `frontend/src/types/consultant.ts`
- `frontend/src/types/task.ts`

## Minimal changes outside the Consultant module

- PM task create/edit exposes the per-task review requirement and optional review due date.
- Main Contractor Engineer submission now creates the versioned review record; non-review tasks use execution completion.
- Admin user/team forms represent Consultants as Engineer + external-consultant and map them to the project Consultant role.
- Reviewed-task deletion now clears dependency edges, review attempts, and polymorphic attachments safely; it does not delete user accounts or projects.

No Administrator, Project Manager, Main Contractor Engineer, Owner, authentication, project-context, or design-system module was rewritten.

## Test results

- End-to-end Consultant workflow: **PASS** (`a288e2a5`).
  - Project scoping and RBAC.
  - Submission and approval gate.
  - Evidence, comments, review attachment, and clarification.
  - Rejection, rework, resubmission history, approval, and duplicate-decision protection.
  - Discipline separation and execution/planning restrictions.
  - Dashboard/notifications plus Admin, PM, and Main Contractor Engineer regression checks.
- Backend schedule/CPM unit tests: **8/8 PASS**.
- Frontend production Docker build: **PASS**.
- Browser smoke test: Consultant project selection, project dashboard, Pending Reviews, and Review History loaded with real empty/data states and correct supervision navigation.
- Alembic migration: **head applied**.
- Temporary test tasks, attachments, notifications, and audit identifiers were removed from the development database after verification.

## Remaining limitations

- The current architecture uses `TaskReview` as the lightweight inspection/review record; a separate enterprise WIR/inspection scheduling module was intentionally not created.
- Review drafts are represented by starting a review and saving comments/attachments; there is no separate complex draft document editor.
- Explicit cross-discipline override is not enabled. Cross-discipline review is rejected by default, which is the safer requested behavior.
- Document annotations and drawing markup depend on the existing attachment/comment capabilities; no new CAD/PDF annotation engine was added.

## Future opportunities (not implemented)

- Telegram/email adapters can subscribe to the structured internal notification events without redesigning review services.
- AI could later assist with document comparison, specification checks, evidence classification, review-note drafting, and risk prioritization, but every decision should remain human-authorized and auditable.
- A future WIR module could add inspection appointments, checklists, signatures, and follow-up dates while continuing to link to the existing task and review history.

