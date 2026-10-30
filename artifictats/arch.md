Architecture reference · as-built

# StructIQ Architecture

The construction consulting-office platform as it exists in the repository today — read from the code, not from intent.

SystemStructIQ

Branchmain · 2e10b51

Reviewed1 Sep 2026

ScopeAPI · Web · Mobile

Sections14

## Contents

1. [01Overall system](#s1)
2. [02Backend](#s2)
3. [03Database](#s3)
4. [04Auth & RBAC](#s4)
5. [05API communication](#s5)
6. [06Modules](#s6)
7. [07Data flows](#s7)
8. [08Integrations](#s8)
9. [09AI components](#s9)
10. [10Docker & deploy](#s10)
11. [11Strengths](#s11)
12. [12Risks](#s12)
13. [13Recommendations](#s13)
14. [14Not implemented](#s14)

Every component below was read from the code. Nothing is described that does not exist, and anything declared but not wired — or documented as a later step — is marked planned and collected in section 14.

01

## Overall system architecture

A monorepo holding two clients, one server and its documentation. Three deployable images; one database.

Fig. 1 — Deployed components and their boundaries

| Layer | Technology | Location |
| --- | --- | --- |
| Web client | React 19, TypeScript, Vite 8, Tailwind 3, TanStack Query 5, Zustand 5 | `frontend/` |
| Mobile client | Flutter 3.32.2 / Dart 3.8.1, Riverpod, go_router, Dio | `mobile_app/` |
| API | FastAPI 0.104, Python 3.11, SQLAlchemy 2.0, Pydantic 2 | `backend/` |
| Database | PostgreSQL 15, Alembic (58 migrations) | `backend/alembic/` |
| Orchestration | Docker Compose — 4 services, one behind a profile | `docker-compose.yml` |

Deliberate absence

There is **no message broker, no Redis and no separate worker tier**. Background jobs use an asyncio loop guarded by a PostgreSQL advisory lock, cross-worker fan-out uses `LISTEN/NOTIFY`, and rate limiting is a database table. The reasoning is recorded in `services/scheduler.py` and `services/rate_limit_service.py`.

02

## Backend architecture

`backend/app` is 213 Python modules in six layers, with a strict direction of dependency: API → services → models.

| Package | Responsibility | Size |
| --- | --- | --- |
| `app/api/` | HTTP surface only: routing, status codes, request validation | 35 modules, \~319 routes |
| `app/schemas/` | Pydantic request and response contracts | 27 modules |
| `app/services/` | All domain logic, policies and integrations | \~100 modules |
| `app/models/` | SQLAlchemy 2.0 typed ORM models | 30 modules, 76 tables |
| `app/core/` | Config, JWT and password primitives, FastAPI deps, permission catalogue | 8 modules |
| `app/ai/` | Model-facing concerns: transcription, analysis, action schemas | 11 modules |
| `app/db/` | Session factory, admin bootstrap, demo seed, RBAC backfill and equivalence | 6 modules |

### Application lifecycle

`app/main.py` uses a FastAPI `lifespan` that starts the reminder scheduler, opens **one PostgreSQL `LISTEN` connection per uvicorn worker**, and logs explicitly whether push, RAG and realtime are configured — so “unconfigured” is never indistinguishable from “nothing happened”. Shutdown stops the listener before the scheduler, so the socket closes while the loop is still running.

### Configuration

`app/core/config.py` is a single pydantic-settings object whose validator **refuses to boot on incoherent configuration**: voice or RAG enabled without an OpenAI key, push enabled without FCM credentials, an OTP shorter than six digits, a RAG chunk overlap at or above the chunk size, an SSE ticket TTL measured in hours. Anything that costs money or writes to people's notification queues defaults to off.

### Background and long-running work

| Work | Mechanism | Where |
| --- | --- | --- |
| Reminder sweeps | asyncio task + PG advisory lock (`776120431`) | `services/scheduler.py` |
| Push delivery | Background thread with its own session, flushed on `after_commit` | `services/push/dispatcher.py` |
| IFC parse / geometry | `multiprocessing` subprocess with timeouts and vertex caps | `services/ifc_processing_service.py` |
| Agent analysis | **Inline**, inside the emitting transaction, wrapped so it cannot fail the primary write | `services/agents/event_subscriber.py` |

03

## Database architecture

PostgreSQL 15, one database, 76 tables, accessed through SQLAlchemy 2.0 typed `Mapped[...]` models. Conventions are applied consistently: UUID primary keys, timestamp mixins, JSONB for open-ended payloads, partial unique indexes for “unique per organization, and unique globally when organization is NULL”, and check constraints for closed string vocabularies.

| Domain | Representative tables |
| --- | --- |
| Identity & RBAC | `users`, `companies`, `roles`, `role_permissions`, `disciplines`, `user_disciplines`, `organization_memberships`, `project_parties`, `project_member_disciplines`, `role_permission_overrides`, `user_permission_overrides`, `consultant_engineer_scopes` |
| Auth & security | `revoked_tokens`, `password_reset_tokens`, `otp_challenges`, `step_up_grants`, `rate_limit_hits`, `audit_logs` |
| Projects & work | `projects`, `project_members`, `tasks`, `task_dependencies`, `task_comments`, `task_reviews`, `task_reschedule_logs`, `milestones` |
| Field & site | `site_reports`, `site_visits`, `field_submissions`, `field_submission_photos`, `photo_categories`, `photo_category_assignments` |
| Documents | `documents`, `document_chunks`, `document_party_shares`, `attachments`, `media_assets` |
| IFC / BIM | `ifc_model_versions`, `ifc_model_groups`, `ifc_elements`, `ifc_spatial_nodes`, `ifc_comparisons`, `ifc_change_records`, `ifc_coordination_findings`, `ifc_suggestions`, `ifc_impact_suggestions`, `ifc_entity_links`, `ifc_processing_jobs` |
| Voice | `voice_recordings`, `voice_analyses`, `voice_action_drafts`, `voice_clarifications`, `voice_execution_logs` |
| AI governance | `ai_insights`, `ai_insight_sources`, `ai_action_versions`, `ai_provider_calls`, `agent_runs`, `domain_events` |
| Messaging & notification | `conversations`, `conversation_participants`, `messages`, `message_recipient_states`, `notifications`, `device_tokens` |
| Collaboration | `owner_requests`, `reminder_rules`, `reminder_events`, `cost_validations`, `design_changes`, `issues`, `project_view_states` |

Vector storage

`document_chunks` holds embeddings in a JSONB column; similarity is cosine, computed in numpy over the candidate set. `VectorStore` is a Protocol precisely so the storage choice can change without touching retrieval. Migrations are Alembic, applied at container start.

04

## Authentication and RBAC

### Authentication implemented

- **Passwords** — argon2 via passlib.
- **Tokens** — JWT HS256. Access 30 minutes, refresh 7 days, each carrying a `type` claim that is checked, never assumed.
- **Refresh rotation** — single-use. The old token is SHA-256 hashed into `revoked_tokens`; expired rows are pruned on login.
- **Three token types that cannot substitute for one another** — `access`, `refresh` and `sse_ticket` (\~60 s, read-only, because `EventSource` cannot send an `Authorization` header).
- **Forced password change** — `must_change_password` blocks every route except four allow-listed ones, inside `get_current_user`.
- **Step-up OTP** — an emailed code for a named purpose grants a short window (10 minutes) for one sensitive operation. Rate-limited on sends, resends and verify attempts.
- **Login brute-force protection** — database-backed, because the API runs multiple workers.

### Authorization implemented

The platform was redesigned from six hardcoded roles to a configurable role model for a consulting office:

```
Organization (companies)
 ├── Role ──────────── RolePermission     configurable; org-owned or global template
 ├── Discipline ────── ifc_disciplines[]  specialization; grants nothing
 └── OrganizationMembership               "I work here, in this role"

Project
 ├── ProjectParty ──── parent_party_id    client / contractor / subcontractor
 └── ProjectMember ─── project_role_id, party_id (NULL = office staff)
                   └── ProjectMemberDiscipline
```

`app/core/permission_catalogue.py` declares roughly 54 permission codes. Each carries five facts: default roles, `project_scoped`, `admin_locked`, `office_only` and `never_external`.

`effective_permissions()` is **the single resolution path** — voice, the AI tool layer, the agents, document retrieval and the IFC workspace all arrive there:

1. Office role's permissions ∪ project role's permissions
2. `RolePermissionOverride` — role-wide administrator decision
3. `UserPermissionOverride` — one person, everywhere
4. `UserPermissionOverride` — one person, on this project (narrowest wins)

Three ceilings that configuration cannot lift

A deactivated account holds nothing. A project-scoped permission additionally requires access to that project. An **external participant** never holds a non-project-scoped permission, nor anything in `NEVER_EXTERNAL` — certification and access governance — and that strip is re-applied *after* overrides, so a mistake in Access Control cannot become a breach. External document access is deny-by-default: a contractor sees nothing until a `DocumentPartyShare` row exists, with no project-level fallback.

### Client-side enforcement is presentation only

The web client caches `GET /access-control/me` in a store and gates routes with `PermissionGuard`; the mobile client asks the same permission codes through `Capabilities`. Both are documented as presentation state — the server re-checks every operation, so a too-generous answer costs a wasted tap and a 403, never access.

### Migration state in progress

The retired enum has **not** been removed. `users.role` is still `NOT NULL` and still written; `users.org_role_id` is the authority whenever it is set. `Role.legacy_role` and `legacy_affiliation` exist solely to satisfy that NOT NULL during provisioning, and are documented as dropped by the same migration that drops `users.role`. `legacy_effective_permissions()` is kept, uncalled, so `rbac_equivalence.py` can prove no account's access changed.

05

## API communication

- **REST** at `/api/v1`, JSON, 35 router modules. Login is OAuth2 password flow (form-encoded); everything else is Bearer JWT.
- **Server-Sent Events** for live updates: `POST /events/ticket` then `GET /events/stream?ticket=…`. Publishing is `pg_notify` on the caller's own session, so it is **transactional** — an event cannot announce a change that was rolled back. All workers listen on one channel.
- **Events are hints, never state.** An envelope carries identifiers and a type; the client refetches through REST, which re-applies every authorization rule. Connection scope is re-resolved on a 30-second TTL, so a user removed from a project stops receiving its events within seconds.
- **Web transport** performs *single-flight refresh* — one shared promise, because a rotating single-use refresh token cannot survive a race — and deliberately distinguishes a `STEP_UP_REQUIRED` 401 from an expired-token 401.
- **Mobile transport** repeats the same pattern in Dio: attach token, refresh once on 401, retry, otherwise clear tokens.
- **Static files** — `/uploads` is a `StaticFiles` mount. Private artefacts (IFC sources, geometry, voice audio) live in a separate directory served only through authenticated endpoints.

06

## Main modules and their responsibilities

| Module | Backend | Web | Mobile |
| --- | --- | --- | --- |
| Projects & members | `api/projects.py` | Full | Full |
| Tasks, dependencies, CPM scheduling | `api/tasks.py`, `services/cpm_service.py` | Full + Gantt | Full |
| Documents & sharing | `api/documents.py`, `services/document_access.py` | Full | — |
| IFC / BIM workspace | `api/ifc.py` (55 routes), 9 services | three.js viewer | List only |
| Site reports & field evidence | `api/site_reports.py`, `api/field_submissions.py` | Full | Capture |
| Issues & design changes (RFIs) | `api/issues.py`, `api/design_changes.py` | Full | Create |
| Messaging | `api/messages.py`, `services/messaging_policy.py` | Full | Full |
| Notifications & push | `services/notification_service.py`, `services/push/` | Full | Full |
| Voice assistant | `api/voice.py`, \~20 services | Full | Full |
| AI insights & agents | `api/ai_intelligence.py`, `api/agents.py` | Full | Diagnostics |
| Access control & org configuration | `api/permissions.py`, `api/organization.py` | Admin pages | — |
| Collaboration — owner requests, visits, reminders | `api/collaboration.py` | Full | Full |
| Cost validation | `api/cost_validations.py` | Full | — |
| Step-up authentication | `api/step_up.py` | `useStepUp` | — |

The frontend is organized feature-first, with shared UI primitives, Zustand stores, providers and hooks. Every route destination is lazy-loaded. There is **one URL per project** — `/projects/:projectId/…` — and the four retired role-prefixed URLs remain registered as redirects, because they exist in delivered push notifications and bookmarks. Localization is English and Arabic with RTL, on both clients.

07

## Important data flows

#### Voice command → executed change

```
record → POST voice (private storage) → transcription (OpenAI)
      → construction analysis (structured output)
      → voice_router: deterministic routing on five independent signals
      ├── question  → voice_query_service / knowledge_router → spoken answer
      └── mutation  → proposed actions + confirmation token (JWT, 10 min)
                    → user confirms → voice_action_service executes
                    → audit_log + ai_action_versions + domain event
```

The AI decides *intent*; the backend decides *authorization and execution*. Nothing manufactures an action from an empty action list.

#### Document question (RAG)

```
upload → chunk (tiktoken) → embed (OpenAI) → document_chunks (JSONB)
ask    → knowledge_router picks the source (structured data / IFC / documents)
       → retrieval (cosine over authorized chunks)
       → answering: citations built from chunk records, never parsed from prose;
         `found` is computed; unsupported answers return INSUFFICIENT_CONTEXT
```

#### IFC upload → coordination findings

```
upload → private storage → validate → subprocess parse (ifcopenshell, timeout)
      → spatial hierarchy → elements → properties → quality checks
      → geometry → comparison against previous version → change records
      → interference detection → coordination findings → impact suggestions
      → notifications; every state transition is a checked transition
```

#### Notification fan-out

```
notify()  ├── PostgreSQL row  (always, inside the caller's transaction)
          └── push queue      (flushed after commit, background thread)
```

The row is the notification; push is a doorbell for it. A rolled-back transaction never rings.

#### Proactive agent analysis off by default

```
emit_domain_event → event_subscriber → orchestrate_for_event
   authority = the project's assigned Project Manager
   no assigned manager → skipped, with no fallback to anything broader
```

An automatic run borrows a real authority a real administrator granted, so it can never read anything a person could not.

08

## External integrations

| Integration | Purpose | State |
| --- | --- | --- |
| **OpenAI** | Transcription, voice analysis, response phrasing, embeddings, RAG answering, optional IFC analysis | implemented The only LLM provider. Every call recorded in `ai_provider_calls`. |
| **Firebase Cloud Messaging** | Push to Android, iOS and web browsers | implemented Off by default; service account mounted read-only. |
| **SMTP** | Invitations, password reset, step-up OTP codes | implemented Optional; absence logs a warning and degrades. |
| **ifcopenshell** | IFC parsing and geometry (in-process library, not a service) | implemented |

No payment, ERP, accounting, calendar or storage-provider integration exists.

09

## AI-related components

Five distinct subsystems, all routed through the same authorization service.

1. 01

   **Voice assistant**`app/ai/` plus roughly 20 `services/voice_*` modules. Arabic and English. Deterministic intent routing, entity resolution, task matching, a rules engine, a clarification loop, confirmation tokens and execution logging.
2. 02

   **AI tool layer**20 declared tools — 15 read, 5 propose. Each `ToolSpec` binds a name to an argument schema, a permission code and a handler. A handler without a registry row is unreachable; nothing is discovered by reflection.
3. 03

   **Agents**Five fixed agents: Site Report, Document Consistency, Revision Impact, RFI, Schedule Risk. Each declares its own narrow tool grant, permission, source engine and event subscriptions. The orchestrator runs them one at a time, isolated — a failure in one leaves the others' results intact — with no agent-to-agent chaining.
4. 04

   **RAG**Chunking, embeddings, JSONB vector store, retrieval and grounded answering. Three independent mechanisms push toward grounding rather than trusting the model to behave.
5. 05

   **AI governance**`ai_action_versions` (append-only before/after state with revert), `ai_insight_sources` with snapshot hashes for stale-insight invalidation, `ai_provider_calls` and `domain_events`.

The rule that holds across all five

AI proposes; the backend authorizes and executes; everything is traceable to a real person's authority.

10

## Docker and deployment structure

| Service | Image / build | Ports | Notes |
| --- | --- | --- | --- |
| `db` | `postgres:15` | 5432→5432 | Healthcheck, `postgres_data` volume |
| `backend` | python:3.11 | 8000→8000 | `uploads_data` and `voice_audio_data` volumes; `./backend/secrets` bind-mounted read-only |
| `frontend` | node:20 build → nginx:1.27-alpine | 5173→80 | Vite env inlined as build args |
| `flutter-tools` | `Dockerfile.ci` | — | `mobile-tools` profile; never starts with `docker compose up` |

Backend start sequence: `wait_for_db.py` (polls, proceeds the instant the database answers) → `alembic upgrade head` → uvicorn with two workers and `--proxy-headers`. The Dockerfile `CMD` additionally bootstraps an admin and seeds demo data; Compose overrides the command and skips both.

Firebase web values must be build-time args because Vite inlines `import.meta.env.*` at compile time. `RAILWAY_DEPLOYMENT.md` describes a three-service Railway layout and states plainly that it is **preparation guidance only — no deployment has been performed.**

11

## Current architecture strengths

1. 01

   **One authorization path, and it is enforced**Every subsystem resolves through `services/authorization.py`. The hard ceilings are re-applied after administrator overrides, so misconfiguration cannot escalate into a breach.
2. 02

   **Configurability without a schema change**An office creates “Resident Engineer” and decides what it may do — no code change, no migration, no route table update. The URL scheme was flattened specifically so it could not depend on role names.
3. 03

   **AI is architecturally constrained, not merely prompted**Tools are declared, not discovered. Citations are built from records the model cannot reach. Actions require confirmation. Every mutation lands in `ai_action_versions` with before and after state.
4. 04

   **Correct under multiple workers**`LISTEN/NOTIFY` for realtime, an advisory lock for the scheduler, a database table for rate limiting — each chosen because the per-process alternative would silently break at `--workers 2`.
5. 05

   **Failure isolation as a stated rule**Geometry failure does not fail an IFC upload, agent failure does not fail the write that triggered it, push failure does not lose a notification.
6. 06

   **Configuration that refuses to lie**The settings validator will not boot a process claiming a feature works when it cannot, and boot logs state plainly what is configured.
7. 07

   **A migration with an evidence gate**`rbac_equivalence.py` compares the new model's answer against the retired one for every real account, rather than asserting the redesign was safe.
8. 08

   **Substantial backend test coverage**90 test modules, including dedicated suites for external-party isolation, authorization equivalence, AI tool authorization and IFC failure paths.

12

## Current architectural risks and weaknesses

1. 01

   **Document bytes are not access-controlled**`GET /documents/{id}/download` correctly calls `assert_document_readable` — and then returns a URL into the `/uploads` `StaticFiles` mount, which has no authentication. The deny-by-default sharing model protects metadata and discovery, but anyone holding or guessing a URL can fetch the file. IFC and voice already demonstrate the correct pattern; documents and attachments do not use it.
2. 02

   **Two role models are live at once**`users.role` and `users.org_role_id` coexist. `core/deps.py` still contains role-based helpers — `require_admin`, `require_project_creation`, `require_project_member_management` and `get_manageable_project_or_403` — that bypass the configurable path everything else funnels through. Until the window closes there are two answers to “who may do this”.
3. 03

   **Vector search does not scale**Cosine similarity is computed in Python over JSONB rows, brute force per query. Fine at the current corpus size, but linear in documents and single-threaded.
4. 04

   **Heavy work runs in the API process**IFC parse and geometry fork subprocesses from the web container; agent analysis runs inline inside the emitting transaction. There is no queue, no worker tier and no backpressure — and enabling automatic analysis puts LLM latency inside a write transaction.
5. 05

   **File storage is host-local**Uploads live in named Docker volumes, so the backend cannot be horizontally scaled as it stands. `PrivateStorage` is a Protocol ready for S3/R2, but only the `local` implementation is written — and the public upload path has no such abstraction at all.
6. 06

   **Tokens in `localStorage`**Both access and refresh tokens are stored where any XSS can read them; refresh rotation limits the window but does not close it.
7. 07

   **Startup diverges between environments**The Dockerfile bootstraps an admin and seeds demo data; Compose overrides the command and does neither. The path exercised locally is not the one shipped.
8. 08

   **Compose defaults are development-grade**A default database password is baked into `docker-compose.yml`, and 5432 is published to the host.
9. 09

   **Thin client-side test coverage**11 test files across 245 frontend sources; the mobile app has 10. Backend coverage is far ahead of both.
10. 10

    **Vestigial configuration**`vite.config.ts` proxies `/ws` to a WebSocket target that does not exist — realtime is SSE. `NotificationChannel.TELEGRAM` is declared with no provider behind it. A JVM crash dump and `frontend/dist/` sit in the repository root.
11. 11

    **A single JWT signing key with no rotation path**`SECRET_KEY` signs access tokens, refresh tokens, SSE tickets and voice confirmation tokens alike; rotating it invalidates all four at once.

13

## Recommended improvements

Ordered by risk reduced per unit of work.

|  | Recommendation | Addresses |
| --- | --- | --- |
| 1 | Serve documents and attachments through an authenticated streaming endpoint, or signed expiring URLs, and unmount `/uploads` from `StaticFiles`. Reuse the `private_storage` pattern already proven by IFC. | Risk 1 |
| 2 | Close the RBAC migration window: replace the remaining role-based helpers in `core/deps.py` with `require_permission`, run the equivalence gate, then drop `users.role` and its companions. | Risk 2 |
| 3 | Move IFC processing and agent analysis out of the request path. Given the deliberate no-broker stance, a database-backed queue using the advisory-lock worker pattern already in `scheduler.py` fits without new infrastructure. | Risk 4 |
| 4 | Execute the documented pgvector migration behind the existing `VectorStore` Protocol. | Risk 3 |
| 5 | Write the S3/R2 `PrivateStorage` implementation and give public uploads the same abstraction, so the backend becomes stateless. | Risk 5 |
| 6 | Make one start sequence authoritative — keep the Dockerfile `CMD` and delete the Compose override, or move bootstrap and seed into an explicit one-shot service. | Risk 7 |
| 7 | Move the refresh token to an `HttpOnly`, `Secure`, `SameSite` cookie and keep only the access token in memory. | Risk 6 |
| 8 | Add a `kid` claim and support two active signing keys, so `SECRET_KEY` can rotate without a fleet-wide logout. | Risk 11 |
| 9 | Remove dead configuration: the `/ws` proxy, the `TELEGRAM` channel value (or implement the provider), the committed crash dump and `dist/`. | Risk 10 |
| 10 | Raise client test coverage toward the backend's standard, starting with the permission guards and token-refresh interceptors — the two places where a client-side bug has security consequences. | Risk 9 |
| 11 | Parameterize the Compose database password with no default, and stop publishing 5432 unless it is explicitly needed. | Risk 8 |

14

## Planned, or not implemented

Stated in the code or documentation, and **not** currently built.

| Item | Status in the repository |
| --- | --- |
| **Phase 8 — autonomous agents** | `orchestrate_for_event()`, `subscribes_to`, the notification policy and finding-routing declarations all exist and are tested, but `AGENT_AUTO_ANALYSIS_ENABLED` defaults to false. `api/agents.py:133` names Phase 8 as the step that turns it on. |
| **pgvector** | Documented as a later migration in `RAG.md` §10. The JSONB and numpy store is what runs today. |
| **Object storage** | `PrivateStorage` is a Protocol with one `local` implementation; S3/R2 is described as “one class” of future work. |
| **Railway deployment** | Preparation guidance only. No deployment and no remote migration have been performed. |
| **CI** | The Flutter `mobile-tools` profile is described as suitable for a future pipeline. No CI configuration exists in the repository. |
| **Android release signing** | Release builds fall back to debug signing. CI signing is supported through environment variables, but no keystore is mounted. |
| **iOS releases** | The Linux tools image cannot produce them; this requires macOS and is explicitly out of scope for the Docker setup. |
| **Additional notification channels** | `NotificationChannel.TELEGRAM` is declared. Adding a channel is documented as one provider plus one line in `_fan_out`. Neither exists. |
| **Document contradiction detection** | `docs/AGENTS.md:137` states that comparing two passages for contradiction is not implemented, and the agent says so rather than implying otherwise. |

Compiled from the working tree at `main` · 2e10b51. Source of record: `docs/ARCHITECTURE.md`.