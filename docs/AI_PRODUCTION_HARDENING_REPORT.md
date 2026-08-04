# AI production hardening report

## Architecture audited

The platform is a Flutter field client, FastAPI/SQLAlchemy/PostgreSQL backend,
React/Vite web client, and Alembic migration chain. Existing AI voice handling
already separated transcription, strict structured interpretation, editable
drafts/clarifications, confirmation, deterministic rules, domain services,
notifications, and audit. IFC processing already parsed hierarchy/elements,
generated geometry, compared revisions, and persisted coordination insights.

The audit found that the documented trust boundary was generally sound, but
four production gaps remained: there was no authenticated transcript-only API
for deterministic mobile simulations, no immutable business-action history or
compensating revert API, IFC acceptance lacked direct project/task/location
compatibility checks, and normal changes did not emit a durable validation
event. Mobile retries also generated new request IDs and the HTTP timeout could
expire before backend AI processing.

## Implemented hardening

- Added append-only `AIActionVersion`, `DomainEvent`, and `AIProviderCall`
  persistence with project/actor/correlation indexes and idempotency constraints.
- Added authenticated, feature-gated `POST /api/v1/voice/commands/from-transcript`.
  It derives identity and candidate context server-side, invokes the same strict
  analysis/draft path, retains failed inputs, and records provider latency.
- Added AI action list/detail/revert/revert-last APIs with RBAC. Only an eligible
  latest task-progress action is automatically compensated. Other actions return
  manual-review or dependency/staleness reasons. A revert is a new immutable
  action and audit event.
- Added PM-only, high-risk voice task creation through the existing task service.
- Added deterministic IFC identity, project type, floor, room, task element-class,
  and major revision-drift rules. Findings are persistent, evidence-backed
  `AIInsight` records. Any compatibility finding results in
  `READY_WITH_WARNINGS`, not silent plain success.
- Added deterministic correlation for an IFC wall removal that may implement an
  approved wall-removal design change; it remains an informational finding for
  engineering confirmation.
- Added durable rules-first domain events for task creation/progress, worker
  field submissions, consultant review completion, IFC processing, and AI
  reverts. Cheap rules run synchronously and the table can later be consumed by
  a queue without changing producers.
- Added persistent event findings for task status/progress/date conflicts,
  worker completion claims before task start, and current IFC class mismatches.
- Added web API/types for action history and revert operations.
- Kept one mobile idempotency key per recording, increased voice response timeout
  to 120 seconds, limited cleartext LAN traffic to Android debug builds, and
  added an opt-in development diagnostics screen. It never fakes recording or
  downstream success.

## Migration

`e32a1b4c5d67_ai_governance_events.py` adds:

- `ai_action_versions`
- `domain_events`
- `ai_provider_calls`

It is additive, has a downgrade, and preserves all existing project data.

## Verification evidence (2026-08-03)

| Suite | Result | Actual output |
|---|---|---|
| Alembic heads/upgrade/current | PASS | Single head/current `e32a1b4c5d67` |
| Backend pytest | PASS | 166 passed, 10 warnings |
| React production build | PASS | 2,848 modules transformed; build completed |
| Flutter analyze | PASS | No issues found |
| Flutter tests | PASS | 10 passed |
| Live OpenAI smoke test | NOT EXECUTED | No live provider credential was used; automated provider behavior is mocked |
| Physical Android microphone/voice | NOT EXECUTED | Explicitly reserved for a real physical phone |
| Android debug APK build | FAIL / INCONCLUSIVE | Executed twice in the CI image; Gradle produced no result before 2-minute and 5.5-minute timeouts, so no APK is claimed |

Warnings are dependency/deprecation and web bundle-size warnings; no test failure
is hidden. The Compose bind-mounted combined Flutter helper timed out without a
result; direct runs in the same built Flutter CI image passed analysis and tests.

## Remaining boundaries

- Automatic reversal is intentionally limited to safe, latest task-progress
  compensation. Created issues, messages, design changes, approvals, and review
  decisions require manual domain review.
- Semantic taxonomy values without a controlled domain handler remain
  non-executable proposals/clarifications. This is safer than inventing a new
  mutation path.
- Near-real-time rules run in-process. `domain_events` is ready for a worker/job
  queue when load requires asynchronous semantic analysis.
- The current web bundle is large and should be code-split separately; this is
  not an AI correctness blocker.
- A real phone, reachable backend host, Android runtime permission prompt, and
  actual acoustic environment are still required for the final microphone test.

## Physical-phone procedure

1. Start PostgreSQL/backend and confirm `http://COMPUTER_LAN_IP:8000/health`
   from the phone browser while both devices are on the same trusted network.
2. Enable `VOICE_FEATURE_ENABLED=true` and configure the backend-only OpenAI key.
   Enable `VOICE_TRANSCRIPT_SIMULATION_ENABLED` only in a non-production test
   environment.
3. Build a debug APK with
   `--dart-define=API_BASE_URL=http://COMPUTER_LAN_IP:8000/api/v1` and optionally
   `--dart-define=ENABLE_AI_DIAGNOSTICS=true`. Release builds require HTTPS.
4. Install the APK, sign in, select a project, open `/dev/ai-diagnostics`, and
   verify API, authentication, microphone permission, AAC/M4A format, and timeout.
5. Open Voice, grant microphone permission, record a short update, stop, play it
   back, upload, and observe transcription → analysis → clarification/draft →
   confirmation → deterministic execution.
6. Verify the corresponding task/report/review on web, notification delivery,
   audit log, `GET /api/v1/ai/actions`, and any AI Intelligence finding.
7. Repeat the same confirmed request ID (or simulate a network retry) and verify
   only one command/action exists.
8. For a safe progress action, test revert and verify a second compensating
   history record; do not expect destructive deletion of the original history.
