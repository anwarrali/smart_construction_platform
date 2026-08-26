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

Reply phrasing and conversation state add three settings, all with working
defaults and none of them required:

| Setting | Default | What it does |
| --- | --- | --- |
| `VOICE_NATURAL_RESPONSES_ENABLED` | `true` | Phrase answers and questions with the model. `false` pins the deterministic templates, which is also what every provider failure falls back to. |
| `OPENAI_RESPONSE_MODEL` | `OPENAI_RAG_MODEL`, else `gpt-4.1-mini` | The phrasing model. Separate from the analysis model: that one needs strict structured output, this one needs to be fast and cheap enough to run on every reply. |
| `VOICE_CONVERSATION_WINDOW_MINUTES` | `20` | How long a half-finished spoken request stays open for the next utterance to complete it. |

No migration is involved: the answer, the outstanding question and the reply
language are written into the existing `structured_result` and
`provider_metadata` JSONB columns.

## Acceptance examples

- “I am starting the foundation rebar installation today.” → medium-risk start proposal; dependencies and assignment rechecked at execution.
- “Today we installed the bottom reinforcement…” from a Worker → field claim and configured photos; no official progress update.
- “The workers completed … about ten percent” from an Engineer → explicit 10% proposal showing old/new values.
- Ceiling opening conflicts with a duct → design-conflict issue draft; location clarification if absent.
- Electrical routing changed → proposed design-change report and approval clarification; never approved automatically.
- “Send the owner…” → exact owner, preview, high-risk acknowledgement, then send.
- “We finished the first floor.” → milestone/floor intent and targeted clarification; no blanket completion.

## Task identification and ambiguity (v2.1)

An engineer does not know the stored task title, so the system never asks for
one. `services/voice_task_matcher.py` ranks the tasks
`authorized_voice_tasks` already returned against what was actually said, and
returns a *decision* rather than a list: resolved, ambiguous, or nothing.

- **Resolved** — one task scores above `RESOLVE_THRESHOLD` and leads the
  runner-up by `AMBIGUITY_MARGIN`. The draft is targeted automatically and a
  warning is attached below 0.75 so the confirmation step still shows it.
- **Ambiguous** — the top three to five candidates become the options on the
  `target.taskId` clarification. The previous behaviour offered up to fifty
  tasks, which is the "remember the exact name" problem in a dropdown.
- **Nothing** — the most plausible open tasks are still offered, and no action
  is targeted.

Matching is lexical and deterministic, not RAG. The candidate set is one
project's task rows, already authorization-filtered, so an embedding round trip
would add latency and unexplainability to a question the database answers
exactly. RAG remains for unstructured documents.

Bilingual matching works by mapping Arabic, Levantine Arabic and English
surface forms onto shared construction concepts (`CONSTRUCTION_LEXICON`) before
any string comparison, with Arabic orthographic folding (hamza carriers,
ta marbuta, alef maqsura, diacritics, tatweel) and Arabic-Indic digits
normalized first. Floor levels and building/zone labels are extracted from both
languages and a contradicted location is a strong penalty, not a missing bonus.

`GET /api/v1/voice/task-candidates?project_id=&q=` exposes the same ranking for
the "choose another task" path. It ranks only what `authorized_voice_tasks`
returns, so no query string can widen scope.

## Report readiness

`GET /api/v1/voice/report-readiness?project_id=&report_date=` returns the day's
**executed** voice actions in structured form — task, discipline, before/after
state, actor, timestamp — with a `ready` flag. It is the hand-off surface for
the report-generation agent and deliberately carries no PDF, template, or
delivery concern. Unconfirmed drafts never appear: only approved information
becomes project knowledge.

## Latency

`services/voice_metrics.py` times transcription, context building, analysis and
drafting, stores the durations on `provider_metadata.latencyMs`, and logs them
without any transcript content. The React client measures microphone start,
recording length, and total round trip.

Measured on a development machine (Python 3.12), ranking one utterance against
one project:

