# Railway Deployment Readiness

This repository is prepared for a three-service Railway staging project:

```text
Frontend (public)  --->  Backend (public)  --->  Railway PostgreSQL
 React/Vite/Nginx         FastAPI/Uvicorn          managed service
```

This document is preparation guidance only. No Railway deployment or remote
database migration has been performed.

## What the repository already provides

- Isolated `frontend/` and `backend/` applications, each with a root-local
  `Dockerfile`.
- A production Vite build served by Nginx.
- React Router fallback through `try_files $uri $uri/ /index.html`.
- FastAPI at `app.main:app`, bound to `0.0.0.0`.
- Environment-based SQLAlchemy and Alembic `DATABASE_URL`.
- A lightweight backend `GET /health` endpoint.
- Comma-separated, credential-safe CORS configuration through `CORS_ORIGINS`.
- Local PostgreSQL, uploads, and private voice-audio volumes in
  `docker-compose.yml`.

Railway supports isolated monorepos by assigning each service its own Root
Directory, and automatically detects a capitalized `Dockerfile` at that root:
[monorepo documentation](https://docs.railway.com/deployments/monorepo) and
[Dockerfile documentation](https://docs.railway.com/builds/dockerfiles).

## Local Docker Compose

Local development remains:

```powershell
docker compose up -d --build
```

The local backend continues to use the Compose PostgreSQL hostname `db` and
port `5432`. Compose overrides the backend image command so it still runs
`alembic upgrade head` and listens on port `8000`. The frontend remains
available on `http://localhost:5173`.

Do not use the root `.env.example` or `backend/.env.example` as real secrets.
Copy them to ignored `.env` files and replace every placeholder.

## Railway service layout

Create an empty Railway project with these services:

| Service | Source | Root Directory | Public domain | Health path |
|---|---|---:|---:|---:|
| Frontend | This Git repository | `/frontend` | Yes | `/healthz` |
| Backend | This Git repository | `/backend` | Yes | `/health` |
| PostgreSQL | Railway PostgreSQL | Managed | No application-facing domain required | Managed |

No `railway.toml` is required. Both Dockerfiles are already located at the
corresponding service roots, so Railway's default Dockerfile detection is the
least surprising configuration.

## Backend variables

Required in the Railway **Backend** service:

| Variable | Railway staging value |
|---|---|
| `DATABASE_URL` | Add a reference to the PostgreSQL service's `DATABASE_URL` |
| `SECRET_KEY` | A new high-entropy staging secret; never reuse a local or production secret |
| `FRONTEND_URL` | `https://FRONTEND_DOMAIN.up.railway.app` |
| `BACKEND_URL` | `https://BACKEND_DOMAIN.up.railway.app` |
| `CORS_ORIGINS` | `https://FRONTEND_DOMAIN.up.railway.app` |

Railway supplies `PORT`; do not hard-code it. The backend starts with:

```sh
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} \
  --workers ${WEB_CONCURRENCY:-2} --proxy-headers
```

Optional backend variables:

```dotenv
WEB_CONCURRENCY=2
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
PASSWORD_RESET_EXPIRE_MINUTES=60
UPLOAD_DIR=/app/uploads
PRIVATE_UPLOAD_DIR=/app/private_uploads
VOICE_AUDIO_RETENTION_POLICY=PRESERVE

# Only when email is enabled:
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_USE_TLS=true

# Only when AI voice processing is enabled:
OPENAI_API_KEY=
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe
OPENAI_ACTION_MODEL=
```

Backend-only secrets must never use a `VITE_` prefix. Railway supports reference
variables for managed PostgreSQL, keeping `DATABASE_URL` synchronized without
copying its password:
[PostgreSQL documentation](https://docs.railway.com/databases/postgresql) and
[variable references](https://docs.railway.com/variables/reference).

## Frontend variables

Required in the Railway **Frontend** service before its production build:

```dotenv
VITE_API_BASE_URL=https://BACKEND_DOMAIN.up.railway.app/api/v1
```

This value is intentionally public and contains no secret. Vite embeds it in the
static bundle at build time, so redeploy the Frontend after changing it.

The frontend Dockerfile declares `ARG VITE_API_BASE_URL`, which allows Railway's
build environment to pass the service variable into Vite. Nginx listens on
Railway's injected `PORT` and serves the SPA. Local Compose explicitly builds
the browser bundle with `http://localhost:8000/api/v1`. Nginx has no dependency
on a Compose-only backend hostname, so the Frontend service can start
independently on Railway.

## CORS

`CORS_ORIGINS` is a comma-separated allowlist. Do not use `*` because
authentication uses credentials.

Examples:

```dotenv
# Local backend
CORS_ORIGINS=http://localhost:5173

# Railway staging backend
CORS_ORIGINS=https://FRONTEND_DOMAIN.up.railway.app

# Multiple explicit domains if needed
CORS_ORIGINS=https://FRONTEND_DOMAIN.up.railway.app,https://staging.example.com
```

Do not include paths such as `/api/v1` in a CORS origin.

## PostgreSQL and Alembic

The backend uses the existing SQLAlchemy `psycopg2` driver. Railway's
`postgresql://...` `DATABASE_URL` is compatible with the current engine and
Alembic configuration.

Configure this as the Backend **Pre-Deploy Command**:

```sh
alembic upgrade head
```

Railway runs pre-deploy commands with service variables and private networking,
which is suitable for migrations. A failing migration prevents the deployment
from proceeding. Do not put demo seeding in this command:
[pre-deploy command documentation](https://docs.railway.com/deployments/pre-deploy-command).

Before every deployment:

```sh
alembic heads
alembic current
```

The repository currently has one migration head. No migration contains a
Railway hostname or credential.

## Persistent file storage

PostgreSQL does not store uploaded files. The backend currently uses local
filesystem storage, so attach Railway volumes to the Backend service:

| Purpose | Mount path |
|---|---|
| Public project uploads | `/app/uploads` |
| Private AI voice audio | `/app/private_uploads` |

Without these volumes, uploads will be lost on redeploy. Railway volumes are
mounted at runtime, not during pre-deploy:
[volume documentation](https://docs.railway.com/volumes).

For a larger production installation, replacing local upload storage with an
object-storage provider would improve horizontal scaling. That architectural
change is intentionally outside this staging-readiness task.

## Safe staging/demo setup

Public registration is disabled, and the repository has no safe idempotent
initial-admin/demo seed command. `backend/scripts/cleanup_core_database.sql` is
a destructive local cleanup utility and must **not** be used on Railway.

Recommended staging process:

1. Decide on a controlled one-time initial Administrator bootstrap procedure
   before opening staging externally.
2. Keep Administrator credentials private.
3. Through the existing authenticated Admin UI/API, create a dedicated demo
   Owner, Project Manager, architect/consultant, Engineers, and Workers.
4. Create a dedicated demo project and example tasks through normal workflows.
5. Give the external architect only their dedicated consultant credentials.
6. Require the temporary password change on first login.
7. Never copy real customer/project data or expose Super Admin credentials.

The missing initial-admin bootstrap is the only application-data preparation
decision that must be resolved before using a brand-new empty Railway database.
It is not a container or networking blocker.

## Deployment-relevant host audit

- `docker-compose.yml` values using `db`, `localhost:5173`, and
  `localhost:8000` are **LOCAL-ONLY**.
- `frontend/vite.config.ts` localhost and WebSocket targets are **LOCAL-ONLY**
  Vite development fallbacks.
- `mobile_app`'s `127.0.0.1` default is **LOCAL-ONLY** and remains overridable
  through `--dart-define=API_BASE_URL=...`.
- PowerShell live-test and presentation-server localhost values are
  **LOCAL-ONLY**.
- Browser API traffic is configurable through `VITE_API_BASE_URL`.
- Generated backend links are configurable through `BACKEND_URL` and
  `FRONTEND_URL`.
- Database traffic is configurable through `DATABASE_URL`.

The `WEBSOCKET` endpoint constants are placeholders; the current messaging
implementation uses REST polling and does not require a Railway WebSocket URL.

## Manual Railway steps

1. Push this prepared repository to the Git branch intended for staging.
2. Create an empty Railway project/environment.
3. Add Railway PostgreSQL.
4. Create Backend and Frontend services connected to the same repository.
5. Set Backend Root Directory to `/backend`.
6. Add the PostgreSQL `DATABASE_URL` as a reference variable on Backend.
7. Generate the Backend public domain.
8. Set Backend variables listed above, using the actual Backend domain.
9. Set Backend Pre-Deploy Command to `alembic upgrade head`.
10. Set Backend health-check path to `/health`.
11. Attach backend upload volumes at `/app/uploads` and
    `/app/private_uploads`.
12. Set Frontend Root Directory to `/frontend`.
13. Generate the Frontend public domain.
14. Set `VITE_API_BASE_URL` to the Backend public URL plus `/api/v1`.
15. Update Backend `FRONTEND_URL` and `CORS_ORIGINS` with the exact Frontend
    `https://` origin.
16. Set Frontend health-check path to `/healthz`.
17. Review staged changes, then deploy PostgreSQL/Backend before Frontend.
18. Confirm `/health`, `/openapi.json`, `/healthz`, login, refresh-token flow,
    upload persistence, and a React deep-link refresh.
19. Complete the controlled demo-account setup described above.

Railway health checks expect HTTP 200 and use the service's injected `PORT`:
[health-check documentation](https://docs.railway.com/deployments/healthchecks).
