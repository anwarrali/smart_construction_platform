# Constrex — Living Project Log

Last updated: 2026-10-27 (Asia/Hebron)

## Retained project knowledge

Constrex is a graduation project for construction-project management and
collaboration. Its four conceptual modules are Core Project Management,
Documents & AI, Execution & Communication, and Administration & Access
Control. The primary stack is React/TypeScript/Vite, FastAPI/SQLAlchemy/Alembic,
PostgreSQL/pgvector, Docker Compose, and a Flutter client using the same APIs.

Implementation claims must come from the current repository and current test
evidence. The master handover remains the detailed source for historical work,
measurements, proposed features, cleanup history, notification diagnostics,
and diagram requirements. In particular, the full Design Package workflow,
every proposed AI behavior, external integrations, mobile/web parity, and IFC
3D quality must not be treated as complete without verification.

## Completed work in this continuity stage

- Read the complete master handover supplied on 2026-10-27.
- Inspected the repository, Git state, top-level runtime documentation, test
  inventory, Compose state, Alembic file head, and selected implementation
  evidence without changing application code or data.
- Established a current-state baseline and created this living log.

## Current implementation state

- Repository access is available.
- Checked-out branch: `feat/ingestion-reliability`.
- HEAD: `fe489dc758fda63ab121e7457e6594fe89c81c34` (`feat: improve job runner
  reliability and automatic RAG indexing`, committed 2026-10-09).
- The branch has no displayed upstream; the same commit is referenced by the
  local `feat/job-runner` branch and `origin/feat/job-runner`.
- The working tree is substantially dirty: 176 tracked diff entries and 189
  untracked files were enumerated. One tracked frontend IFC viewer file is
  deleted. These changes predate this continuity stage and their ownership and
  intended grouping have not been established.
- Current files contain backend/frontend work in ingestion, IFC, RBAC,
  permissions, agents, voice, projects, tasks, notifications, and UI, plus new
  migrations and tests. Presence in the worktree is not evidence of completion.
- Alembic's source-tree head resolves to `i6f3a9c4d170`; the connected database
  revision has not been checked.
- Docker Desktop's Linux engine was not running/reachable, so service health,
  database connectivity, and worker behavior are not verified.
- Test-file inventory: 117 backend, 33 frontend, and 10 mobile test files.

## Known bugs and technical risks

- The large uncommitted change set makes the tested baseline and feature
  boundaries unclear and creates a high risk of misattributing work.
- Three newest Alembic migrations are untracked; migration files existing in
  the source tree do not prove that the current database is at that head.
- No current full test run has been performed in this continuity stage.
- `docs/MANUAL_QA_TEST_PLAN.md` still uses the former StructIQ name and contains
  many unchecked manual cases. Its later defect register reports automated
  fixes, but those fixes are largely in the uncommitted worktree and need fresh
  verification.
- The handover's notification, IFC performance/quality, ingestion, RBAC, RAG,
  and mobile issues remain historical or unresolved until reproduced against
  the present environment.

## Decisions and rationale

- Preserve the Constrex name, four-module structure, established stack, RBAC
  integrity, citation-aware RAG intent, and clean modular diagram requirements.
- Treat the handover as historical context and the inspected code plus fresh
  tests as the authority for current status.
- Classify features as implemented, partially implemented, planned, or
  unresolved; do not infer completion from routes, documents, or test files.
- Keep IFC 3D optional; prefer semantic hierarchy and readable 2D technical
  views unless quality and performance are accepted.
- Keep the broad Design Package workflow and external integrations out of
  current scope unless the repository and graduation priorities establish them.
- Do not clean, reset, migrate, delete, or reorganize the dirty worktree until
  its intended contents are understood and protected.

## Pending tasks

1. Establish ownership and intended scope of the current uncommitted changes.
2. Protect the work with a recoverable checkpoint before any cleanup or
   separation, if the user wants one.
3. Start Docker Desktop, inspect service health and the live Alembic revision.
4. Run backend, frontend, and mobile checks and record exact commands/results.
5. Execute the relevant manual QA smoke/retest cases and reconcile the defect
   register with observed behavior.
6. Build a verified feature matrix across the four modules.
7. Update remaining old branding in documentation only after confirming the
   document is still an active deliverable.

## Last verified Git state

- Branch: `feat/ingestion-reliability`
- Commit: `fe489dc758fda63ab121e7457e6594fe89c81c34`
- Verified: 2026-10-27
- Working tree: dirty; no reset, cleanup, commit, checkout, or migration was run.

## Last verified test results

- Current continuity stage: no application test suite has yet been run.
- Environment check: `docker compose ps` could not connect because the Docker
  Desktop Linux engine was unavailable.
- Historical handover only: backend 2,521 passed / 1 skipped / 0 failed;
  frontend 228 passed; mobile 38/38 passed with clean analysis and an API 35
  emulator E2E checkpoint. These results are not current verification.