| tasks | p50 | p95 |
|------:|----:|----:|
| 25 | 1.5 ms | 2.1 ms |
| 100 | 3.6 ms | 4.9 ms |
| 400 | 11.1 ms | 18.5 ms |
| 1000 | 37.6 ms | 59.6 ms |

Task text features are parsed once per distinct string and cached, and the
quadratic string-similarity pass runs only on the top `REFINE_WIDTH` candidates
— it can add at most 0.20 and therefore cannot change which five tasks are
shown. Both are covered by call-count tests rather than wall-clock assertions.

## Realtime

`task_progress_service.update_task_progress` now publishes `TASK_UPDATED`
itself. Previously only the REST endpoint did, so a confirmed voice update and
an engineer's verify-and-apply on a worker submission both changed a task
without telling any open board.

## Web client

React gains a voice capture surface at `project → voice-assistant`
(`features/voice/components/VoiceAssistantPanel.tsx`), previously mobile-only.
It records with `MediaRecorder`, shows a local Web Speech preview while the
engineer talks where the browser supports one — display only, never sent and
never acted on — and falls back silently where it does not. The authoritative
transcript, interpretation and every mutation remain server-side. An in-flight
upload is aborted when a new recording starts, and a failed upload keeps the
audio for retry.

## Read versus write (v2.2)

The pipeline had one exit: build drafts, resolve a target, wait for
confirmation. That is right for "ابدأ المهمة" and wrong for "شو حالة الحفر؟",
and the difference was invisible because both sentences name a task. When the
model correctly proposed *no* action for a question, `build_action_drafts`
manufactured an `ADD_TASK_NOTE` from the raw transcript and then demanded a
task for it — which is how questions became notes and answered with "which task
do you mean?".

`ConstructionVoiceResult` now carries a `request_kind` decided before anything
is proposed:

- **QUESTION** — answered from project data; terminal at `COMPLETED`; nothing to
  confirm.
- **COMMUNICATION** — a message with a recipient, never a task handler.
- **STATEMENT** — reconciled against the record; a stated stoppage on a task
  the database calls complete raises a clarification instead of a note.
- **ACTION** — unchanged: drafts → clarification → confirm → rules engine.

`ACTION` is the default, so anything the model does not positively classify
keeps its existing path and its confirmation step.

`services/voice_query_service.py` answers questions **deterministically** from
`authorized_voice_tasks` and the task graph. The model decides what was asked;
the backend decides what is true. There is no second provider call — a question
costs a few queries, not another round trip — and the model never narrates a
status, so it cannot state a percentage that does not exist. Topics are a
bounded set (`TASK_STATUS`, `TASK_BLOCKERS`, `NEXT_TASK`, `REMAINING_TASKS`,
`PROJECT_PROGRESS`, `OPEN_ISSUES`, `REPORT_READINESS`, `LATEST_SITE_REPORT`, …)
that arbitrary Arabic, English, or mixed phrasing maps onto; adding a phrasing
needs no code change. Adding a genuinely new *kind* of answer does — which is
what `LATEST_SITE_REPORT` and `SITE_REPORTS` are; see v3.1 below.

"Which task do you mean?" is now asked only when a task-level question genuinely
matches more than one task. Project-level questions never ask it.

