# Construction Voice Assistant v2

## Architecture and trust boundary

The mobile client uploads private audio to the authenticated backend. The backend transcribes it, builds a project-isolated context, asks OpenAI for a strict `ConstructionVoiceResult` proposal, validates every referenced task and recipient again, creates editable action drafts, and waits for confirmation. Only `VoiceRulesEngine` can dispatch an explicit handler. Existing task, review, messaging, notification, and audit services remain authoritative.

Spoken content is untrusted data. It cannot select an unknown handler, invent an ID, grant a permission, set an unverified percentage, approve a design change, or claim execution. Original and normalized transcripts are stored separately.

## Intent taxonomy and executable handlers

`VoiceIntent` describes task, worker, issue, design, milestone, communication, review, report, observation, clarification, unsupported, and no-action meanings. Semantic intents are intentionally separate from the smaller `SuggestedActionType` handler allowlist.

Executable handlers currently cover starting a task, updating explicit progress, submitting for review, creating an issue, creating an unverified worker field submission, adding a task note, creating a site-report draft, task/project messaging, owner updates, proposed design-change reports, and consultant review decisions. Unknown handler names fail schema validation.

Risk is assigned by backend policy, not accepted from the model:

- Low: notes, worker evidence, report drafts.
- Medium: start/progress, issues, messages, proposed design changes.
- High: formal review decisions, review submission, and owner updates. Mobile requires detailed acknowledgement.

## Roles

- Workers create traceable claims/evidence only. Their speech never changes official task status or progress. Reports route through the existing responsible-engineer workflow.
- Contractor engineers and project managers retain only their existing project, assignment, discipline, task-state, dependency, and messaging authority.
- Consultants use the configured reviewer and discipline workflow. A spoken review cannot bypass assignment.
- Owners receive authorized updates but gain no mutation permission.
- Administrators are not substituted as actors for another user.

## Context and multilingual handling

`VoiceContextBuilder` supplies only the current project, authenticated actor, visible tasks, visible dependency states, relevant milestones, allowed handlers, and candidate project recipients. The raw Arabic, Levantine Arabic, English, or mixed transcript is preserved. Operational fields and the current UI are English; names, codes, and IDs are never translated.

## Progress, milestones, and design changes

An explicit engineer percentage may be proposed. Measurements are deterministically prevented from becoming percentages. Vague completion language creates a clarification and leaves official progress unchanged. The schema classifies milestone/floor/zone statements, but there is no milestone-completion handler: completion remains in the existing deterministic milestone workflow. Every spoken design change is created as `PROPOSED`; `approved=true` is rejected.

## Evidence

`tasks.voice_evidence_requirements` is JSON configuration such as:

```json
{"minimumPhotos": 3, "views": ["GENERAL", "DETAIL", "DETAIL"]}
```

The backend converts this to deterministic draft requirements. `POST /voice/commands/{id}/evidence` accepts private image evidence. Confirmation is blocked until the configured minimum exists. When a worker confirms the report, those photos become ordinary `FieldSubmissionPhoto` records for engineer review.

## Messaging and routing

The model may select only IDs in `candidateRecipients`. The backend revalidates project membership and messaging policy. Owner updates must target the current project owner only. All message text is previewed in the editable draft and sent only after confirmation. The project-wide broadcast path is not used by default.

## State, concurrency, audit, and errors

Commands follow `UPLOADED → TRANSCRIBING → TRANSCRIBED → ANALYZING → NEEDS_CLARIFICATION/READY_FOR_CONFIRMATION → CONFIRMED → EXECUTING → EXECUTED/PARTIALLY_EXECUTED`, with failure and cancellation branches. Invalid transitions, stale task snapshots, repeated execution, duplicate action IDs, and cross-project IDs are rejected. Upload, analysis, edit, clarification, confirmation, execution, evidence, and domain mutations are audited.

`voice_action_policy.py` centralizes retryable user-facing errors for processing, timeouts, permissions, stale data, dependencies, and evidence. API errors should be logged with a support correlation ID by deployment middleware; stack traces and provider details must never be displayed.

## API

- `POST /api/v1/voice/commands`: upload and analyze audio.
- `GET /api/v1/voice/commands/history`: user history.
- `GET /api/v1/voice/commands/{id}`: authorized detail.
- `PUT /api/v1/voice/commands/{id}/draft-actions/{draftId}`: edit/select a draft.
- `POST /api/v1/voice/commands/{id}/clarifications`: answer a targeted question.
- `POST|GET /api/v1/voice/commands/{id}/evidence`: upload/list pre-confirmation evidence.
- `POST /api/v1/voice/commands/{id}/confirm`: confirm selected drafts; high-risk actions require `detailedConfirmation`.
- `POST /api/v1/voice/commands/{id}/execute`: deterministic execution.
- `POST /api/v1/voice/commands/{id}/cancel`: cancel an unexecuted command.

The existing retry and secure-audio endpoints remain compatible.

## Configuration and deployment

Keep `OPENAI_API_KEY` on the backend. Configure `OPENAI_ANALYSIS_MODEL`, transcription model, timeout, audio size/duration, confidence threshold, retention, and feature flag through environment settings. Apply migrations through revision `a28d1b6f3e57`, validate a single Alembic head, then build React and run Flutter analysis/tests.

## Acceptance examples

- “I am starting the foundation rebar installation today.” → medium-risk start proposal; dependencies and assignment rechecked at execution.
- “Today we installed the bottom reinforcement…” from a Worker → field claim and configured photos; no official progress update.
- “The workers completed … about ten percent” from an Engineer → explicit 10% proposal showing old/new values.
- Ceiling opening conflicts with a duct → design-conflict issue draft; location clarification if absent.
- Electrical routing changed → proposed design-change report and approval clarification; never approved automatically.
- “Send the owner…” → exact owner, preview, high-risk acknowledgement, then send.
- “We finished the first floor.” → milestone/floor intent and targeted clarification; no blanket completion.
