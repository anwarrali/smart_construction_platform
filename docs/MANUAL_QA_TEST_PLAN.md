# StructIQ — Manual QA Test Plan

A browser test plan for the platform **as implemented on branch
`feat/ingestion-reliability`** (commit `fe489dc` plus uncommitted work, inspected
2026-10-09). Every route, label, limit and expected result below was read from
the code, not from earlier reports or proposals. Where the plan depends on
something the repository cannot tell (passwords, your choice of test project),
it says so.

**How to use it.** Do the environment checklist (§3) once. Then run the test
cases in the order of §6, ticking one box per case. When a case fails, fill in
the template in §7. Steps are written so you do not need to open the code.

**Result legend.** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested` — tick one.
*Blocked* means a prerequisite is missing (service down, no account), not that
the feature is wrong.

---

## Contents

1. [Application inventory](#1-application-inventory)
2. [Recent changes and what needs special attention](#2-recent-changes-and-what-needs-special-attention)
3. [Environment setup checklist](#3-environment-setup-checklist)
4. [Test cases](#4-test-cases)
   - [4.1 Smoke](#41-smoke-sm) · [4.2 Authentication](#42-authentication-au) · [4.3 Projects](#43-projects-and-workspace-pr)
   - [4.4 Permissions and isolation](#44-permissions-and-project-isolation-pe) · [4.5 Files panel — ingestion](#45-files-panel--ingestion-fi)
   - [4.6 Indexing and the index badge](#46-indexing-and-the-index-badge-ix) · [4.7 Documents library and Document Assistant](#47-documents-library-and-document-assistant-do)
   - [4.8 Other modules](#48-other-implemented-modules-mo) · [4.9 Regression and reliability](#49-regression-and-reliability-re)
5. [Test data checklist](#5-test-data-checklist)
6. [Execution order](#6-execution-order)
7. [Defect report template](#7-defect-report-template)
8. [Coverage and limitations](#8-coverage-and-limitations)
9. [QA pass 2026-10-17 — defect register and retest cases](#9-qa-pass-2026-10-17--defect-register-and-retest-cases)

---

## 1. Application inventory

### 1.1 How access works (read this first)

The app decides **everything by permission, not by role name.** A sidebar item
appears only if your account holds its permission; opening a guarded URL
without the permission sends you to `/dashboard`. After login you land on a
page chosen the same way:

| You hold… | You land on |
| --- | --- |
| `platform.manage_users` | `/admin` (Platform dashboard) |
| `project.manage_members` or `platform.create_project` | `/dashboard` (Project-manager dashboard) |
| `client_portal.view` and you are external | `/owner-dashboard` |
| `task.review` | `/dashboard` (Consultant dashboard) |
| `task.view` | your only project's **My tasks**, or `/projects` |
| none of the above | `/projects` |

Default permissions of the six seeded roles (an office can edit roles, so your
database may differ — check **Roles & disciplines** if a result surprises you).
"stripped" = the role lists it, but the server removes it for people outside
the office.

| Permission | org_admin | project_manager | senior_engineer | contractor_rep. | client_rep. | site_engineer |
| --- | :-: | :-: | :-: | :-: | :-: | :-: |
| platform.manage_users | ✔ | – | – | – | – | – |
| platform.create_project / project.edit | ✔ | – | – | – | – | – |
| project.manage_members | ✔ | ✔ | – | – | – | – |
| task.view | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| task.create | ✔ | ✔ | – | – | – | – |
| task.update_progress | ✔ | ✔ | ✔ | ✔ | – | ✔ |
| task.review | ✔ | ✔ | ✔ | stripped | – | ✔ |
| document.view | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| document.upload | ✔ | ✔ | ✔ | ✔ | – | ✔ |
| site_report.submit | – | ✔ | ✔ | ✔ | – | ✔ |
| site_report.verify | – | ✔ | – | – | – | – |
| issue.create | ✔ | ✔ | ✔ | ✔ | – | ✔ |
| issue.resolve | ✔ | ✔ | – | – | – | – |
| design_change.propose | ✔ | ✔ | ✔ | ✔ | – | ✔ |
| design_change.approve | – | – | ✔ | stripped | – | ✔ |
| schedule.view | ✔ | ✔ | – | – | ✔ | – |
| ifc.view | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| ifc.upload | ✔ | ✔ | ✔ | ✔ | – | ✔ |
| client_portal.view | ✔ | – | – | – | ✔ | – |
| message.send | ✔ | ✔ | ✔ | ✔ | – | ✔ |
| message.broadcast | ✔ | ✔ | – | – | – | – |

### 1.2 Pages

All URLs are relative to the frontend, `http://localhost:5173`.
`:projectId` is the id in the address bar after you open a project.

**Public**

| Page | URL | Status |
| --- | --- | --- |
| Landing page | `/` | Implemented |
| Login | `/auth/login` | Implemented |
| Forgot password | `/auth/forgot-password` | Implemented; **no email is sent** locally (SMTP not configured) |
| Reset password | `/auth/reset-password?token=…` | Implemented; unreachable without the email (see §8) |
| Not found | any unknown URL | Implemented |

**Portfolio (left sidebar, outside a project)**

| Sidebar label | URL | Permission | Notes |
| --- | --- | --- | --- |
| Platform dashboard | `/admin` | platform.manage_users | |
| Portfolio dashboard | `/dashboard` | — | permission-based landing page |
| Owner dashboard | `/owner-dashboard` | client_portal.view | also `/executive-overview` |
| My actions | `/my-actions` | — | Collaboration, "actions" tab |
| My projects | `/projects` | — | list, create (admin), open |
| My schedule | `/schedule` | — | Collaboration, "schedule" tab (site visits) |
| Tasks across projects | `/tasks` | task.view | |
| Client requests | `/requests` | — | Collaboration, "requests" tab |
| Project documents | `/documents` | document.view | library across projects; Files panel only appears inside a project |
| People & access | `/users` | platform.manage_users | create/edit/deactivate users |
| Project teams | `/admin/project-teams` | platform.manage_users | |
| Permissions | `/admin/access-control` | platform.manage_permissions | per-person overrides; "Roles" tab links to Roles page |
| Roles & disciplines | `/admin/roles` | org.manage_roles | edit role permissions |
| Messages | `/messages` | — | |
| Notifications | `/notifications` | — | |
| Settings / profile | `/settings` | — | profile, password; `/auth/change-password` opens the same page |
| MCP clients | `/settings/mcp-clients` | — | not in sidebar; MCP is **enabled** on this stack |
| Site reports / Issues / Design changes / Milestones (portfolio) | `/site-reports`, `/issues`, `/design-changes`, `/milestones` | site_report.view, issue.view, design_change.view, schedule.view | reachable by URL; `/reports` redirects to `/site-reports` |

**Project workspace (sidebar after opening a project)**

| Group | Sidebar label | URL `/projects/:projectId/…` | Permission |
| --- | --- | --- | --- |
| Plan | Project overview | `dashboard` | task.view |
| Plan | My tasks | `my-work` | task.view |
| Plan | Tasks | `tasks`, `tasks/:taskId` | task.view |
| Plan | Pending reviews | `review-queue` (+ `reviews`, `history`) | task.review |
| Plan | Schedule / Gantt | `schedule` (+ `milestones`) | schedule.view |
| Control | Issues | `issues` | issue.view |
| Control | Design changes | `design-changes` | design_change.view |
| Control | Client requests | `requests` | task.view |
| Field | Voice Assistant | `voice-assistant` | task.view — uses real OpenAI calls |
| Field | Voice reports | `voice-reports` | field_evidence.verify |
| Field | Site reports | `site-reports` | site_report.view |
| Field | Site visits | `site-visits` | task.view |
| Field | Project information | `evidence` | task.view (photo/evidence archive) |
| Reference | Documents | `documents` | document.view — **library + Files panel** |
| Reference | IFC / BIM | `ifc` | ifc.view |
| Reference | AI insights | `ai-intelligence` | ai.view_insights |
| Reference | Agents | `agents` | task.view |
| Team & activity | Collaboration | `collaboration` | task.view |
| Team & activity | Messages | `messages` | task.view |
| Team & activity | Team | `team` | project.manage_members |
| Team & activity | Project parties | `parties` | project.manage_parties |
| Team & activity | Activity | `activity` | task.view |

Old per-role addresses (`/project-manager/projects/…`, `/engineer/projects/…`,
`/consultant-engineer/projects/…`) are kept as redirects to `/projects/…`.

### 1.3 Background services behind the UI

| Feature | Runs where | Needs |
| --- | --- | --- |
| File processing (Files panel) | `worker` container, job `ingestion.process_file` | worker running |
| Automatic indexing of files | `worker`, job `rag.index_file` | worker, `RAG_ENABLED`, `RAG_AUTO_INDEX_ENABLED`, OpenAI key — **costs money** |
| Automatic indexing of library PDFs | `worker`, job `rag.index_document` | same as above |
| Manual "Index for AI" in Document Assistant | inside the API request (synchronous) | OpenAI key — **costs money** |
| Document Assistant questions | API | OpenAI key — **costs money** |
| IFC parse / geometry | `worker`, jobs `ifc.process_version` / `ifc.generate_geometry` | worker |
| Voice assistant | API | microphone, OpenAI key — **costs money** |
| Push notifications | API | **enabled** (Firebase configured) — real devices may be notified |
| Email | — | **not configured** (no SMTP); emails are logged, not sent |
| Realtime updates | API (SSE) | enabled |
| Automatic agent analysis | — | **off** (`AGENT_AUTO_ANALYSIS_ENABLED=false`); agents run only when you press Run |

Effective switches on the running API (read 2026-10-09): `RAG_ENABLED=true`,
`RAG_AUTO_INDEX_ENABLED=true`, `INGESTION_BACKGROUND_PROCESSING_ENABLED=true`,
`JOB_RUNNER_EMBEDDED=false` (the worker container does the work),
`PUSH_ENABLED=true`, `MCP_ENABLED=true`, `VOICE_FEATURE_ENABLED=true`,
`IFC_ENGINEER_UPLOAD_ENABLED=false`, `ACCESS_TOKEN_EXPIRE_MINUTES=30`,
`LOGIN_MAX_ATTEMPTS=10` per 15 minutes.

### 1.4 File rules (from the upload gate)

| | Files panel (unified ingestion) | Documents library |
| --- | --- | --- |
| Accepted extensions | `.pdf .doc .docx .xls .xlsx .txt .jpg .jpeg .png .webp .dwg .dxf .ifc .zip` | `.pdf .doc .docx .xls .xlsx .txt .jpg .jpeg .png .dwg` |
| Size limit | 200 MB (IFC models via the IFC workspace: 500 MB) | 25 MB |
| Wrong type | **415** "Unsupported file type…" | 415 |
| Contents don't match extension | **415** "File content does not match its extension" | 415 |
| Empty file | **400** "Uploaded file is empty" | 400 |
| Too large | **413** "File exceeds the … MB limit" | 413 |
| IFC without IFC upload permission | **403** "IFC upload permission required for model files" | n/a |

What happens after a Files-panel upload, per type:

| Type | Processing result | Index badge expected |
| --- | --- | --- |
| PDF with a text layer | Ready | Indexing… → **Searchable** |
| PDF with no text layer (scan) | **Partially processed** — "No readable text in this document" | none |
| DOCX with text | Ready | Indexing… → **Searchable** |
| TXT | Ready | Indexing… → **Searchable** |
| XLSX | Partially processed — "This format is stored but not parsed" (sheet names only) | none |
| DOC / XLS (old Office) | Partially processed — "stored but not parsed" | none |
| JPG / PNG / WEBP | Ready (stored, no text) | none |
| DWG / DXF | Partially processed — "stored but not parsed" | none |
| IFC via Files panel | Partially processed (header read only; full model work belongs to the IFC workspace) | none |
| ZIP | Ready (or Partially processed if some entries were skipped); each member listed as its own row marked "from a package" | per member, by its own type |
| ZIP inside a ZIP | the inner ZIP is stored but not expanded ("Package is nested too deeply") | none |
| Byte-identical re-upload | processed normally, row marked "duplicate" | **none** — its text is already searchable through the first copy |
| Corrupt PDF (valid header, broken body) | **Failed** — "Content could not be extracted" + **Retry** button | none |

Indexing is skipped for files over 25 MB (`RAG_MAX_FILE_MB`).

---

## 2. Recent changes and what needs special attention