Progress wording is interpreted semantically: a quantitative fraction ("نص
الشغل") becomes a percentage flagged `approximate`, which the confirmation card
states out loud; a vague amount ("تقريباً كله") yields no percentage at all and
asks instead.

The manufactured fallback draft is gone. Zero proposals plus no answer now
produces one short clarifying question, never an invented mutation.

## Conversation (v2.3)

Three complaints, one root cause each. All three were about the layer *above*
retrieval: the data was right every time.

### Same data, different question

Retrieval and phrasing are now separate steps.
`services/voice_query_service.py` still decides **what is true**, from the same
authorization-scoped rows, and still produces a deterministic sentence per
topic. What changed is that the deterministic sentence became the *fallback*
rather than the answer: `ai/response_composer.py` is given the engineer's own
words plus a **fact pack** — `project_snapshot()`, which is the project's
counts, its completed and open tasks with their state and dates, and its open
issues, plus whatever the topic retrieved — and writes the reply to the question
that was actually asked.

    "شو نسبة تقدم المشروع؟"  → "نسبة تقدم المشروع 45.45%. خلصنا 5 مهام من أصل 8…"
    "كم مهمة خلصت؟"          → "خلصنا 5 مهام لحد هلا."
    "شو المهام اللي ضايلة؟"  → "باقي 3 مهام: TSK-006 …، TSK-007 …، TSK-008 …"

One read of the project serves all three, which is why a new phrasing needs no
new topic and no code change.

The model is a phrasing engine over supplied facts and never a source of facts:
the prompt forbids any number, name, date or status not present in the pack, and
`sanitize_facts()` strips identifiers, confidence, topics and intent names
before anything is sent, so nothing internal can be echoed. Every failure path —
no key, timeout, refusal, empty output — returns the deterministic sentence, so
the worst case is the previous behaviour rather than an error.
`VOICE_NATURAL_RESPONSES_ENABLED=false` pins that behaviour deliberately.

Replies follow the **spoken** language, not the interface's:
`services/voice_language.py` reads the script of the transcript, and the chosen
language travels to the clients as `providerMetadata.replyLanguage` and
`structuredResult.answer.language`.

### A missing field is a question, not an error

An unsaid field used to fail `SuggestedAction`'s schema validation, which fails
the *whole* structured parse — so "بدي أرفع مشكلة عن شغل اليوم" surfaced as "AI
analysis is temporarily unavailable". The schema now keeps only the invariants
that are not about completeness (voice can never record a design change as
approved; an unrecognised review decision is treated as unsaid), and
`services/voice_action_requirements.py` owns what each action cannot execute
without.

Each outstanding field becomes one question, phrased by the composer with the
deterministic wording as its fallback, and answered in the engineer's language:

| Said | Understood | Asked |
| --- | --- | --- |
| "خلصنا نص الشغل" | progress 50%, no task | "فهمت إنك خلصت نص الشغل، بس أي مهمة عم تحكي عنها؟ TSK-006 ولا TSK-007؟" |
| "بدي أرفع مشكلة" | an issue, no problem | "تمام، شو المشكلة اللي بدك تسجلها؟" |
| "I want to report an issue" | an issue, no problem | "…can you tell me what the problem is?" |

One question at a time: answering "which task?" often makes the next field
obvious, so the next question is written only after the answer arrives. The
rules engine still refuses to execute any draft with an outstanding field, so
nothing is lost by asking instead of failing.

**The review card waits.** While anything is missing the command stays in
`NEEDS_CLARIFICATION`, the outstanding question is written into
`structuredResult.answer` as the spoken reply, and the clients render the
question rather than a card reading "Task: unknown, Progress: 50%". Once
everything is known, the reply becomes a one-sentence restatement of what is
about to happen — "رح نحدث نسبة الإنجاز لمهمة TSK-006 — Order electrical
materials لتوصل 50%، ممكن تراجعها وتأكد؟" — above the unchanged review card.

### The answer to a question continues the request

`services/voice_conversation_service.py` treats an unanswered question as what
it already is: a stored command in `NEEDS_CLARIFICATION` whose drafts name the
missing fields. When the next utterance arrives within
`VOICE_CONVERSATION_WINDOW_MINUTES` (default 20) from the same speaker on the
same project, and it proposes nothing of its own, it is tried as the answer.

    "خلصنا نص الشغل."   → asks which task, keeps progress = 50
    "المهمة السادسة."   → TSK-006 — Order electrical materials, 50%, ready to confirm

The pending drafts are *copied forward* onto the new command — one command per
utterance keeps the audio, the transcript and the audit trail aligned — and the
earlier command is cancelled with `closedReason: continued`. A merge can only
ever fill a missing field; it cannot create an action or change one. An
utterance that proposes something of its own is a new instruction and supersedes
the abandoned question instead (`closedReason: superseded`); a question asked
mid-flow is answered and leaves the pending request open.

The interpreting model is told what is outstanding through
`application_context.pendingRequest`, so a two-word reply is read as an answer
rather than as an unclassifiable fragment.

Positional references are resolved by `voice_task_matcher.task_position()` /
`match_by_position()`: "المهمة السادسة", "رقم ٦", "task 6" and "the sixth one"
index the authorized task list in the order the engineer sees it (by task code).
A floor is not a task — "الطابق السادس" resolves to nothing rather than to work.

### What never reaches the engineer

Intent names, topics, action types, field paths, confidence numbers, identifiers
and validation messages stay in the logs and the fact-pack sanitizer. A
user-correctable problem is always a sentence in their language: "ما عرفت أي
مهمة تقصد. احكيلي اسمها أو رقمها." rather than a 422. Only a genuinely technical
failure still surfaces as an error, with the detail logged and a clean message
shown.

## Capabilities (v3)

v2 made the assistant conversational. v3 makes it an *interface to the
platform*: anything the speaker can do through the UI they can ask for in their
own words, and anything they cannot is declined in a sentence.

### The registry, not a phrase list

`services/voice_capabilities.py` describes each operation once — what it does,
who may do it, what it needs, and how people actually ask for it:

```
UPDATE_TASK_SCHEDULE  category=tasks  roles={project_manager}  permission=task.edit
  needs a task, needs dueDate
  "خلّي موعد المهمة السادسة الأسبوع الجاي" · "أجّل مهمة التكييف لبعد أسبوعين"
  · "move the ductwork deadline to 15 September"
```

Four consumers read it and none keeps its own copy: the **prompt** (rendered per
speaker, listing only what that person holds), **draft building** (which asks
for whatever is still unsaid), the **permission pre-check** (which declines in
words), and the **rules engine** (which re-checks everything at execution).
Payload *fields* stay in `ai/action_payload_contract.py`, which the registry
composes with, so a field cannot be named two different things.

Nothing is keyed on wording. The examples teach the model the shape of a
request; mapping the other five hundred phrasings onto the same capability is
what the model is for.

Capabilities added in v3, each bound to the endpoint the web UI already calls:

| Capability | Backend operation | Who |
| --- | --- | --- |
| `UPDATE_TASK_SCHEDULE` | `tasks.update_task` (planned dates) | project manager |
| `UPDATE_TASK_ASSIGNMENT` | `tasks.update_task` (assignees) | project manager |
| `UPDATE_TASK_PRIORITY` | `tasks.update_task` (priority) | project manager |
| `UPDATE_TASK_DETAILS` | `tasks.update_task` (name, description) | project manager |
| `DELETE_TASK` | `tasks.delete_task` | project manager |
| `UPDATE_ISSUE_STATUS` | `issues.update_issue` (status, resolution) | project manager |
| `ASSIGN_ISSUE` | `issues.update_issue` (owner) | project manager |

Voice writes no business logic of its own: it turns speech into the arguments
those functions already take, so every rule inside them — who may reassign,
which statuses accept which change, that resolving needs a note — applies to
voice without being restated.

### Permission is the platform's answer, twice

`is_available()` mirrors the platform's rules (role, project membership,
permission catalogue, structural flags such as *is site engineer*) so the
assistant can decline early and in words:

> "ما عندك صلاحية تعدّل مواعيد المهام."

That is a mirror, never the authority. The rules engine calls the same check
again at execution, and the operation's own service checks a third time. A
capability listed in the registry can still be refused, and that refusal is the
one that counts. The catalogue the model sees is filtered the same way, so it is
never taught to offer something this speaker could not do.

### Spoken values become real ones

The model passes words through; the backend resolves them, because a model that
computes a date is fluent and occasionally a week wrong.

- **Dates** — `services/voice_dates.py` resolves "اليوم", "بكرة", "الأسبوع
  الجاي", "نهاية الشهر", "بعد أسبوعين", "يوم 15", "15 سبتمبر", "next Sunday",
  ISO and numeric forms, against the project calendar. A bare weekday that could
  mean two days resolves to *neither* and offers both. The confirmation card
  shows the resolved day, so a wrong reading is caught before anything is
  written.
- **People** — `services/voice_entity_resolution.py` matches names and roles
  against the project team only, counting how much of a name matched so a full
  name beats a shared first name, and handling the clitics Arabic attaches
  ("لأحمد"). Two equal matches is a question, never a guess. The project owner
  is resolved from the project itself, so "ابعت لصاحب المشروع" never asks who.
- **Issues** — matched by word overlap against the project's own issues, or by
  position ("المشكلة الثانية").
