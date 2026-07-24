# AI Voice Foundation

## Configuration

OpenAI is called only by FastAPI. Put the key in `backend/.env`:

```env
OPENAI_API_KEY=your_real_key
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe
OPENAI_ACTION_MODEL=gpt-5.6-luna
```

Never put the key in Flutter, React, source control, API responses, or logs. The
checked-in examples contain placeholders only. If the key is absent, AI routes
return HTTP 503 with a safe configuration message and the application remains
running.

The transcription integration follows OpenAI's current
[speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text).
Structured proposals use the Responses API Pydantic parsing pattern from the
[Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

## Start the backend

After adding the key, rebuild because the official `openai` Python package was
added:

```powershell
docker compose up -d --build backend
```

For local Python development, install `backend/requirements.txt`, run Alembic,
then start Uvicorn from `backend`:

```powershell
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

No new migration is required. The bounded transcription request does not store
raw audio or transcripts. The existing legacy `voice_recordings` table remains
unchanged for workflows that explicitly use it.

## Mobile request flow

1. Flutter records an M4A file locally.
2. On stop, Flutter sends authenticated `multipart/form-data` to
   `POST /api/v1/ai/transcribe` with fields `audio` and `project_id`.
3. The existing Dio JWT interceptor adds the access token.
4. FastAPI checks authentication and project access, validates file type,
   signature, and the 25 MB limit, then calls OpenAI from the backend.
5. Flutter displays the returned transcript in an editable preview.
6. Cancel discards the local draft. Continue sends the edited transcript to
   `POST /api/v1/ai/analyze-command`.

Supported uploads are MP3, MP4, MPEG, MPGA, M4A, WAV, and WebM. The model is
prompted to preserve Arabic, English, mixed construction terminology,
percentages, names, and measurements.

## Current action-analysis boundary

Structured proposal types are prepared for task progress/status, issue and site
report creation, task comments, review submission, and unknown commands.
Deterministic rules currently enforce project consistency, confidence,
percentage bounds, role restrictions, required fields, and clarification when a
task has not been resolved.

Every analysis response returns `canExecute: false`. Confirmation in Flutter is
only confirmation of the preview; it does not call SQL or a mutating domain
endpoint. Existing RBAC, task dependencies, consultant review rules, audit logs,
notifications, and application services remain the source of truth.

## Next implementation step

Implement the first executable rule as a dedicated confirmation endpoint:

1. Resolve `task_reference` only within the selected project and the user's
   authorized task scope.
2. Return candidate tasks when there are zero or multiple matches; never guess.
3. Re-fetch the selected task under a transaction at confirmation time.
4. Re-run RBAC, assignment, dependency, status, progress, and consultant-review
   checks.
5. Call the existing task progress application service/endpoint rather than
   updating SQL directly.
6. Record `source=voice_ai`, transcript/proposal metadata in the existing audit
   system and use the existing notification mechanism.
