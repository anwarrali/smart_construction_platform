# Construction Project Management Platform — Core Audit Report

Date: 2026-07-13

## Outcome

The existing application was reviewed before changes were made. Working modules were preserved. Confirmed gaps were implemented and deployed to the current Docker stack. The live database is now on Alembic revision `r19a2e7c94b64`; existing task, assignment, and project-member data was preserved.

## What Already Worked

- Invitation-based authentication, access/refresh tokens, forced password change, logout revocation, and role-based backend authorization.
- Administrator user create/edit, role/status/specialty management, activate/deactivate endpoints, and project-team management.
- Project Manager access limited to assigned projects, project dashboards, project team management, task CRUD, multiple task assignees, priorities, disciplines, dates, dependencies, issues, reports, documents, and design changes.
- Inclusive task duration calculation across backend, API responses, forms, dashboard calculations, Gantt, and CPM.
- Dependency validation, circular-dependency prevention, Gantt dependency arrows, and dependency-network Critical Path Method calculations. The longest individual task is not used as a critical-path fallback.
- In-app notifications, read/unread state, user notification preferences, Telegram identifiers/preferences, audit logs, responsive modal forms, and project-scoped consultant access.

## Confirmed Gaps

- Milestones existed only as an unused legacy task flag; there was no normalized milestone model, CRUD workflow, task linking, progress calculation, or dashboard integration.
- Internal messages had constants and permission labels but no database model, API, page, or notification integration.
- Only an assigned Consultant could approve/reject task reviews; the assigned Project Manager could not review.
- Task rejection comments were optional and the frontend silently supplied a generic fallback.
- Review history stored user IDs but did not return/display submitter and reviewer identities.
- Administrator password reset existed only as an unconnected backend endpoint.
- The public reset-password URL had no frontend route/page.
- Engineer affiliation supported only two values and merged internal engineers with main-contractor engineers.
- Frontend permissions incorrectly showed task creation to Engineers although the backend correctly denied it.
- Owner recent activity still referenced the removed single-assignee property.
- Email delivery was a development log stub and could expose invitation/reset content in logs.

## Implemented

### Administrator and Account Access

- Connected Administrator Reset Password to the Users page, with confirmation and a forced password change on next login.
- Added audit logs for user create/update, deactivate/reactivate, and administrator password reset.
- Added account-reactivation and password-reset notifications.
- Added a complete public reset-password page and route.
- Invalidated every outstanding reset token after either a successful self-service reset or an administrator reset.
- Added optional SMTP delivery configuration and removed credential/reset-link logging.
- Separated engineer affiliation into `internal_engineer`, `external_consultant`, and `main_contractor`, with backend role validation and matching UI/filter labels.

### Milestones

- Added normalized `milestones` storage with project-scoped codes (`MLS-001`, etc.) and a task-to-milestone foreign key.
- Added project-scoped CRUD APIs protected by backend project-management RBAC.
- Added task linking, calculated progress, completed/pending/delayed state, and completion counts.
- Added Milestones pages for Project Managers and Administrators.
- Added milestone metrics to project and portfolio dashboards.
- Added read-only milestone markers to Gantt. Markers depend visually on linked tasks and are excluded from CPM, so milestones cannot corrupt the task dependency calculation.
- Added milestone audit logs and notifications to affected task assignees.

### Review and Approval

- Assigned Consultants and the assigned Project Manager can approve or reject work under review.
- Rejection now requires a nonblank backend-validated comment.
- Rejection produces `rework_required`; Engineers can modify progress and resubmit; approval produces `done` plus `reviewStatus=approved`.
- Full immutable review records include submitter and reviewer identities and are displayed with timestamps.
- Submission notifications are sent to eligible Consultants and the assigned Project Manager; feedback is sent to all task assignees.

### Messages and Notifications

- Added normalized, direct project messages with sender, receiver, project, content, timestamps, and read/read-at state.
- Added project-access and active-recipient validation on every message API.
- Added participant, conversation, unread-count, send, and mark-read APIs.
- Added a responsive Messages page for Project Managers, Consultants, Engineers, and Owners, with immediate local updates, focus refresh, and 15-second background refresh.
- Every message creates an in-app notification and an audit record without writing message content into the audit log.
- Notifications remain decoupled from Telegram: messages produce normal domain notifications, while existing user Telegram preferences/chat IDs are retained for a future delivery adapter.

## Verification

- Python syntax compilation: passed.
- Existing unit tests: 8/8 passed, including all requested inclusive-duration examples and dependency-based CPM path ordering.
- Frontend production Docker build: passed (2,828 modules transformed).
- Backend production Docker build: passed.
- Migration verification on an isolated PostgreSQL database: full upgrade, downgrade to `q18`, and re-upgrade to `r19` passed.
- Isolated end-to-end workflow: passed for Admin provisioning, three affiliation types, activation, PM/Consultant project assignment, task creation, inclusive duration, Engineer submission, mandatory PM rejection, rework/resubmission, PM approval, review identities/history, milestone/Gantt/dashboard integration, messaging/read state/notifications, RBAC denial, audit logs, and Administrator password reset.
- Live smoke verification: backend healthy, frontend HTTP 200, project dashboard/Gantt/milestone/message participant APIs HTTP 200, migration at `r19a2e7c94b64`, and backend logs contain no runtime errors.
- Live data after deployment: 55 tasks and 45 project memberships preserved; the new milestone and message tables started empty rather than receiving fabricated production data.

## Recommendations

- Configure `SMTP_HOST`, `SMTP_FROM_EMAIL`, and credentials in the deployment secret store before relying on self-service email delivery. Administrator temporary-password recovery is already operational without SMTP.
- Implement the Telegram delivery adapter later as a consumer of existing notifications and user Telegram preferences; the core notification/message domain does not need redesign.
- Add CI that runs the unit suite, isolated migration test, E2E script, and frontend production build on every pull request.
- Add browser automation (Playwright or equivalent) for responsive form layout, keyboard accessibility, and the main role workflows.
- Code-split the frontend bundle; the production build succeeds, but the main JavaScript chunk is approximately 708 KB before gzip.
- Decide whether the dormant cost-validation backend module is a supported product module before registering it; it currently has no routed API or frontend workflow.
- Plan a separate, backed-up cleanup migration for obsolete legacy tables/flags only after confirming no external integration still consumes them. They were intentionally not deleted during this work.