- **Priorities and issue states** — matched against the platform's enums:
  "خطر" is `critical`, "سكّرها" is `closed`.

A person or task identifier that the model supplies is *checked* against the
project, never trusted; anything outside it is dropped and asked about rather
than failing the analysis.

### Failures become explanations

`services/voice_action_errors.py` classifies whatever an existing service raises
into a stable `error_code` and a sentence in the speaker's language. Execution
results now carry three things: `message` (the backend's own English, for logs),
`errorCode`, and `userMessage` — and the clients render only the last.

| Raised | Code | Heard |
| --- | --- | --- |
| 403 from `update_task` | `PERMISSION_DENIED` | "ما عندك صلاحية تعمل هذا التعديل." |
| "At least one authorized recipient is required" | `RECIPIENT_REQUIRED` | "لمين بدك أبعت الرسالة؟" |
| "…outside your authorized project contacts" | `RECIPIENT_NOT_ALLOWED` | "ما بقدر أبعت لهذا الشخص من هذا المشروع." |
| 409 workflow conflict | `WORKFLOW_CONFLICT` | "ما بقدر أعمل هذا حسب وضع المهمة الحالي." |

Success is narrated the same way and *only from a confirmed result* — "تم إرسال
الرسالة لصاحب المشروع." is written after the backend returns, never from the
fact that a request was sent.

### Messaging, end to end

Sending was reaching the messaging service and then failing *after* it: the
audit row written next serialized the action payload with raw `UUID` recipients
into a JSONB column, which raised, took the surrounding request with it, and
left the engineer with a generic error for a message that had in fact been
delivered. `SuggestedActionPayload.as_dict()` now dumps in JSON mode, so
identifiers are strings by the time anything stores them.

The rest of the messaging path is now resolved rather than guessed: the owner
comes from the project, a named person from the team, and a message with nobody
to send it to asks "لمين؟" with the team as options instead of failing
validation at execution.

### Conversation

Three behaviours on top of v2's continuation:

- **Corrections.** "لا، قصدي المهمة الثالثة", "لا، خليها 20 سبتمبر" rewrite the
  proposal already on screen — including one that has reached
  `READY_FOR_CONFIRMATION` — instead of stacking a second one beside it. Only
  the values named in the correction change; everything else is carried
  forward, which is what makes it a correction and not a restart.
- **Interruptions.** A question asked mid-request is answered, and the reply
  ends with what is still outstanding: *"…وبالنسبة للطلب السابق، لسه بحاجة
  أعرف: ممكن تخبرني التاريخ الجديد؟"* The pending request is untouched.
- **Language continuity.** A continuation keeps the language the conversation
  started in, so a two-word Latin-script answer inside an Arabic exchange does
  not flip the assistant into English.

Answers of every kind now complete a pending request: a task, a date, a person,
a percentage, a priority, an issue state, or free text.

### What voice still cannot do

- **Attach a file.** Documents and photos need bytes, which speech does not
  carry. The assistant says so rather than implying it uploaded something;
  evidence photos still go through the existing evidence upload.
- **Anything the speaker's role or permissions do not allow**, by design.
- **Create or edit projects, members, permissions, or schedules wholesale** —
  those are not registered capabilities, so voice declines them rather than
  reaching for an endpoint nobody decided to expose to speech.

### No silent states

An engineer said *"في تأخير في وصول المواد لمهمة اليوم"*, was asked to clarify,
answered *"المواد الكهربائية تأخرت"* — and the screen went blank. Two faults met:

**The answer was recorded and never read.** `_ask_neutral_clarification` asks a
question that belongs to no draft, so there is no field for its answer to go
into; `answer_clarification` stored the words and stopped. The command kept its
`NEEDS_CLARIFICATION` status, its only clarification now had an answer, and its
reply was still the *previous* question.

**The client then had nothing to render.** Its three cards were gated on: an
unanswered clarification (gone), a complete proposal (never existed), and an
answer *whose gate excluded `NEEDS_CLARIFICATION`* — a status the command keeps
while it waits. Three cards, all off.

The fix has three parts:

- **Re-interpretation.** `answer_clarification` now reports whether the answer
  still needs interpreting — true whenever the question had no draft behind it,
  and also when what was said does not fit the field that was asked about. The
  clarification endpoint then re-runs the pipeline on the request and the
  answer *together*, exactly as if they had been said in one breath, with the
  question carried in `pendingRequest` so a two-word reply reads as a reply.
  `NEEDS_CLARIFICATION → COMPLETED` became a legal transition, since a clarified
  request may turn out to be a question.
- **An invariant, not a patch.** `renders_something()` states what a client can
  show — a question, a proposal, or a sentence — and `ensure_visible_state()`
  adds a plain fallback when none of the three exists. `interpret_command` runs
  it on *every* exit, including exceptional ones. A provider outage during
  re-interpretation produces "ما قدرت أكمل الطلب حالياً. جرّب تحكيلي مرة تانية."
  rather than a stack trace or a blank card.
- **Render precedence in the client.** The Flutter screen gates on
  `isAsking` — is a question actually on screen — rather than on the command's
  status, shows the reply whenever there is one, and has a last-resort line for
  a state that should never arrive. The clarification card shows a spinner and
  disables its buttons while an answer is being interpreted.

Two things the same investigation turned up and fixed: an abandoned open
question used to be fed to the model for twenty minutes, colouring unrelated
requests (it is now carried only into the answer that follows it); and an
unresolvable answer used to raise a 422 where re-reading the request in context
is both kinder and more likely to be right.

## Acceptance fixes (v3.1)

Five defects from a device-level acceptance pass against real project data.
Each one is the same shape: a request that had nowhere correct to go, so it
went somewhere plausible instead.

### A site report is a document, not a summary

"اعطيني آخر تقرير موقع" came back as a project summary. There was no query
topic for a *filed* report, and the two nearest ones answer different
questions: `PROJECT_PROGRESS` is where the project stands, `REPORT_READINESS`
is whether there is enough confirmed work to write a report at all. The model
had to pick one of them, and both are truthful answers to a question nobody
asked.

`LATEST_SITE_REPORT` and `SITE_REPORTS` now exist. They read the `site_reports`
table through `authorized_site_reports`, which mirrors
`api/site_reports.list_site_reports` exactly — an Owner still sees only what
has been submitted or approved, a Consultant Engineer still sees project-wide
reports plus their own discipline's. The answer always names the record: its
date, who filed it, and its review state, none of which a project summary
carries. The prompt lists the five topics side by side with what separates
them, so the distinction is taught rather than inferred.

### A suspicion is not a fact

"أتوقع إنه في مشكلة في المشروع" was classified `STATEMENT` — an assertion about
the world — and the assistant offered to record it. The engineer had to say
"I'm asking you" before it would look.

Two changes, both narrow. The prompt now separates a first-hand report ("المواد
ما وصلت") from a belief offered for checking ("أتوقع…", "أعتقد…", "بظن…",
"I think…"), and says explicitly that a belief is a question about the record.
Behind it, `voice_router` reads the transcript for a hedge and answers from the
record instead of asking what to do about it — but *only* for a `STATEMENT`
that proposed no action, so "أتوقع نخلص بكرة، سجّل ملاحظة" is still the note it
plainly is. A hedge never creates a question; it only stops a suspicion from
being treated as something to write down.

### A person is an identity, a question, or an explanation

Two problems, one root. Assignment resolved a spoken name against every project
member, including people whose project role cannot hold work — so a draft
reached the review card looking correct and failed at execution with the tasks
API's own sentence. And a name that matched nobody produced a bare "مين بدك
يكون مسؤول عنها؟", which tells an engineer who has just said a name that the
assistant was not listening.

`assignable_people` now applies the tasks API's own eligibility rule (imported
from it, not restated) at drafting, at clarification, at the follow-up merge and
again in the rules engine. And when a spoken name matches nobody available, the
question says which name: *"ما لقيت حدا اسمه «أحمد» ضمن أعضاء المشروع اللي
بيقدروا يستلموا هاي المهمة. مين بدك يكون مسؤول عنها؟"* The name is read out of
the utterance conservatively — an Arabic ل- clitic or an English "to"/"for" —
and when it cannot be read, the wording names no name rather than inventing one.

