# AI Voice Reporting and Task Updates

## Architecture and trust boundary

The production workflow is:

`audio → authenticated upload → transcription → strict AI interpretation → editable drafts/clarification → explicit confirmation → deterministic Rules Engine → domain services → audit/notifications`

The OpenAI integration never writes project data. It returns proposals validated
by Pydantic. `VoiceRulesEngine` reloads every target, checks current identity,
account state, project membership, task scope, role, assignment, status,
dependencies, review requirements, confidence, optimistic version, and stale
task snapshots. It then invokes existing task, issue, site-report, messaging, or
field-evidence services from a fixed action allowlist.

Transcript text is untrusted content. Spoken prompt-injection instructions have
no authority and cannot select an operation outside the structured schema.

## Worker versus engineer behavior

- A Worker voice report can only create a `FieldSubmission` in `SUBMITTED`.
  Completion and percentages remain evidence claims. The task is unchanged.
- The assigned Engineer receives a notification and can verify evidence only,
  verify and explicitly apply a suggested progress update, or reject with a
  reason. Verify-and-apply shows old/new task values and requires a second
  confirmation. It uses the normal task progress policy in one transaction.
- An authorized Main Contractor Engineer may prepare task start, progress,
  review submission, note, issue/blocker, site-report draft, and message actions.
  Nothing executes before confirmation.
- Explicit completion proposes 100% and Consultant review where required.
  Reviewed work never goes directly to `DONE`; the existing Consultant workflow
  remains authoritative.
- Project Managers receive only permissions already present in the normal task
  services. Owners and administrators receive no new mutation permissions.

## Configuration

Set these values only on the FastAPI server:

```env
VOICE_FEATURE_ENABLED=true
OPENAI_API_KEY=
OPENAI_TRANSCRIPTION_MODEL=gpt-transcribe
OPENAI_ANALYSIS_MODEL=gpt-5.6-luna
OPENAI_TIMEOUT_SECONDS=60
VOICE_MAX_FILE_MB=25
VOICE_MAX_DURATION_SECONDS=180
VOICE_AUDIO_RETENTION_DAYS=30
VOICE_MIN_EXECUTION_CONFIDENCE=0.80
```

Startup fails with a clear configuration error when voice is enabled without a
key. The key is never sent to React or Flutter and is not included in provider
errors, metadata, logs, or audit details. Provider calls use a finite timeout
and two SDK retries for safe transient failures.

## Persistence

Migration `y26b9f4d1c35_voice_command_workflow.py` extends the durable
`voice_analyses` command record and adds:

- `voice_action_drafts`: independent editable actions, confidence, missing
  fields, warnings, target snapshot, selection, and execution state.
- `voice_clarifications`: one targeted question/answer at a time.
- `voice_execution_logs`: actor, before/after state, result, and safe error.

The existing `FieldSubmission`, `FieldSubmissionPhoto`, `Attachment`,
`Notification`, and `AuditLog` entities are reused. Audio is held in protected
file storage, not a normal database blob. User/idempotency uniqueness, row
versions, target snapshots, row locks, and execution states prevent duplicate
or stale execution.

## State machine

`UPLOADED → TRANSCRIBING → TRANSCRIBED → ANALYZING`

Analysis then reaches `NEEDS_CLARIFICATION` or `READY_FOR_CONFIRMATION`.
Confirmation and execution proceed through:

`READY_FOR_CONFIRMATION → CONFIRMED → EXECUTING → EXECUTED`

Individual failures produce `PARTIALLY_EXECUTED`. Safe provider failures reach
`FAILED` and may be retried from retained audio. A command may reach
`CANCELLED` only before execution. Invalid transitions return HTTP 409.

## API

All routes are under `/api/v1`, require JWT authentication, and enforce project
isolation.

- `POST /voice/commands` — multipart upload with `project_id`, optional
  `task_id`, duration, idempotency key, and audio.
- `GET /voice/commands/history`
- `GET /voice/commands/{id}`
- `PUT /voice/commands/{id}/draft-actions/{draft_id}`
- `POST /voice/commands/{id}/clarifications`
- `POST /voice/commands/{id}/confirm`
- `POST /voice/commands/{id}/execute`
- `POST /voice/commands/{id}/cancel`
- `GET /ai/voice-analyses/{id}/audio` — protected retained audio.
- `GET /field-submissions/pending`
- `PUT /field-submissions/{id}/verify`
- `PUT /field-submissions/{id}/verify-and-apply`
- `PUT /field-submissions/{id}/reject`

Example upload:

```bash
curl -X POST "$API/api/v1/voice/commands" \
  -H "Authorization: Bearer $TOKEN" \
  -F "project_id=$PROJECT_ID" \
  -F "task_id=$TASK_ID" \
  -F "duration_seconds=24" \
  -F "idempotency_key=mobile-2026-07-30-001" \
  -F "audio=@site-update.m4a;type=audio/mp4"
```

Example strict provider proposal (simplified):

```json
{
  "summary": "بدأت تمديدات الكهرباء في الطابق الثاني",
  "detectedTask": {
    "taskId": "an-id-from-the-authorized-candidate-list",
    "taskTitle": "Electrical rough-in",
    "confidence": 0.94
  },
  "progress": {
    "mentioned": false,
    "percentage": null,
    "confidence": 1.0
  },
  "discipline": {"value": "electrical", "confidence": 0.98},
  "location": {"text": "الطابق الثاني"},
  "workCompleted": [],
  "problems": [],
  "materials": [],
  "suggestedActions": [{
    "type": "START_TASK",
    "reason": "Explicit start statement",
    "targetId": "an-id-from-the-authorized-candidate-list",
    "payload": {},
    "confidence": 0.94
  }]
}
```

Unknown fields are rejected. IDs not present in the authorization-filtered
candidate list are rejected before a draft is stored.

## Client UX

Flutter provides recording, timer, pause/resume, cancellation, upload and
processing states, playback, Arabic/English targeted clarification, editable
independent actions, and confirm-then-execute. The Worker outcome remains a
report sent for Engineer review.

React adds `Project → Voice Reports` for execution-side Engineers. It provides
pending reports, worker/task filtering, protected audio, transcript and AI
summary, photos, current/suggested task values, warnings, and the three review
decisions.

## Errors, security, and cost control

Clients receive safe messages for invalid audio, empty speech, timeout,
temporary provider failure, permission loss, stale task state, and validation
failure. Provider response bodies and stack traces are not exposed.

Uploads are bounded by type, extension, signature, size, and reported duration;
generated storage keys avoid trusting filenames. AI context contains only
authorized relevant tasks and prefers the open task. Transcription is persisted
and reused on retry; confirmation does not retranscribe. Prompts are versioned,
focused, and do not include project history or secrets.

Audio retention is configuration-driven. A deployment scheduler should remove
expired, unreferenced audio only after the configured period and must preserve
audio still required by active review or audit policy.

## Local development and tests

```powershell
cd backend
python -m pip install -r requirements.txt
python -m pip install pytest
alembic upgrade head
alembic heads
python -m pytest -q

cd ../frontend
npm run build

cd ../mobile_app
flutter analyze
flutter test
```

External OpenAI requests are mocked in automated tests. Never put a real API key
in an example file or test fixture.