- The manual QA document records later automated PASS claims through
  2026-10-23, but they have not been rerun in this stage.

## Single most useful next action

Confirm that the current uncommitted work is intentional and should be
preserved as the active work-in-progress baseline; then create a recoverable
checkpoint and run the full verification sequence from that exact state.

## Preservation inventory — 2026-10-27

Status: inventory complete; backup not yet created. No application code,
configuration, upload, database, Git ref, index, or migration was changed.

### Actions and actual results

- Re-read this log before updating it.
- Inspected `git status --short`, `git diff --stat`, `git diff --name-only`,
  `git diff --numstat`, the untracked-file list, directory distribution, and
  representative RBAC, ingestion/RAG, IFC, tasks, voice, frontend, migration,
  and test changes.
- Tracked diff: 176 files, 5,102 insertions, 1,973 deletions. The changes span
  112 frontend files, 59 backend files, and 5 documentation files.
- Untracked inventory after this log was introduced: 190 files totalling about
  31.89 MiB. The largest items are generated graduation reports and previews;
  the inventory also contains source diagrams, evidence outputs, three
  Alembic migrations, tests, UI components, and documentation.
- The changes do not appear to be one task. Representative evidence shows at
  least RBAC/project-scope redesign, permission UI and migrations, ingestion
  and RAG reliability, IFC processing and removal of the web 3D viewer, task
  filtering/reliability, voice failure handling, shared UI/design work, QA
  regression tests, and report/diagram generation.
- Sensitive ignored local files were detected by path only; their values were
  not displayed or copied: root/backend/frontend `.env` files, an FCM service
  account file, and the Flutter Firebase project configuration. A secret-pattern
  path scan also matched generated frontend output and configuration examples,
  which must be reviewed without publishing their contents.
- Ignored runtime data exists under `backend/private_uploads` (150 files,
  approximately 0.09 MiB); `backend/uploads` is empty. No repository-local
  `.db`, SQLite, dump, or backup file was found by the filename scan.
- Large reproducible local directories include `frontend/node_modules`
  (approximately 369.98 MiB), `mobile_app/build` (approximately 1,141.97 MiB),
  and `mobile_app/.dart_tool` (approximately 174.15 MiB). `.git` is about
  39.11 MiB. A literal full-directory copy therefore needs roughly 1.8–2 GiB
  plus destination overhead.
- Only the C: filesystem was visible, with approximately 124.07 GiB free. No
  user-approved private backup destination has been supplied.
- Available preservation tools are Windows Robocopy and bsdtar. No 7-Zip
  command was found.

### Backup recommendation

Use a new timestamped directory on a private NTFS destination outside this
repository, preferably an external or independently protected drive. Make a
literal copy including `.git`, tracked/untracked files, ignored credentials,
private uploads, and metadata practical on NTFS. Create a separate `git bundle
--all` for Git history, plus file inventory and SHA-256 manifests; verify the
copy by counts, sizes, hashes, bundle verification, and a read-only Git status
comparison. Never place the credential-bearing copy in a shared/public path.

Recovery must be documented and tested against a separate empty directory. A
source-only/public archive, if later needed, must be a separate artifact that
excludes all `.env` files, service-account credentials, Firebase deployment
configuration, private uploads, caches, and generated bundles containing
those files.

### Blockers before backup or testing

- The user must provide and confirm the private backup destination.
- The destination must have at least 3 GiB free for a literal copy and
  verification artifacts; more is preferable.
- Docker remains unavailable, so the PostgreSQL Docker volume cannot yet be
  inspected or dumped. A filesystem backup alone must not be described as a
  database backup.
- Some ignored Flutter ephemeral symlink paths denied enumeration during the
  scan. The copy must avoid following junctions/symlinks and must report every
  skipped or failed path before it can be accepted as verified.
- No tests, builds, migrations, dependency installation, cleanup, checkout,
  reset, stash, merge, or rebase may run until the backup is created and
  verified.

## Backup destination check — 2026-10-27

- User authorized `D:\ConstrexBackups`, describing it as an existing, private,
  writable external destination. This supersedes the earlier missing-destination
  item; permission to use this specific destination has been provided.
- `Get-Item` and `Get-PSDrive` could not find D: in the sandbox. Repeated the
  destination and drive checks with approved execution outside the sandbox;
  D: was still absent and only C: was listed.
- Destination free space, filesystem, permissions, and actual writability
  therefore remain unverified. No backup directory, copy, or bundle was created.
- Reconfirmed branch `feat/ingestion-reliability` and HEAD
  `fe489dc758fda63ab121e7457e6594fe89c81c34`.
- No application code changed and no tests, builds, migrations, or Docker
  startup were run. Only this log was updated after reviewing its contents.
- Next action: reconnect the external drive at D: or provide its actual path;
  then resume destination validation and the authorized verified backup.