### A failure says what failed

`CLARIFICATION_REQUIRED` used to say "لسه في معلومة ناقصة", which is true of
every incomplete draft and useful for none of them. The outstanding field
already has a question written for it, so the refusal now says those words:
*"ما نفذت الطلب لأنه لسه بدي أعرف: أي مهمة تقصد؟"*

`VoiceActionError` carries a code and both sentences from wherever the reason
was known, so a precise refusal is never re-derived from its own English. Twelve
more codes classify sentences the task, issue and assignment services already
raise — an unresolved target, an ineligible assignee, a missing date, a locked
progress value, a review that is not due — each with a sentence saying what
happened and what to do next. Anything unmatched still degrades to
`ACTION_FAILED`; nothing guesses a reason.

### An answered question stays answered

The loop. "حدثلي المهمة السادسة وخلي تاريخها 19 سبتمبر" would ask for the date,
accept it, and then ask which task — round and round.

The cause was in how the *answer* arrived. `is_possible_answer` treats any
utterance that proposes an action as a new request, which is right for a new
instruction and wrong for the model's other way of answering a question:
restating the whole action with the missing piece filled in. Read as new, that
answer had a date and no task, so it asked for the task the pending request had
already resolved — and superseded that request on the way past.

`continues_pending` recognises it, under three conditions that all have to
hold: every proposed handler is one the pending request is already waiting on,
none of them names a target of its own, and the utterance does not name a
different task from the one already resolved. The merge also reads values out
of the re-proposed payload, not only out of the loose sentence. A genuinely new
request — a different operation, or the same one about a different task — is
still a new request.

Two smaller things from the same trace: the prompt's `"حدث المهمة" →
UPDATE_TASK_PROGRESS` example was pinning a sentence that named a date to a
progress update (the bare verb still means progress; a sentence that says what
to change is decided by what it says), and the neutral "شو بدك أعمل
بهالمعلومة؟" repeated word for word because "have I asked this already?" was
asked of one recording rather than of the conversation.

## Voice state recovery

`uploading` and `transcribing` were the only statuses with no primary action, no
delete and no retry, so a request that never returned left no controls and
reloading the page was the only way out. Both states now offer
`VoiceViewModel.abandon()`, which supersedes the attempt and returns to idle.
Because abandoning cannot cancel an HTTP request already in flight, every async
completion compares the attempt token it started with and drops itself if
superseded — otherwise a late response would drag the engineer back into a
result for a recording they had discarded. Nothing is confirmed at that point,
so nothing has been written and abandoning is always safe.