| Change | Where | Why it needs testing |
| --- | --- | --- |
| **Durable job queue + dedicated worker** (`fe489dc`) | `backend/app/services/jobs/`, `app/worker.py`, `docker-compose.yml` (`worker` service) | All file processing, IFC processing and indexing moved off the API onto the worker. If the worker is down, uploads are accepted but nothing progresses. |
| **Automatic indexing of Files-panel uploads** (`fe489dc`) | `services/ingestion/pipeline.py`, `services/rag/ingestion.py` | New behaviour: text files become searchable without any button. Duplicates and text-less files must **not** be indexed. |
| **Ingestion failures are now real failures** (uncommitted) | `pipeline.py` | A crashed processing run marks the file **Failed** ("Processing did not complete") and is retried automatically, instead of hanging in Queued. |
| **Automatic background indexing of library PDFs** (uncommitted) | `api/documents.py`, `services/rag/ingestion.py`, job `rag.index_document` | Uploading a PDF to the Documents library now indexes it in the background. The Document Assistant's manual "Index for AI" still works synchronously. |
| **Index fields on the file API** (uncommitted) | `schemas/ingestion.py` | `indexStatus`, `indexedAt`, `indexError` now returned for each file. |
| **Index badge in the Files panel** (uncommitted) | `frontend/src/features/ingestion/components/IndexStatusBadge.tsx`, `ProjectFilesPanel.tsx` | New badge (**Indexing…**, **Searchable**, **Indexing failed**); panel keeps refreshing while indexing runs and for up to 2 minutes after a text file finishes processing. |
| **Permission-based frontend** (merged, PR #5) | whole frontend | Login landing page, sidebar and every button now follow permissions. A stale frontend build broke login on 2026-10-09 — see §3 step 4. |
| **Single start sequence** (merged, PR #6) | `backend/Dockerfile`, `docker-compose.yml` | The API runs migrations and seeds roles on start; the worker waits for the schema. |

**Highest regression risk:** login and landing page (permission-based routing),
Files panel uploads (now depend on the worker), Documents upload (now queues a
background job), Document Assistant manual index (must still be synchronous),
and IFC uploads (moved onto the worker).

---

## 3. Environment setup checklist

Run these from the repository root (`C:\projects_final\ConstructionPlatformSoftwareProject`)
in Git Bash or PowerShell. None of these commands change application data.

- [ ] **1. Docker Desktop is running.**
  `docker info --format '{{.ServerVersion}}'` prints a version.
  If it errors, start Docker Desktop and wait. (If Docker Desktop shows a
  startup error dialog, **never** choose "Reset to factory defaults" — it deletes
  every volume, including the database.)

- [ ] **2. The four services are up.**
  `docker compose ps`
  Expect `Construction_db` (healthy), `construction_backend`, `construction_worker`,
  `construction_frontend`, all **Up**. Start any that are missing:
  `docker compose up -d db backend worker frontend`

- [ ] **3. The API answers.** `curl -s http://localhost:8000/health` → HTTP 200.
  Interactive API docs (read-only browsing): `http://localhost:8000/docs`.

- [ ] **4. Images are current — the step that broke login once.** Images are
  built, not linked to your code, so they go stale after merges or edits:
  ```bash
  docker image inspect constructionplatformsoftwareproject-backend constructionplatformsoftwareproject-worker constructionplatformsoftwareproject-frontend --format '{{.RepoTags}} {{.Created}}'
  ```
  All three must be newer than your latest code change. **This branch has
  uncommitted backend and frontend changes**, so rebuild all three before testing:
  ```bash
  docker compose build backend worker frontend
  docker compose up -d backend worker frontend
  ```
  Rebuild backend and worker **together**: a worker older than the API rejects
  the new `rag.index_document` job as an unknown kind.

- [ ] **5. The worker is ready and knows every job kind.**
  `docker compose logs --tail 20 worker` shows `worker ready (queue=default)`.
  ```bash
  docker exec construction_worker python -c "from app.services.jobs.handlers import KINDS; print(sorted(KINDS))"
  ```
  The list must include `rag.index_document` and `rag.index_file`.

- [ ] **6. The API runs its embedded runner off** (the worker does the work):
  `docker compose logs backend | grep -i "embedded job runner"` →
  "embedded job runner disabled; jobs run on a dedicated worker".

- [ ] **7. Open the site.** `http://localhost:5173` (the frontend container; it
  calls the API at `http://localhost:8000/api/v1`, baked in at build time).
  Hard-refresh once (`Ctrl+Shift+R`).

- [ ] **8. Confirm the browser runs the new frontend.** Open DevTools → Network,
  log in, and check that requests go to `http://localhost:8000/api/v1/...`.
  Then in a project's **Documents** page, an already-indexed text file shows a
  green **Searchable** badge next to **Ready**. If no file is indexed yet, this
  check is done during test IX-02.

- [ ] **9. Accounts.** You need the passwords — they are not in the repository.
  Accounts that exist in your database (active, no forced password change):

  | Purpose | Account | Role |
  | --- | --- | --- |
  | Admin | `admin@gmail.com` | org_admin |
  | Project manager | `managerr@gmail.com` | project_manager (PM of *Residential Complex C*) |
  | Senior engineer (internal reviewer) | `civilcons@gmail.com` or `archconst@gmail.com` | senior_engineer |
  | Contractor (external) | `archcont@gmail.com` | contractor_representative |
  | Client (external) | `projectowner@gmail.com` | client_representative (owner of *Residential Complex C*) |
  | Forced password change | `manager@gmail.com` | project_manager, `must_change_password=true` |

  Do **not** use the inactive accounts (`pm@constro.io`, `consultant@constro.io`,
  `owner@gmail.com`, `supervisor@constro.io`, the `@constro.io` engineers,
  `anwar.roumanen@…`) except in AU-05. Accounts and projects with random suffixes
  (`…6d64c05e…`, `…27114cdbeb…`, *Alpha/Beta/Knowledge…* projects) are leftovers
  from automated test runs; ignore them.
  The demo seed (`Al-Nour Residential Building`, `*.demo@smartconstruction-demo.com`)
  is **not** loaded in this database.

- [ ] **10. Isolate your testing (recommended).** Log in as the admin and create
  a dedicated project, e.g. **"QA Manual Test 2026-10-09"** (test PR-02), with
  `managerr@gmail.com` as project manager and `projectowner@gmail.com` as owner.
  Do all uploads there. Use *Residential Complex C* only for read-only checks and
  for cross-project isolation tests, and *Riverside Tower* (where `managerr` is
  **not** a member) as the "other project".

- [ ] **11. Watching logs without changing anything** — keep a terminal open:
  ```bash
  docker compose logs -f --tail 50 worker      # processing and indexing jobs
  docker compose logs -f --tail 50 backend     # HTTP requests and errors
  ```
  Worker lines to look for: `[Jobs] ingestion.process_file … finished`,
  `indexed file …`, `[Jobs] rag.index_file … finished`, `indexed document …`.

- [ ] **12. Read-only database checks** used by some tests (they only `SELECT`):
  ```bash
  docker exec Construction_db psql -U postgres -d construction_platform -c "<query>"
  ```
  The database password and name come from `docker-compose.yml` defaults; if you
  changed them in `.env`, use yours.

**Costs and side effects — know these before you start**

| Action | Real external effect |
| --- | --- |
| Upload a text PDF/DOCX/TXT in the Files panel | one OpenAI **embedding** call per file (automatic) |
| Upload a PDF to the Documents library | one embedding call (automatic) |
| Document Assistant: Index for AI / Re-index | one embedding call |
| Document Assistant: Ask | embedding + answering-model calls |
| Voice assistant | transcription + model calls |
| Uploading a document, assigning tasks, messages, issues… | in-app notifications, and **push notifications to registered phones** (push is enabled) |
| Anything you create | persistent rows in the shared dev database — there is no automatic cleanup |

Keep test files small (a page or two): embedding cost scales with text length.

---

## 4. Test cases

Each case: **ID · Priority · Feature**, then purpose, prerequisites, steps,
expected result, optional read-only verification, failure indicators, result
and evidence. P0 = must pass before anything else is meaningful; P1 = core
workflow; P2 = edge cases and secondary pages.

### 4.1 Smoke (SM)

#### SM-01 · P0 · Application loads
- **Purpose:** the frontend and API are reachable and current.
- **Prerequisites:** §3 steps 1–7.
- **Steps:**
  1. Open `http://localhost:5173`.
  2. Click **Login** (top navigation).
- **Expected:** the landing page renders with the StructIQ logo; the login page
  shows email/username and password fields. No blank page.
- **Verify (optional):** DevTools → Console has no red errors; Network shows the
  JS bundle `/assets/index-….js` loaded with status 200.
- **Failure indicators:** blank white page; endless spinner; 502/connection refused.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`
- **Evidence:** screenshot of the page + Console tab.

#### SM-02 · P0 · Login lands on the right page
- **Purpose:** the regression that broke login on 2026-10-09 — a stale or
  role-based frontend bounced users back to the login page.
- **Prerequisites:** admin account.
- **Steps:**
  1. On `/auth/login`, enter `admin@gmail.com` and the password; click the
     sign-in button.
- **Expected:** you leave the login page and land on `/admin` (Platform
  dashboard). The sidebar shows an **Administration** section.
- **Verify:** `docker compose logs --tail 20 backend` shows
  `POST /api/v1/auth/login 200`, then `GET /api/v1/auth/me 200` and
  `GET /api/v1/access-control/me 200`.
- **Failure indicators:** you stay on (or return to) the login page with no
  message → the frontend image is stale (redo §3 step 4).
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`
- **Evidence:** screenshot, the backend log lines, Network tab of the login.

#### SM-03 · P0 · Navigation has no dead ends
- **Purpose:** every sidebar item opens a working page.
- **Prerequisites:** logged in as admin.
- **Steps:**
  1. Click each item in the left sidebar in turn (Platform dashboard,
     Portfolio dashboard, Owner dashboard, My actions, My projects, My schedule,
     Tasks across projects, Client requests, Project documents, People & access,
     Project teams, Permissions, Roles & disciplines, Messages, Notifications).
  2. Open **My projects** → open *Residential Complex C* → click each item in the
     project sidebar (Plan, Control, Field, Reference, Team & activity groups).
- **Expected:** every page renders a heading and content or an empty-state
  message. Loading indicators disappear within a few seconds.
- **Failure indicators:** blank page, a spinner that never ends, an error toast
  on open, a redirect to `/dashboard` from an item that was shown in the sidebar.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`
- **Evidence:** URL + screenshot + Console of the failing page.

#### SM-04 · P1 · Unknown URL
- **Steps:** open `http://localhost:5173/this-page-does-not-exist`.
- **Expected:** the Not Found page, with a way back.
- **Failure indicators:** blank page or crash.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### SM-05 · P1 · Arabic / RTL
- **Steps:** switch the language to Arabic (language switcher in the top bar or
  profile), then open Projects and a project's Documents page.
- **Expected:** text is Arabic, layout mirrors right-to-left, the Files panel
  badges read in Arabic (e.g. **قابل للبحث** for Searchable).
- **Failure indicators:** raw keys such as `ingestion.index.ready` on screen.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

### 4.2 Authentication (AU)

#### AU-01 · P0 · Wrong password
- **Purpose:** a failed login is reported, not silent.
- **Steps:** enter a valid email with a wrong password; submit.
- **Expected:** a red message "Incorrect username/email or password"; you stay on
  the login page.
- **Failure indicators:** no message; a generic crash; being logged in.
- **Caution:** 10 failed attempts for one email within 15 minutes locks that email
  with "Too many failed sign-in attempts. Try again later." Do this test **once**.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### AU-02 · P1 · Empty fields
- **Steps:** submit the login form with both fields empty.
- **Expected:** a "required" validation message; no request is sent.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### AU-03 · P0 · Logout
- **Steps:** logged in, use the user menu (top bar) → logout.
- **Expected:** you return to the login page. Pressing the browser Back button
  does not show protected pages; opening `/dashboard` sends you to `/auth/login`.
- **Failure indicators:** protected data visible after logout.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### AU-04 · P1 · Protected URL without a session
- **Steps:** in a private window, open `http://localhost:5173/projects`.
- **Expected:** redirect to `/auth/login`.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### AU-05 · P1 · Deactivated account
- **Prerequisites:** an inactive account whose password you know (e.g. one of the
  inactive accounts in §3 step 9), or deactivate a test user you created in MO-14.
- **Steps:** try to log in with it.
- **Expected:** "Your account has been deactivated. Contact your administrator."
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### AU-06 · P1 · Forced password change
- **Prerequisites:** `manager@gmail.com` (has `must_change_password`), or a user
  you create in MO-14 (new accounts must change their password).
- **Steps:**
  1. Log in.
  2. Try to open `/projects` by URL.
- **Expected:** you are sent to `/auth/change-password` and kept there until the
  password is changed; after changing it you can use the app.
- **Failure indicators:** reaching other pages without changing the password.
- **Note:** this permanently changes that account's password.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### AU-07 · P2 · Session refresh after expiry
- **Purpose:** the access token lasts 30 minutes; the app refreshes it silently.
- **Steps:** log in, leave the tab idle for 35 minutes, then click a sidebar item.
- **Expected:** the page loads without asking you to log in (Network shows
  `POST /auth/refresh 200`, then the request succeeds).
- **Failure indicators:** unexpected logout, or repeated 401s in the Network tab.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### AU-08 · P2 · Forgot password (partial)
- **Steps:** on `/auth/forgot-password`, submit your email.
- **Expected:** a neutral confirmation message (the same for any email).
  **No email arrives** — SMTP is not configured. The backend log shows
  "Email delivery is disabled because SMTP_HOST/SMTP_FROM_EMAIL are not configured".
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested` — full reset flow is Blocked (see §8).

### 4.3 Projects and workspace (PR)

#### PR-01 · P0 · Project list
- **Steps:** as admin, open **My projects**.
- **Expected:** a list including *Residential Complex C* and *Riverside Tower*,
  each with an **Open** action.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### PR-02 · P0 · Create the QA project
- **Purpose:** project creation, and the isolated project for the rest of the plan.
- **Prerequisites:** admin (only `platform.create_project` holders see the button).
- **Steps:**
  1. **My projects** → **+ Add Project**.
  2. Name: `QA Manual Test 2026-10-09`. Fill dates/description as you like.
  3. **Owner \***: choose `projectowner@gmail.com` (the list shows only accounts
     the server accepts as a client).
  4. **Project Manager \***: choose `managerr@gmail.com` (only eligible managers
     are listed).
  5. Click **Create Project**.
- **Expected:** success toast; the project appears in the list.
- **Failure indicators:** empty Owner/PM pickers; 4xx error on save.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### PR-03 · P1 · Open and switch projects
- **Steps:** open the QA project; use the project switcher in the sidebar (or
  **All projects**) to open *Residential Complex C*; switch back.
- **Expected:** the URL `/projects/:projectId/…` changes; the page content
  (documents, tasks) belongs to the selected project only.
- **Failure indicators:** data from the previous project still shown after switching.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### PR-04 · P1 · Staff the QA project
- **Prerequisites:** admin or the project's PM.
- **Steps:** in the QA project → **Team** → add `civilcons@gmail.com` (senior
  engineer) as an office member. Optionally add a party under **Project parties**
  (kind: main contractor) and add `archcont@gmail.com` as a member of that party.
- **Expected:** members appear in the team list with their project role.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### PR-05 · P2 · Old addresses redirect
- **Steps:** open `/project-manager/projects/<QA project id>/dashboard`.
- **Expected:** you end up on `/projects/<id>/…` (the current address).
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

### 4.4 Permissions and project isolation (PE)

#### PE-01 · P0 · Landing page per role
- **Steps:** log in, in turn, as `managerr@gmail.com`, `civilcons@gmail.com`,
  `archcont@gmail.com`, `projectowner@gmail.com`. Log out between accounts.
- **Expected:**
  - managerr → `/dashboard` (project-manager dashboard);
  - civilcons → `/dashboard` (consultant / review dashboard);
  - archcont → its project's **My tasks** (if it has exactly one project) or `/projects`;
  - projectowner → `/owner-dashboard`.
- **Failure indicators:** bounced to login; landing on a page that then shows
  "access denied"; the admin dashboard for a non-admin.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### PE-02 · P0 · Sidebar follows permissions
- **Steps:** for each account in PE-01, note which sidebar items appear.
- **Expected:** only the admin sees People & access, Project teams, Permissions,
  Roles & disciplines. The client (`projectowner`) sees no **+ Upload Document**
  button and no Files-panel **Upload file** button (no `document.upload`).
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### PE-03 · P0 · Guarded URL by direct navigation
- **Steps:** as `archcont@gmail.com`, type `http://localhost:5173/users` and then
  `/admin/access-control`.
- **Expected:** redirected to `/dashboard` both times; no user list ever renders.
- **Failure indicators:** the page renders, even briefly with data.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### PE-04 · P0 · Another project's files are not reachable
- **Purpose:** project isolation for files and documents.
- **Prerequisites:** the QA project's id (from its URL); `managerr` is **not** a
  member of *Riverside Tower*. Note *Riverside Tower*'s id (open it as admin).
- **Steps:**
  1. Log in as `managerr@gmail.com`.
  2. Open `http://localhost:5173/projects/<Riverside Tower id>/documents`.
- **Expected:** no Riverside documents or files are shown — an access error,
  an empty page, or a redirect. Riverside does not appear in managerr's project list.
- **Verify:** Network shows the files request answering **403**.
- **Failure indicators:** any Riverside file or document listed.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### PE-05 · P1 · External participant sees only shared documents
- **Prerequisites:** PR-04 done with `archcont` attached to a party in the QA
  project; at least one library document uploaded by someone else (DO-01).
- **Steps:** log in as `archcont@gmail.com`, open the QA project → Documents.
- **Expected:** documents uploaded by the office are **not** listed unless shared
  with archcont's party; archcont's own uploads are listed.
- **Failure indicators:** office documents visible to the contractor by default.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### PE-06 · P1 · Document Assistant respects project boundaries
- **Steps:** as `managerr`, in the QA project, open **Ask AI** on an indexed
  document and ask about content that exists only in a *Riverside Tower* document.
- **Expected:** "Nothing in the indexed text answers this…" — no content from the
  other project.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

### 4.5 Files panel — ingestion (FI)

Where: QA project → **Documents** (Reference group) → the **Project files** card
below the library ("Everything uploaded to this project, and what the pipeline
made of it."). Logged in as admin or `managerr` unless stated.

#### FI-01 · P0 · Upload a text PDF
- **Prerequisites:** sample file **F1** (§5). Worker log open.
- **Steps:**
  1. Click **Upload file**, choose F1.
- **Expected:**
  1. Toast "File accepted. Processing continues in the background."
  2. A row appears: filename, `PDF · <size>`, badge **Queued** → **Processing**
     → **Ready** (green) within seconds, without reloading.
  3. Then the index badge appears: **Indexing…** → **Searchable** (see IX-01/02).
- **Verify:** worker log shows `ingestion.process_file … finished`, then
  `indexed file …` and `rag.index_file … finished`.
- **Failure indicators:** row stuck in Queued > 1 minute (worker down?);
  Failed for a normal PDF; no row at all.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`
- **Evidence:** screenshot of the row; worker log lines.

#### FI-02 · P1 · Upload each supported type
- **Prerequisites:** F3 (DOCX), F4 (TXT), F5 (XLSX), F6 (PNG/JPG), F8 (DXF, optional).
- **Steps:** upload each, one at a time.
- **Expected** (see the table in §1.4):
  - DOCX, TXT → **Ready**, then **Searchable**;
  - XLSX → **Partially processed** (amber), description "The file is kept and
    downloadable; deep reading is not implemented for it.", **no** index badge;
  - PNG/JPG → **Ready**, no index badge;
  - DXF/DWG → **Partially processed**, no index badge.
- **Failure indicators:** XLSX/image showing **Indexing failed**; DOCX/TXT never
  becoming Searchable.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-03 · P1 · Scanned PDF (no text layer)
- **Prerequisites:** F2.
- **Expected:** **Partially processed** — "No readable text in this document";
  no Retry button (not retryable); **no** index badge.
- **Failure indicators:** Failed, or Indexing failed.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-04 · P0 · Unsupported type
- **Prerequisites:** F10 (e.g. a `.csv` or `.md` file).
- **Expected:** red toast with the server message
  "Unsupported file type for ingest"; no row is created.
- **Note:** the file picker filters by accepted extensions — choose "All files"
  in the picker to select it.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-05 · P0 · Misleading extension
- **Prerequisites:** F11 — a plain text file renamed to `fake.pdf`.
- **Expected:** red toast "File content does not match its extension"; no row.
- **Failure indicators:** the file is accepted.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-06 · P1 · Empty file
- **Prerequisites:** F12 — a 0-byte `empty.txt`.
- **Expected:** red toast "Uploaded file is empty"; no row.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-07 · P2 · Size limit
- **Purpose:** the panel refuses an oversized file before uploading
  (the client knows the 200 MB limit from `upload-constraints`).
- **Steps:** choose a file over 200 MB **only if you have one handy** (do not
  generate one just for this).
- **Expected:** toast "This file is larger than the 200 MB limit." immediately,
  with no upload. Otherwise mark *Not tested*; the Documents-library limit
  (25 MB, DO-05) is easier to test.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-08 · P1 · Duplicate upload
- **Steps:** upload F1 again (same bytes; the name may differ).
- **Expected:** a new row marked "· duplicate", processed to **Ready**, and
  **no** index badge (its text is already searchable through the first copy).
- **Failure indicators:** the duplicate gets indexed (Searchable) — the same
  passages would then appear twice in search.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-09 · P1 · Failed file and Retry
- **Prerequisites:** F13 — a corrupt PDF (§5 explains how to make one).
- **Steps:**
  1. Upload F13.
  2. When it shows **Failed**, hover the badge, then click **Retry**.
- **Expected:**
  1. **Failed** (red), description "The file was stored, but reading its contents
     did not succeed.", tooltip with the suggested action, and a **Retry** button.
  2. Retry: toast "Processing has been queued again."; status goes Queued →
     Processing → **Failed** again (the file is still corrupt). That is the
     expected result, not a bug.
- **Failure indicators:** no Retry button on a retryable failure; status stuck in
  Queued; an index badge on a failed file.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-10 · P1 · ZIP package
- **Prerequisites:** F14 — a ZIP containing F1 and F3.
- **Expected:** the ZIP row → **Ready**; one extra row per member, marked
  "· from a package"; each member is processed by its own type (the PDF and DOCX
  members become **Searchable**).
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-11 · P2 · Invalid and nested ZIPs
- **Prerequisites:** F15 (corrupt ZIP: a real ZIP with bytes chopped off the end)
  and F16 (a ZIP containing another ZIP).
- **Expected:**
  - F15 → **Failed** "Package could not be read" with **Retry**;
  - F16 → outer ZIP **Ready** or **Partially processed**; the inner ZIP is listed
    but not expanded ("Package is nested too deeply").
- **Note:** a text file merely renamed to `.zip` is refused at upload (415) —
  that tests FI-05, not this case.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-12 · P1 · IFC through the Files panel
- **Prerequisites:** F7 — `backend/tests/fixtures/minimal_ifc4.ifc`.
- **Expected:** **Partially processed** (header read; full model processing
  belongs to the IFC workspace); **no** index badge.
- **Also test:** as `archcont@gmail.com` (contractor), uploading the same IFC → red
  toast "IFC upload permission required for model files" if the contractor lacks
  IFC upload on this deployment (`IFC_ENGINEER_UPLOAD_ENABLED=false`). Record what
  you see either way.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-13 · P1 · Refresh and navigate during processing
- **Steps:**
  1. Upload F3; while it shows Queued/Processing, press `F5`.
  2. Upload F4; immediately click another sidebar item, wait 30 seconds, return
     to Documents.
- **Expected:** after both, the rows show their real current status (Ready /
  Searchable). Nothing is lost or duplicated.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### FI-14 · P2 · File download
- **Note:** the Files panel has **no download button**. Downloads are tested
  through the Documents library (DO-07). The unified endpoint
  `GET /api/v1/projects/{projectId}/files/{fileId}/download` can be exercised from
  `http://localhost:8000/docs` with a logged-in token if you want backend coverage.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

### 4.6 Indexing and the index badge (IX)

The badge sits to the right of the processing badge in each Files-panel row.

| Badge | Colour | Meaning |
| --- | --- | --- |
| *(none)* | — | not indexed — normal for images, drawings, models, scans, duplicates |
| **Indexing…** | blue | the worker is embedding the text |
| **Searchable** | green | text is in the RAG index |
| **Indexing failed** | red | indexing ran and failed; hover shows the server's reason |

#### IX-01 · P0 · Indexing state appears
- **Steps:** upload F1 and watch the row without touching anything.
- **Expected:** after **Ready**, within a few seconds **Indexing…** (blue) may
  appear briefly, then **Searchable** (green). The two badges sit side by side.
  With a one-page file indexing can finish between two refreshes (every 4
  seconds), so seeing only **Searchable** is also a pass.
- **Failure indicators:** the row stays Ready with no badge for more than 2
  minutes while the worker log shows `rag.index_file … finished` → the panel did
  not refresh (reload to confirm; see IX-05).
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### IX-02 · P0 · Searchable persists after reload
- **Steps:** after IX-01, reload the page; log out and in again; return.
- **Expected:** the row still shows **Ready** + **Searchable** (server-reported).
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### IX-03 · P1 · No misleading badge on text-less files
- **Steps:** check the rows from FI-02 (XLSX, image, DXF), FI-03 (scan), FI-08
  (duplicate), FI-12 (IFC).
- **Expected:** none of them shows any index badge.
- **Failure indicators:** **Indexing failed** or **Indexing…** on any of them.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### IX-04 · P1 · Automatic refresh stops when settled
- **Steps:** with DevTools → Network filtered on `files`, open the QA project's
  Documents page when **all** rows are settled (no Queued/Processing/Indexing, and
  the last text file finished more than 2 minutes ago). Watch for 30 seconds.
- **Expected:** one list request on load, then **no** further requests.
  During an upload, requests repeat every ~4 seconds; they stop once everything
  has settled and the 2-minute indexing pickup window has passed.
- **Failure indicators:** requests every 4 seconds forever on a settled list.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### IX-05 · P1 · Extraction-to-indexing handover
- **Purpose:** processing settles first, indexing starts a moment later; the
  panel must keep refreshing across that gap.
- **Steps:** upload F4 (TXT) and watch the Network tab and the row.
- **Expected:** requests continue after **Ready** until the **Searchable** badge
  appears, then stop.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### IX-06 · P2 · Indexing failed state — needs controlled setup
- **Purpose:** red **Indexing failed** badge with the server's reason as tooltip.
- **Why controlled:** normal UI actions on a healthy stack cannot produce it.
  It needs a **separate development environment** whose embedding calls fail,
  for example one running with an invalid OpenAI key. Upload F1 there and
  watch the row. Do **not** change the shared environment's key for this test.
- **Expected (when set up):** **Ready** + **Indexing failed** (red); hovering
  shows a readable reason (e.g. the provider error); the file remains listed and
  downloadable; after restoring the key, the job is retried automatically and the
  badge becomes **Searchable**.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested` (expected: Blocked unless set up)

#### IX-07 · P2 · Server-side record of indexing (read-only)
- **Steps:** after IX-02, run:
  ```sql
  SELECT original_filename, status, index_status, indexed_at, index_error
  FROM ingested_files WHERE project_id = '<QA project id>' ORDER BY created_at;
  SELECT kind, status, attempts, created_at, started_at, finished_at, last_error
  FROM background_jobs WHERE project_id = '<QA project id>' ORDER BY created_at;
  ```
- **Expected:** text files `index_status = READY`; text-less files `NOT_INDEXED`;
  jobs `SUCCEEDED` with `attempts = 1`; the corrupt PDF's ingestion job
  `SUCCEEDED` (a bad file is recorded as Failed on the file, not retried).
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

### 4.7 Documents library and Document Assistant (DO)

Where: QA project → **Documents**; the upper card is the library. Upload with
**+ Upload Document** (dialog fields: file, **Title**, **Project \***,
**Document Type**, **Notes**).

#### DO-01 · P0 · Upload a PDF to the library — background indexing
- **Prerequisites:** F1 (or another small text PDF, ideally F9 with a known answer).
- **Steps:**
  1. **+ Upload Document** → choose the file, Title `QA retention clause`,
     type *Contract*; click **Upload**.
  2. Wait ~15 seconds, then click **Ask AI** on the new row.
- **Expected:**
  1. Toast "Document uploaded successfully."; the row appears.
  2. The assistant ("Ask about this document") shows **AI index: Ready** and
     "1 pages · N passages" — indexing happened in the background with no click.
- **Verify:** worker log shows `indexed document …` and
  `rag.index_document … finished`.
- **Note:** the assistant reads the status **once when opened** and does not
  refresh. If it says **Not indexed**, close it, wait, and reopen — that is
  expected behaviour, not a bug.
- **Failure indicators:** still **Not indexed** after a minute and a reopen,
  while the worker log shows no `rag.index_document` job.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### DO-02 · P1 · Non-PDF library upload
- **Prerequisites:** F6 (PNG) or F3 (DOCX).
- **Expected:** uploads normally; **no Ask AI** button on the row (Ask AI is
  shown only for PDFs); no indexing job in the worker log.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### DO-03 · P1 · Fake PDF refused
- **Prerequisites:** F11.
- **Expected:** an error toast (server: "File content does not match its
  extension"); no row.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### DO-04 · P1 · Manual Index / Re-index (synchronous)
- **Steps:** open **Ask AI** on the DO-01 document → click **Re-index**.
- **Expected:** button shows **Indexing…**, then toast
  "Indexed 1 pages into N passages." and the summary updates. This one runs inside
  the request (a few seconds) — unlike uploads, which index in the background.
- **Note:** costs one embedding call.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### DO-05 · P2 · Library size limit
- **Prerequisites:** a PDF over 25 MB (F17) — only if you have one.
- **Expected:** error toast "File exceeds the 25 MB limit"; no row.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### DO-06 · P0 · Ask a question answered by the document
- **Prerequisites:** F9 indexed (DO-01). F9 contains the sentence
  "Retention is five per cent of each interim payment."
- **Steps:** in the assistant, type `What is the retention percentage?`; click **Ask**.
- **Expected:** an answer stating five per cent, with a **Source** citation
  showing the page number. "Answers come only from this document."
- **Failure indicators:** an answer not grounded in the document; no citation.
- **Note:** costs embedding + answering calls.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### DO-07 · P1 · Ask an unrelated question
- **Steps:** ask `What is the capital of France?`.
- **Expected:** "Nothing in the indexed text answers this. Try rephrasing, or
  check that the right document is indexed." — the assistant does not answer
  from general knowledge.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### DO-08 · P1 · Ask before indexing
- **Steps:** upload a PDF with automatic indexing still running, or open Ask AI on
  a PDF whose status is **Not indexed** (e.g. one uploaded before this branch).
- **Expected:** the Ask field is disabled with "Index the document before asking
  a question."; **Index for AI** is available.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### DO-09 · P1 · Download and delete
- **Steps:** on a library row click **Download**; then **Delete** a test document.
- **Expected:** the original file downloads intact; delete removes the row.
- **Also:** as `projectowner@gmail.com`, confirm there is no Delete button.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### DO-10 · P2 · Search and type filter
- **Steps:** use **Search documents...** and the **All Types** filter.
- **Expected:** the list narrows correctly; clearing restores it.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

### 4.8 Other implemented modules (MO)

Run in the QA project as `managerr@gmail.com` unless stated. These pages were not
changed on this branch; the goal is a regression pass of their main workflow.

#### MO-01 · P1 · Tasks
- **Steps:** **Tasks** → **New Task**; name, dates, discipline; assign
  `civilcons@gmail.com` (the assignee list shows only members the server accepts);
  save. Open the task; change status/progress; add a comment.
- **Expected:** the task appears on the board; detail page shows the changes;
  the assignee gets a notification.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-02 · P1 · My tasks and review
- **Steps:** log in as `civilcons@gmail.com` → QA project → **My tasks** and
  **Pending reviews**.
- **Expected:** the MO-01 task is listed; review actions are available.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-03 · P1 · Issues
- **Steps:** **Issues** → **Raise an issue** / **Create issue**; title, category,
  severity; save. As managerr, resolve it (resolution note required).
- **Expected:** issue listed; resolve requires a note; status changes.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-04 · P1 · Design changes
- **Steps:** **Design changes** → **Propose design change** → **Submit change**.
  Log in as `civilcons@gmail.com` and approve or reject it.
- **Expected:** proposal listed; approve/reject buttons only for the reviewer.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-05 · P1 · Site reports
- **Steps:** **Site reports** → **Create site report** → fill, attach a photo →
  **Submit report**. As managerr, verify it.
- **Expected:** report listed; verification changes its review status.
- **Note:** submitting requires site responsibility on the project or seeing all
  project work; a member without it may not see the form — expected.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-06 · P2 · Schedule / Gantt and milestones
- **Steps:** **Schedule / Gantt**; then **+ Add Milestone** on the milestones page.
- **Expected:** tasks with dates render on the Gantt; milestone saved.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-07 · P1 · Collaboration: client requests and site visits
- **Steps:** as `projectowner@gmail.com` → **Client requests** → **New request**.
  As managerr, open it and **Send response**. Then **Site visits** → schedule one.
- **Expected:** request visible to both; response recorded; visit appears in
  **My schedule**.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-08 · P1 · Messages
- **Steps:** **Messages** → **New Conversation**; choose a recipient; send. As
  managerr, also try a project/team announcement (needs `message.broadcast`).
- **Expected:** conversation appears for both; announcement option only for
  holders of message.broadcast (admin/PM).
- **Note:** triggers notifications and possibly push.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-09 · P1 · Notifications
- **Steps:** after MO-01/MO-08, open **Notifications**; click one.
- **Expected:** it opens the related page (task, message, document).
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-10 · P1 · IFC workspace
- **Prerequisites:** F7 (`minimal_ifc4.ifc`); for comparison also
  `multi_discipline_ifc4.ifc`.
- **Steps:** **IFC / BIM** → **New Model Group** → **Create group** →
  **Upload IFC** (F7). Wait for processing.
- **Expected:** the version moves through processing states to Ready (the worker
  log shows `ifc.process_version … finished`); the spatial tree/elements appear.
  There is **no 3D viewer** (removed 2026-10-17, see QA-03); element links open
  the Elements tab.
- **Failure indicators:** stuck in a processing state while the worker is up.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-11 · P2 · AI insights and Agents
- **Prerequisites:** an account holding `agents.view` (Office Administrator by
  default; anyone else only by explicit grant — see QA-07).
- **Steps:** **Agents** → **Run all**; then **AI insights**.
- **Expected:** a run summary ("finished"); findings, if any, appear in AI insights
  with Create issue / Create task actions for authorized users. Agents are
  rule-based; automatic (event-triggered) analysis is off on this stack.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-12 · P2 · Project information (evidence archive)
- **Steps:** **Project information** → browse; as managerr add a project photo
  category.
- **Expected:** list paginates; category added (requires project.manage_members).
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-13 · P2 · Voice assistant (costs money)
- **Prerequisites:** a microphone; accept the cost of transcription.
- **Steps:** **Voice Assistant** → record a short request, e.g. "What tasks are
  overdue?".
- **Expected:** a transcribed request and an answer, or a clarifying question.
  Any action is proposed for confirmation, never executed silently.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-14 · P1 · People & access (admin)
- **Steps:** as admin → **People & access** → add a user: full name, email
  (e.g. `qa.engineer.20261009@example.com`), password, **Office role** (e.g.
  Engineer), status Active; save. Search for them. Deactivate them afterwards.
- **Expected:** created; the office role is required (saving without one shows
  "Choose an office role for the new account."); the new user must change their
  password at first login (AU-06).
- **Note:** creates a persistent account.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-15 · P2 · Roles & disciplines and Permissions (admin)
- **Steps:** open **Roles & disciplines** and inspect a role's permissions (do
  not save changes to shared roles). Open **Permissions**: the **Roles** tab shows
  a link to Roles & disciplines; the **People** tab shows a person's effective
  permissions.
- **Expected:** both pages load; the person summary shows their office role name.
- **Caution:** editing a shared role changes access for everyone holding it.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### MO-16 · P2 · Profile and MCP clients
- **Steps:** **Settings** → edit profile fields; open
  `http://localhost:5173/settings/mcp-clients` → **New token** (optional).
- **Expected:** profile saves; MCP page lists tokens (MCP is enabled). A created
  token's secret is shown once.
- **Note:** a created token is a live credential — revoke it after the test.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

### 4.9 Regression and reliability (RE)

#### RE-01 · P0 · Uploads while the worker is stopped
- **Purpose:** distinguish "worker down" from an application bug; prove durability.
- **Steps:**
  1. `docker compose stop worker`
  2. Upload F4 in the Files panel.
  3. Observe for 1 minute.
  4. `docker compose start worker`
- **Expected:** upload accepted; the row stays **Queued** while the worker is
  stopped (not Failed, not lost). Within seconds of starting the worker it becomes
  **Ready**, then **Searchable**. The job was kept in the database.
- **Failure indicators:** the upload is refused; the row disappears; it stays
  Queued after the worker is back for more than a minute.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### RE-02 · P1 · Library upload while the worker is stopped
- **Steps:** as RE-01, but upload a PDF to the library; open Ask AI before and
  after restarting the worker.
- **Expected:** upload succeeds immediately; **Not indexed** while stopped;
  **Ready** after the worker is back (reopen the assistant).
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### RE-03 · P1 · API restart during use
- **Steps:** logged in, run `docker compose restart backend`, wait for
  `/health` to answer, then click around.
- **Expected:** brief errors during the restart at most; afterwards the session
  still works (or refreshes) without a manual login.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### RE-04 · P1 · Network loss in the browser
- **Steps:** DevTools → Network → set **Offline**; try an upload and a page
  change; set back to **No throttling**.
- **Expected:** a readable error toast (e.g. "The file could not be uploaded."),
  no crash; after reconnecting, actions work again.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### RE-05 · P1 · Retry does not create duplicates
- **Steps:** after FI-09, click **Retry** twice quickly.
- **Expected:** at most one processing run (status changes once); the IX-07 query
  shows no duplicate active jobs for the file.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### RE-06 · P1 · Expected rejections are not bugs
- A quick reference for judging results:

  | You see | It is |
  | --- | --- |
  | 415 / "Unsupported file type" for `.csv`, `.exe`, `.md` | **expected** |
  | 415 / "content does not match" for a renamed file | **expected** |
  | "Partially processed" for XLSX, DWG, DXF, IFC (Files panel), scanned PDF | **expected** |
  | No index badge on images, drawings, models, scans, duplicates | **expected** |
  | Corrupt PDF → Failed, Retry → Failed again | **expected** |
  | Document Assistant still "Not indexed" until reopened | **expected** (it does not refresh) |
  | Redirect to `/dashboard` from a page you lack permission for | **expected** |
  | Row stuck in Queued with the worker running | **bug** — capture worker log |
  | "Indexing failed" on a normal text PDF with the API key working | **bug** |
  | Bounced back to login after a correct password | **bug** (or stale frontend — §3 step 4) |
  | Another project's file or document visible | **security bug — report immediately** |

---

## 5. Test data checklist

Prepare these in a folder such as `C:\QA-files\`. Keep text files to one or two
pages. Never upload real client documents.

| ID | File | How to make it | Used in |
| --- | --- | --- | --- |
| F1 | `qa-spec.pdf` — 1-page text PDF | Word/LibreOffice: type a paragraph → *Save as PDF* | FI-01, FI-08, IX-01 |
| F2 | `qa-scan.pdf` — image-only PDF | take a screenshot of text → print/save the **image** to PDF (no text layer) | FI-03 |
| F3 | `qa-method.docx` — text DOCX | Word: a few sentences | FI-02, FI-10, FI-13 |
| F4 | `qa-notes.txt` — UTF-8 text | Notepad: a few lines | FI-02, IX-05, RE-01 |
| F5 | `qa-boq.xlsx` | Excel: a small sheet | FI-02 |
| F6 | `qa-photo.png` (or `.jpg`) | any small screenshot | FI-02, DO-02 |
| F7 | `minimal_ifc4.ifc` | **in the repo**: `backend/tests/fixtures/minimal_ifc4.ifc` (others in the same folder) | FI-12, MO-10 |
| F8 | `qa-drawing.dxf` (optional) | export from a CAD tool; skip if you have none | FI-02 |
| F9 | `qa-retention.pdf` | text PDF containing exactly: "Retention is five per cent of each interim payment." | DO-01, DO-06 |
| F10 | `qa-data.csv` | Notepad → save as `.csv` | FI-04 |
| F11 | `fake.pdf` | copy F4 and rename it to `fake.pdf` | FI-05, DO-03 |
| F12 | `empty.txt` | an empty Notepad file saved as-is (0 bytes) | FI-06 |
| F13 | `qa-corrupt.pdf` | copy F1, open the copy in Notepad, delete everything after the first line (keep `%PDF-…`), save | FI-09, RE-05 |
| F14 | `qa-package.zip` | Windows: select F1 + F3 → *Send to → Compressed (zipped) folder* | FI-10 |
| F15 | `qa-broken.zip` | copy F14; open the copy in a hex editor (or truncate with a tool) to remove the last part of the file. Skip if you cannot do this safely | FI-11 |
| F16 | `qa-nested.zip` | zip F14 together with F4 | FI-11 |
| F17 | a PDF over 25 MB (optional) | only if you already have one | DO-05 |

Do not create or upload executables, password-protected or encrypted archives,
"zip bombs", or very large files made only to stress the system.

---

## 6. Execution order

1. **Environment** — §3 steps 1–12. Stop here if any step fails.
2. **Smoke (P0)** — SM-01, SM-02, SM-03.
3. **Authentication (P0)** — AU-01, AU-03, AU-04.
4. **Project setup** — PR-01, PR-02 (create the QA project), PR-03, PR-04.
5. **Permissions (P0)** — PE-01, PE-02, PE-03, PE-04.
6. **Files panel core (P0)** — FI-01, IX-01, IX-02, FI-04, FI-05.
7. **Library and assistant core (P0)** — DO-01, DO-06.
8. **Worker durability (P0)** — RE-01.
9. **Files panel breadth (P1)** — FI-02, FI-03, FI-06, FI-08, FI-09, FI-10, FI-12, FI-13; IX-03, IX-04, IX-05, IX-07.
10. **Library breadth (P1)** — DO-02, DO-03, DO-04, DO-07, DO-08, DO-09; PE-05, PE-06.
11. **Other modules (P1)** — MO-01 … MO-05, MO-07 … MO-10, MO-14.
12. **Reliability (P1)** — RE-02 … RE-05; AU-05, AU-06.
13. **Remaining P2** — SM-04, SM-05, AU-07, AU-08, PR-05, FI-07, FI-11, FI-14, IX-06, DO-05, DO-10, MO-06, MO-11, MO-12, MO-13, MO-15, MO-16.

---

## 7. Defect report template

```markdown
### DEF-<number>: <one-line summary>

- **Test case:** <ID, e.g. FI-09>
- **Date / time:** <when it happened — needed to find log lines>
- **Account:** <email and role>
- **Project:** <name and id from the URL>
- **Page / URL:** <full URL>
- **Build:** branch <feat/ingestion-reliability>, images created <from §3 step 4>

**Steps to reproduce**
1. …
2. …

**Expected**
<from the test case>

**Actual**
<what happened — exact error text>

**Evidence**
- Screenshot: <file>
- Browser console errors: <paste>
- Network: <failing request URL, status code, response body>
- Worker log: <`docker compose logs --since 10m worker`>
- Backend log: <`docker compose logs --since 10m backend`>
- Read-only DB check (if used): <query and result>

**Severity:** Blocker / Major / Minor / Cosmetic
**Reproducible:** Always / Sometimes / Once
```

---

## 8. Coverage and limitations

**Verifiable through the UI alone:** login and landing, navigation, permission
visibility, project creation and switching, every Files-panel upload outcome,
the index badge states **Indexing… / Searchable**, polling behaviour (with the
Network tab), library upload, Ask AI, manual re-index, downloads, and the main
workflow of each module in §4.8.

**Needs a read-only backend check to be certain:** that a job ran on the worker
rather than the API (worker log); job attempts and retries (IX-07 query); that a
duplicate or text-less file was *deliberately* not indexed (`index_status`);
cross-project isolation at the API level (Network status codes).

**Cannot be tested here without extra setup:**

| Area | Why | What it would take |
| --- | --- | --- |
| Password reset end-to-end | no SMTP; the reset token is stored only as a hash | configure SMTP in a dev environment |
| Indexing failed badge (IX-06) | needs the embedding provider to fail | a separate dev stack with an invalid key |
| Worker crash mid-job and automatic recovery | killing a worker mid-parse safely needs timing control | covered by automated tests (`test_job_runner.py`, `test_ingestion_reliability.py`) |
| Ingestion "Processing did not complete" (run broke) | needs a database fault during processing | covered by automated tests |
| Files over 200 MB / 500 MB | impractical and resource-heavy | skip |
| Push notifications on a phone | needs a registered device | a phone signed in to the mobile app |
| Mobile app | out of scope of this web plan | — |
| Demo-seed scenarios | the demo seed is not loaded (`ENABLE_DEMO_SEED` requires `ENVIRONMENT=staging`) | a staging database |

**Known data observations (not test failures):** in *Residential Complex C*,
`elec@gmail.com` and `civilcont@gmail.com` are external contractors holding the
internal `site_engineer` project role — current rules would refuse that
combination for new assignments, so it is legacy data. *Riverside Tower* has the
same account as owner and project manager. Several leftover rows from automated
test runs exist (accounts/projects with random suffixes).

**Known limitations in the current implementation (expected behaviour):**
- The Document Assistant does not refresh its index status while open.
- The manual library re-index runs synchronously inside the request.
- Existing files and documents uploaded before automatic indexing are not
  back-filled; index them with the assistant's **Index for AI**.
- The Files panel has no download button.
- If every processing attempt crashes the worker outright, a file can remain in
  Processing and the Retry button is not offered for that state.

---

## 9. QA pass 2026-10-17 — defect register and retest cases

Defects reported during manual QA on 2026-10-17, with the cause found in the
code or the live data, the change, and the automated test that now pins it.
**Verification result** is the automated result on this branch. Every
browser retest below is **Not tested** until the images are rebuilt (§9.3):
the running containers were built 2026-10-14 and contain none of these fixes.

Backend test file for this pass: `backend/tests/test_qa_pass_2026_10_17.py`.

### 9.1 Defect register

| ID | Title | Original behaviour | Root cause | Files changed | Test | Verification result | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QA-01 | Milestones card on the manager dashboard | The dashboard's Milestones decision card went to the portfolio list, not to milestones | The card linked to a fixed `/projects` path; milestones exist only inside a project | `frontend/src/utils/projectRoutes.ts` (`portfolioMilestonesPath`), `features/dashboard/project-manager/pages/ProjectManagerDashboard.tsx` | `utils/projectRoutes.test.ts` (3 new cases) | PASS (automated) | With several projects it opens the first project's milestones; there is no cross-project milestone page (not added: no new features in this pass) |
| QA-02 | Task status filter shows every task | Choosing a status on a project's task board still listed all tasks | `GET /projects/{id}/tasks` accepted no filter parameters and silently ignored them; the page could also show a slower, older response over a newer one | `backend/app/api/tasks.py` (`_apply_task_filters`, shared by both list endpoints), `frontend/src/features/tasks/pages/TasksPage.tsx` (latest-request guard) | `test_qa_pass_2026_10_17.py` filter cases; `TasksPage.test.tsx` | PASS (automated) | — |
| QA-03 | Remove the website 3D viewer | A 3D viewer tab (three.js) shipped with the IFC workspace | Product decision: the viewer is withdrawn; IFC upload, metadata and analysis stay | Deleted `features/ifc/components/IFCViewer.tsx`; edited `IFCWorkspacePage.tsx`, `IFCInformationTabs.tsx`, `IFCElementsTab.tsx`, `IFCActionTabs.tsx`, `AIIntelligencePage.tsx`, `services/api.ts`, `services/endpoints.ts`; removed `three` and `@types/three`; backend `api/ifc.py` (geometry asset/mapping routes removed), `services/ifc_geometry_service.py` (tessellation runs in a temporary directory, no stored asset) | `test_ifc_authorization.py`, `test_ifc_downloads_and_limits.py`, `test_ifc_interference_pipeline.py`; Findings tab tests | PASS (automated) | Geometry assets already in storage are left in place (no file deletion in this pass); interference analysis still tessellates on the worker |
| QA-04 | Mixed Arabic-English speech | Mixed speech came back with English terms translated and identifiers altered; replies followed the interface language | The interpretation prompt normalised the transcript into one language; the browser live preview (single-locale) was shown in place of the server transcript | `backend/app/ai/construction_analysis_service.py` (MIXED LANGUAGE section, prompt v10), `frontend/src/features/voice/components/VoiceAssistantPanel.tsx` (preview only while recording) | `test_qa_pass_2026_10_17.py` reply-language, no-language-hint and prompt cases; panel test "hides the browser's live preview" | PASS (automated, mocked provider) | Transcription quality itself depends on the provider; verified only with recorded transcripts, not live audio |
| QA-05 | Standalone issue update needs a task | Updating an issue by voice asked "which task?" and offered "Choose another task"; the resolution-note question had no input | The panel only knew task-selection questions; `update_draft` treated every target as a task | `backend/app/services/voice_command_service.py` (issue-aware `update_draft`), `VoiceAssistantPanel.tsx`, new `ClarificationAnswer.tsx` | `test_qa_pass_2026_10_17.py` issue-draft cases; panel tests "answers an issue's text question…", "offers 'choose another task' only…" | PASS (automated) | — |
| QA-06A | Repeated email codes for permission changes | Every permission toggle asked for a new email code | The step-up grant for `admin.change_permissions` was single-use | `backend/app/services/step_up_service.py` (`session_scoped` purposes; the grant stays valid for `STEP_UP_VALIDITY_MINUTES`, default 10) | `test_step_up_security.py` (4 new cases: one code covers a run, window expires, authorizes nothing else, destructive purposes stay single-use) | PASS (automated) | Window length is the existing setting; email verification is not weakened elsewhere |
| QA-06B | System administration grants project access | An Office Administrator could open the tasks, documents, models and reports of every project | `platform.view_all_projects` bypassed project membership for everything, and `org_admin` holds every execution permission | `backend/app/core/permission_catalogue.py` (`platform.work_in_all_projects`, `registry` flag), `core/role_templates.py` (leadership templates), `core/deps.py` (`user_can_see_project_record`; work gate uses the new code), `services/authorization.py` (registry codes, per-project `effective_permissions`), `api/projects.py`, `api/organization.py`, `api/dashboard.py`, migration `i6f3a9c4d170`; frontend `app/store/permission.store.ts`, `hooks/usePermissions.ts`, `ProjectWorkspaceContext.tsx`, `app/router/PermissionGuard.tsx`, `utils/projectRoutes.ts`, i18n | `test_qa_pass_2026_10_17.py` (5 cases), `test_platform_view_all_projects.py`, `test_cost_validation_access.py`, `test_rbac_schedule_and_ai_insights.py`, pinned RBAC sets; `permission.store.test.ts`, `PermissionGuard.test.tsx`, `projectRoutes.test.ts` | PASS (automated) | The administrator still lists, edits and staffs every project and reads the audit log; joining a project's team gives them its work. General Manager and Technical Director are unchanged |
| QA-07 | Agents page open to everyone with tasks | Engineers saw Agents in the menu and could run agents | The page, route and API followed `task.view` | `backend/app/core/permission_catalogue.py` (`agents.view`), `core/role_templates.py` (org_admin), `api/agents.py` (all 6 routes), migration `h5e2f8b3c069`; frontend `navigation.ts`, `router/index.tsx`, `projectRoutes.ts` | `test_qa_pass_2026_10_17.py` agents cases; pinned sets in `test_role_templates.py` and `test_rbac_security_regression.py` (delegable office work); `navigation.test.ts`; `AgentsPage.test.tsx` | PASS (automated) | Migration grants it only to the seeded Office Administrator role; anyone else needs an explicit grant |
| QA-08 | Task progress consistency | Progress offered on To Do work then refused; repeated clicks sent repeated saves; a committed save reported as failed when the refresh failed; a voice batch applied later steps after an earlier step on the same task was refused | No in-flight guard; outcome taken from the reload, not the change; status gate not mirrored in the UI; the rules engine did not track failed targets | `features/tasks/pages/TaskDetailPage.tsx`, `EngineerTaskDetailPage.tsx`; `backend/app/services/voice_rules_engine.py`, `voice_action_service.py` (dependent steps SKIPPED) | `TaskDetailPage.test.tsx` (3 cases); `test_qa_pass_2026_10_17.py` dependent-skip case; existing `test_task_update_reliability.py` | PASS (automated) | Managers are still not granted engineer progress (by design) |
| QA-09 | Voice stops responding | After recording, the panel sometimes showed nothing and no console error | A provider failure is stored and returned as a `FAILED` command with HTTP 201; the panel treated it as success and dropped the retry. Provider retries (2) × 60 s could outlast the browser deadline | `VoiceAssistantPanel.tsx` (FAILED handling, Cancel while processing), `services/api.ts` (300 s upload timeout), `transcription_service.py` / `construction_analysis_service.py` (`max_retries=1`) | panel test "treats a FAILED command as a failure…" | PASS (automated) | The six 2026-10-17 failures were provider-side (AIProviderError, 18:29–18:33 UTC); they cannot be reproduced on demand |
| QA-10 | Errors without a trail | A support ID was shown but no log line carried it | Failures were stored without being logged | `backend/app/api/ai.py`, `app/api/voice.py` (log support ID, class, provider message — never audio, transcript or keys) | covered by QA-09 panel test; log content by review | PASS (automated) / log format NOT TESTED in a browser | — |

### 9.2 Retest cases

Run after the rebuild in §9.3. Accounts as in §3.

#### QA-R01 · P1 · Milestones from the manager dashboard
- **Steps:** as the project manager, open the dashboard → **Milestones** card.
- **Expected:** lands on `/projects/<first project>/milestones`; with no project, on `/projects`.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### QA-R02 · P0 · Task filtering
- **Steps:** project **Tasks** → choose each status in turn; then a status with
  no tasks; then **All statuses**; combine status with priority and a search word;
  switch filters quickly.
- **Expected:** only matching tasks each time; empty board for an empty status;
  the full list after clearing; the board always matches the filter last chosen.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### QA-R03 · P1 · Mixed-language voice (costs money)
- **Steps:** with the interface in English, say "حلينا مشكلة في الـ structure
  elements في TSK-001"; repeat with the interface in Arabic.
- **Expected:** the transcript keeps "structure elements" and "TSK-001" as
  spoken; the reply is in Arabic both times; the grey live preview disappears
  when recording stops.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### QA-R04 · P1 · Standalone issue by voice (costs money)
- **Steps:** as a user allowed to update issues, say "issue ISS-… is resolved".
- **Expected:** no "Which task?" question and no "Choose another task"; if a
  resolution note is asked for, a text box accepts it; confirming resolves the issue.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### QA-R05 · P1 · Permission changes need one code per window
- **Steps:** as administrator, **Permissions** → change one permission → enter
  the email code → change three more within 10 minutes → wait past 10 minutes and change one more.
- **Expected:** one code for the first four changes; a new code after the window;
  deactivating a user still asks for its own code.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### QA-R06 · P0 · Agents visibility
- **Steps:** as an engineer and as the project manager, look for **Agents** and
  open `/projects/<id>/agents` directly; as administrator, grant `agents.view` to
  the manager, reload, then revoke it.
- **Expected:** hidden and redirected without the grant (API answers 403);
  visible and working with it; gone again after revoking.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### QA-R06B · P0 · Administrator reach
- **Steps:** as the Office Administrator, open **Projects** and choose a project
  you are not on; try `/projects/<id>/tasks` and `/projects/<id>/documents`
  directly; then add yourself to its team and reload.
- **Expected:** the project is listed and opens on its **Team** page; the menu
  offers Team and Parties only; task and document URLs return to the Team page
  (the API answers 403); after joining, the full project opens. As General
  Manager, every project opens fully without joining.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### QA-R07 · P0 · Progress consistency
- **Steps:** as the assigned engineer open a **To Do** task; then start it, enter
  40 %, click **Save progress** several times quickly; turn the network off after
  the click returns (DevTools → Offline) and save again.
- **Expected:** no progress box before **Start task**; one save per click burst
  (Network tab shows one PUT); a committed save says "Saved" even if the refresh fails.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### QA-R08 · P1 · Voice failure and recovery
- **Steps:** stop the network mid-processing, or set an invalid provider key on a
  dev stack; record a command; then **Cancel** during processing.
- **Expected:** an error with a support ID and **Retry send** (same recording);
  the backend log has a `voice processing failed support_id=…` line with that ID
  and no transcript; Cancel always returns to idle.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

#### QA-R09 · P0 · IFC after the viewer removal
- **Steps:** run MO-10; open a finding's elements from **AI Intelligence**.
- **Expected:** upload, processing, spatial tree, elements and findings work;
  no 3D tab or **View 3D** button anywhere; element links open the Elements tab.
- **Result:** `[ ] Pass  [ ] Fail  [ ] Blocked  [ ] Not tested`

### 9.3 Before retesting

The database is already at migration `i6f3a9c4d170`; the code must match it:

```bash
docker compose build backend worker frontend
docker compose up -d backend worker frontend
```

No data is reset by this; uploaded files and accounts are untouched.

The rebuild was done on 2026-10-21 (images built 13:14 UTC, containers started
14:01 UTC); §9.4 records the verification that followed.

### 9.4 Post-rebuild verification — 2026-10-21

**Environment.** Branch `feat/ingestion-reliability`, uncommitted work intact
(183 status entries, identical before and after). Backend, worker and frontend
run the rebuilt images and contain this pass's code (checked inside each
container). `GET /health` → 200. Alembic current = head = `i6f3a9c4d170`; no
pending migration. No errors in backend or worker startup logs.

**Where the tests ran.** Not on the development database. The suite's
fixtures write and delete their own rows, so the run used
`structiq_qa_20261021`, a copy restored from a read-only `pg_dump` of
`construction_platform`, dropped afterwards. Uploads go to throwaway tmpfs
mounts.

| Check | Command | Result |
| --- | --- | --- |
| Focused backend (RBAC, staffing, view-all vs work-in-all, agents, milestones, site reports, step-up, templates, catalogue) | `pytest` on 17 files | **258 passed**, exit 0 |
| Focused frontend (guard redirect, project-scoped permissions, landing fallback, navigation, agents, tasks, voice) | `vitest run` on 9 files | **90 passed**, exit 0 |
| Full backend | `pytest tests` | **2694 passed, 1 skipped**, exit 0 — the skip is the opt-in segfaulting IfcOpenShell worker test |
| Full frontend | `vitest run` | **273 passed, 1 failed**, exit 1 — see below; after the i18n decision **275 passed**, exit 0 |
| Typecheck | `tsc -b` | exit 0, no output |
| Production build | `npm run build` | exit 0 |
| Lint | `eslint .` | exit 1, **179 problems, all pre-existing** (baseline 185; no file/rule pair increased) |

**The one frontend failure** — `src/i18n/i18n.test.ts › keeps interpolation
placeholders identical in both languages`, on
`pmDashboard.decisions.milestonesOpen_one` (and `_two`). Not a regression in
behaviour: rendered through i18next with the real catalogue, Arabic gives
"لا توجد مراحل مفتوحة" (0), "مرحلة واحدة ما زالت مفتوحة" (1),
"مرحلتان ما زالتا مفتوحتين" (2), "3 مراحل ما زالت مفتوحة" (3),
"11 مرحلة ما زالت مفتوحة" (11). The component passes `count` itself, so no
form needs `{{count}}` to render; Arabic singular and dual express the number
through the noun, and adding it would read "1 مرحلة واحدة". The test requires
each English form's placeholders in the same Arabic form, which Arabic grammar
does not support for zero/one/two. The Arabic wording is pre-existing
uncommitted work and was not changed. **Resolved (option 1, chosen
2026-10-21):** the test now lets `{{count}}` be omitted only in Arabic
`_zero/_one/_two` forms, still compares every other placeholder, and a new
assertion requires `{{count}}` in every Arabic `_few/_many/_other` form whose
English text has it. Checked by breaking the catalogue on purpose (a stray
placeholder in `_one`, `{{count}}` removed from `_few`): both were caught.

**Data preservation.** Users, projects, tasks and project memberships are
identical by row fingerprint; all 21 uploaded files identical by checksum; all
7 Docker volumes present. Across all 83 tables the only differences came from
live use of the running app during the window, not from the tests: one
step-up request at 14:24:20 UTC (one row each in `audit_logs`,
`notifications`, `otp_challenges`, `rate_limit_hits`), and 15 expired
`revoked_tokens` pruned by routine cleanup.

**Known, not caused by this work.** `alembic check` reports model/database
drift (a legacy `contractor_profiles` table and index-name differences). No
model file has changed since commit `fe489dc`; worth a separate cleanup.

### 9.5 Browser checklist — outstanding

Nothing below has been run in a browser. Accounts as in §3; use the QA project.

| # | Check | Steps and expected result | Result |
| --- | --- | --- | --- |
| B1 | Administrator login and project list | Log in as the Office Administrator → **Projects** lists every project, including ones they have not joined | NOT TESTED |
| B2 | Team and Parties on a project not joined | Open such a project → it lands on **Team**; menu shows Team and Parties only; members and parties load; adding a member works | NOT TESTED |
| B3 | Execution modules refused until joined | Type `/projects/<id>/tasks`, `/documents`, `/ifc`, `/issues`, `/site-reports`, `/schedule`, `/agents` → each returns to Team; DevTools shows 403 for the API calls, no blank page | NOT TESTED |
| B4 | Joining changes access | Add the administrator to the team, reload → the full project menu appears; Tasks and Documents open. Remove them → refused again | NOT TESTED |
| B5 | General Manager and Technical Director | Log in as each → every project opens fully without joining; no Team-only view | NOT TESTED |
| B6 | Agents permission | Engineer and PM: no **Agents** entry, URL redirects, API 403. Grant `agents.view` to the PM → visible and runs; revoke → gone | NOT TESTED |
| B7 | Milestones navigation and task filters | PM dashboard **Milestones** card → project milestones. **Tasks**: each status shows only its tasks; empty status empty; **All statuses** restores; rapid switching shows the last choice | NOT TESTED |
| B8 | Mixed-language voice and failure/retry (costs money) | Say "حلينا مشكلة في الـ structure elements في TSK-001" → transcript keeps English terms and TSK-001; reply in Arabic in both UI languages; preview disappears when recording stops. Go offline mid-processing → error with support ID and **Retry send**; **Cancel** returns to idle | NOT TESTED |
| B9 | Task progress persistence and notifications | Assigned engineer: To Do shows **Start task**, not a progress box; after starting, save 40 % with several quick clicks → one PUT, one "Saved", one notification to the manager; reload keeps 40 % | NOT TESTED |
| B10 | IFC without the 3D viewer | Upload `minimal_ifc4.ifc` → processes to Ready; spatial tree, elements and findings work; no 3D tab or **View 3D** button; finding element links open Elements | NOT TESTED |

Record each as PASS, FAIL or BLOCKED with evidence (screenshot or Network
entry). StructIQ is not QA-ready until B1–B10 are recorded.

### 9.6 Browser QA findings — 2026-10-22

Reported from the first browser pass over §9.5. Each was traced to its cause in
code, the live request log or the database before anything was changed. **How
it was verified:** in a separate reproduction stack — a copy of the development
database (`pg_dump`), a second backend on port 8001 running the working tree,
and the frontend dev server pointed only at it; test passwords were set on four
accounts *in the copy only*. "Observed" below means executed in that browser
and seen. Your own stack still needs the rebuild in §9.3 before §9.5 is rerun.

| ID | Symptom | Root cause | Fix | Observed in reproduction |
| --- | --- | --- | --- | --- |
| QB-A | Administrator opens a project and is returned to the dashboard | "Open" goes to `/projects/:id`; the guard's project pattern required a trailing slash, so a refusal fell back to `/dashboard` → `/admin`. The guard also rendered the page on the office-wide answer before the project's arrived, so the overview fired 403s first | Guard matches `/projects/:id` and waits for the open project's permissions, even on a fresh page load; "Open" uses the project's `canOpenWork` | Admin "Open" → Team page; `/tasks`, `/documents`, `/ifc`, `/issues` by URL → Team, **zero** 403 requests |
| QB-B | Coordination, Messages, Project documents, Executive overview offered to the administrator | Menu entries checked office-wide codes only; the administrator works in no project, so each page was empty (`200 []`) or refused | Projects carry `canOpenWork`; portfolio work entries and routes require at least one workable project (`WorkScopeGuard` explains otherwise) | Menu shows Dashboard, Projects and administration only; `/messages`, `/owner-dashboard` show "You are not on any project team" |
| QB-C | Project Tasks shows empty columns to the administrator | `TasksPage` turned any failed load, including 403, into an empty list | Separate access-denied and error states (with retry) | Covered by `TasksPage.test.tsx`; administrator never reaches the page now (QB-A) |
| QB-D | Engineer's Project Overview: "Open your own work for assigned-task metrics" | Overview endpoint requires `task.view_all`; menu, route and landing offered it on `task.view` | Overview requires `task.view_all`; landing is overview → my work → team → parties | Engineer "Open" → My tasks; overview URL → My tasks, no 403s |
| QB-E | Engineer sees the team beside a permission error | "View Members" fell back to `project.members` after the 403; project list and detail embedded the full team for anyone with access | Payload `members` only for `project.manage_members`; no fallback; button and overview team card shown only to staffers | Engineer list payload `members: []`; no "View Members"; manager still sees the team |
| QB-F | Administrator cannot send a message or announcement | Messaging is project-scoped (no global announcements). Recipient 403s were swallowed into empty lists. The announcement group showed "All project members" but stored `""`, so Send never enabled — for authorised users too | Group defaults with the announcement; the refused project is explained; Send states what is missing | After joining the team, announcement sent with Send enabled; refused project shows the explanation |
| QB-G | Executive overview: "You don't have permission to open this client portal" | Entry shown to internal administrators; the client portal is project work since QA-06B | Entry and page require a workable project; the page lists only those, and one failure no longer blanks all | Entry hidden for the administrator; direct URL explains |
| QB-H | Engineer granted Create Project cannot find it | Editing the Engineer template made an office copy holding the grant with **zero holders**; all engineers still pointed at the template | Permission resolution uses the office's copy of a replaced template (as the role list already does); the copy's member count includes them; create-only users are not sent to the PM dashboard | Engineer sees **Add Project**; `platform.create_project` in their permissions |
| QB-I | Verification code on every permission change | By design: one code covers permission changes for 10 minutes. The existing echo switch had no production guard and the dialog ignored it | `ENVIRONMENT`; boot refused with `OTP_DEV_ECHO_ENABLED` outside development/local/test; dialog fills in and labels an echoed code | Tests only (`test_qa_pass_2026_10_22.py`, `StepUpDialog.test.tsx`) |
| QB-J | Engineer's supervision area loads forever | Review dashboard opened from the portfolio has no project and returned early without clearing `loading` | Every path settles; stale responses ignored; link to Projects | Engineer dashboard shows "Select an assigned project…" with a Projects button |

**Policy decisions taken, from the existing rules rather than new ones:** the
client portal and project messaging are project work (QA-06B), so the office
administrator reaches them by joining a project's team. System-wide
announcements do not exist: conversations require a project
(`conversations.project_id` is not nullable). The minimum safe addition would be
a separate office-announcement model (no project, recipients = active office
members), gated by its own permission and delivered through notifications —
a new feature with a migration, not done in this pass.

**Data note.** Fixing QB-H makes an existing decision take effect: on
2026-10-22 at 10:19 UTC the administrator granted `platform.create_project` to
the Engineer role. Once the rebuilt backend runs, all four engineers can create
projects. Revoke it under Roles if that was only a test.

**Automated results after these fixes** (isolated database copy):
backend **2709 passed, 1 skipped** (opt-in crash test); frontend **297 passed**;
typecheck and production build pass; lint 179 problems, all pre-existing
(baseline 185, no file/rule pair increased). No migration.

#### Retest scenarios (your stack, after the rebuild)

| # | Scenario | Expected | Result |
| --- | --- | --- | --- |
| R1 | Admin → Projects → Open a project not joined | Team page; menu Team and Parties only | NOT TESTED |
| R2 | Admin types `/projects/<id>/tasks`, `/documents`, `/ifc`, `/issues` | Back to Team; DevTools shows no 403 | NOT TESTED |
| R3 | Admin portfolio menu; open `/messages`, `/owner-dashboard` | No work entries; pages explain "not on any project team" | NOT TESTED |
| R4 | Admin joins the team, reloads, opens Messages → New conversation → Project announcement | Full menu; "All project members" preselected; Send enables with text; sends | NOT TESTED |
| R5 | Engineer opens the project; tries `/projects/<id>/dashboard` | Lands on My tasks; no overview entry; no 403 | NOT TESTED |
| R6 | Engineer on Projects | No "View Members"; project payload has no team (Network tab) | NOT TESTED |
| R7 | Engineer dashboard | Settles; no endless "Loading supervision workspace" | NOT TESTED |
| R8 | Engineer with the Engineer-role grant | "Add Project" visible and creating a project works; revoke the grant → button gone | NOT TESTED |
| R9 | Local QA with `ENVIRONMENT=development` and `OTP_DEV_ECHO_ENABLED=true` | Permission change dialog shows and fills the code; with `ENVIRONMENT=production` the backend refuses to start | NOT TESTED |
| R10 | Project manager → Messages → Project announcement | Send enables with text; announcement delivered | NOT TESTED |

### 9.7 Permission customization — 2026-10-23

What changed (details in [RBAC.md](RBAC.md#customizing-permissions-end-to-end)
and [PERMISSION_COVERAGE.md](PERMISSION_COVERAGE.md)):

- Access Control › People shows, per permission, the **effective answer**, the
  **explicit decision** for the person (Allowed / Denied / Inherits from role)
  and **why** (granted by the role, directly, denied by an override, blocked
  because they are not on the project…), and names the office's copy of the
  role when that is what governs.
- Office roles marks a role as a **shared template** (first change creates the
  office's copy) or **this office's configuration**.
- `task.view`, `site_report.view`, `issue.view`, `design_change.view`,
  `project.invite_external`, `message.send`, `message.send_client` and
  `task.comment` are now enforced by the API, not only by the screens.
- An open tab re-reads its permissions on focus and after any 403 — no reload
  or re-login needed after a change.
- Development / QA: `ENVIRONMENT=development` (or `local`, `test`, `qa`) plus
  `STEP_UP_PERMISSION_EDIT_BYPASS=true` removes the verification code from
  role and person permission edits only. Production refuses to start with it.

**Rebuild first.** The backend and frontend images are built, not mounted:
`docker compose build backend worker frontend`, then
`docker compose up -d`. `backend/.env` now carries `ENVIRONMENT=development`
and `STEP_UP_PERMISSION_EDIT_BYPASS=true` for this local stack.

**Executed 2026-10-23 against an isolated database** (`cps_rbac_isolated`,
migrated from nothing to `i6f3a9c4d170`), a live backend running the working
tree, test accounts created only there:

| # | Scenario | Result |
| --- | --- | --- |
| A | Role grant `platform.create_project` to Engineer, no code → persisted → engineer creates a project (201) → revoke → 403 | PASS (5/5) |
| B | Person grant to Rana → she holds it, Omar (same role) does not and is refused → remove → Rana refused | PASS (5/5) |
| C | Inherited `issue.create` → person deny (explained `denied_for_user`) → 403 → remove → `granted_by_role` again | PASS (4/4) |
| D | `issue.view` revoked while signed in → next request 403, same token, no restart → restored | PASS (3/3) |
| E | Another office's engineer unaffected by this office's role edit; cannot open this office's project | PASS (2/2) |
| F | Engineer cannot edit permissions with the bypass on; password reset and deactivation still answer `STEP_UP_REQUIRED` | PASS (3/3) |
| F′ | Backend started with `ENVIRONMENT=production STEP_UP_PERMISSION_EDIT_BYPASS=true` | Refused to start (exit 1, names the variable) |

#### Retest on your stack (after the rebuild)

| # | Scenario | Expected | Result |
| --- | --- | --- | --- |
| P1 | Admin → Office roles → Engineer → tick *Create projects* | Saves with no verification dialog; label changes to "This office's configuration" | NOT TESTED |
| P2 | Engineer (already signed in, other browser) clicks back into the tab | "Add Project" appears without reloading; creating a project works | NOT TESTED |
| P3 | Untick it; engineer clicks back into the tab | Button gone; a direct `POST /projects` answers 403 | NOT TESTED |
| P4 | Access Control › People › an engineer → *Allow* a permission the role lacks | No dialog; row shows Allowed / "Allowed for this person" / "Granted directly to this person"; a colleague on the same role is unchanged | NOT TESTED |
| P5 | Same person → *Deny* a role permission, then *Use role default* | "Denied by a person-specific override", then "Granted by the Engineer role" | NOT TESTED |
| P6 | Deny *View issues* for an engineer; they open the project's Issues by URL | Page refused; `GET /issues/project/<id>` 403 in DevTools | NOT TESTED |
| P7 | Client representative opens a task/issue discussion nobody started | "You can reply once somebody starts this discussion…" instead of a Start button | NOT TESTED |
| P8 | Change your own password / reset someone's password | Verification code still required | NOT TESTED |

**Data consequences to know before P1–P8:** the Consultant (legacy) role — one
account in the development database — no longer posts task comments or
messages the client. That is the retired Consultant policy the role was frozen
from (intentional, see PERMISSION_COVERAGE.md); grant per person if needed. Client Representatives (five accounts) can no
longer *start* conversations through the API (the web client already offered
no button); they can still reply.

### 9.8 Permission-to-capability audit — 2026-10-23 (second pass)

Two reports: Rana granted *Create tasks* saw **Add Task** and got "Only the
assigned Project Manager can create project tasks"; Rana granted *Delete a
project* found no way to delete one. Both are fixed, along with every other
place that answered with the assigned-manager id instead of the permission —
see [PERMISSION_COVERAGE.md](PERMISSION_COVERAGE.md).

**Automated evidence (isolated database `cps_rbac_isolated`).**
`tests/test_permission_capabilities.py`:
- Defect A: person grant creates a task, which is persisted; revoke refuses
  with no row written; role grant reaches both engineers; a colleague is
  unchanged; deny stops the assigned manager; a grant never reaches a project
  the person is not on.
- Defect B on disposable projects: refused without the permission, project
  intact; per-project grant shows *Delete* on that project only; impact counts;
  delete removes only that project; audit row written.
- A read matrix of 18 permissions and a write matrix of 8, each in both
  directions.

#### Retest on your stack (after `docker compose build backend worker frontend`)

| # | Scenario | Expected | Result |
| --- | --- | --- | --- |
| T1 | Access Control › People › Rana › *Create tasks* → Allow; Rana opens a project she is on → Tasks → Add Task → save | Task appears; no error | NOT TESTED |
| T2 | Set Rana's *Create tasks* back to role default; Rana clicks back into the tab | Add Task gone; a direct `POST /tasks` answers 403 | NOT TESTED |
| T3 | Rana with *Edit tasks* allowed (and *See every task*) | Edit and delete a task she does not own | NOT TESTED |
| T4 | Deny *Update task progress* for an assigned engineer | Start / progress refused with a permission message | NOT TESTED |
| T5 | Office Roles › Engineer: read *Update task progress* | "Only on tasks assigned to the person." shown under it | NOT TESTED |
| D1 | Create a throwaway project; Access Control › People › Rana, project = that one › *Delete a project* → Allow | Projects page shows *Delete* on that project only | NOT TESTED |
| D2 | Delete → dialog | Counts listed; button disabled until the exact name is typed; Cancel changes nothing | NOT TESTED |
| D3 | Type the name → *Delete permanently* | Project gone from the list; the audit log has `project_deleted` | NOT TESTED |
| D4 | As a Project Manager without the grant | No *Delete* anywhere; `DELETE /projects/<id>` answers 403 | NOT TESTED |
| S1 | Documents › a document › *Parties* → tick the contractor party | The contractor's account can now open the document; untick → refused | NOT TESTED |
| S2 | Schedule two site visits for the same person at the same time | A conflict message, not a server error | NOT TESTED |

**Do not run D1–D3 on a real project.** Deletion is permanent and stored files
are not cleaned up (see *Policy decisions* in PERMISSION_COVERAGE.md).
