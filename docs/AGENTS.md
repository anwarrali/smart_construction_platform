# The five project agents

Five bounded analysts over data the platform already holds. Each reads through
the Phase 5 tool layer, reasons deterministically, and produces findings stored
as `AIInsight` — the record the review queue, the severity filters, the
promotion endpoints and the AI Intelligence page already work against.

No agent writes project data. No agent decides an authorization question.

## Why these are analysts, not autonomous actors

An agent that could change the project would need its own authorization story,
its own audit trail and its own confirmation path — three things the platform
already has, attached to the voice command lifecycle. Duplicating them for
agents would have produced a second way to change a project, governed by
different rules, which is the outcome Phase 5 and 6 both forbid.

So agents produce findings. Acting on one is a person's move, through
`/ai-intelligence/insights/{id}/create-issue` or `/create-task`, which require
`ai.promote_insight` and go through the services the web UI calls.

## The five

| Agent | Responsibility | Permission | Tools |
| --- | --- | --- | --- |
| **Site Report** | Delays, recurring problems, missing detail, progress conflicting with the task record | `site_report.submit` | `get_site_reports`, `get_site_report`, `get_tasks`, `get_issues`, `get_project_status` |
| **Document Consistency** | Establish which documents are related, then check those | `task.view` | `search_documents`, `get_document`, `query_project_knowledge` |
| **Revision Impact** | What a model revision or design change may affect, with the link as evidence | `ifc.view` | `analyze_ifc`, `query_ifc`, `get_design_changes`, `get_tasks`, `search_documents` |
| **RFI** | Unanswered and overdue requests, recurring clarification areas | `design_change.propose` | `get_design_changes`, `get_project_users`, `search_documents`, `query_project_knowledge` |
| **Schedule Risk** | Overdue, stalled, blocked and undated work | `schedule.view` | `get_tasks`, `get_project_status`, `get_site_reports` |

### There is no RFI entity in this platform

`docs/NOTIFICATIONS.md` records the decision: the flow where one discipline
raises something another must review and respond to is **DesignChange**, so
that is what the RFI Agent reads. Its findings say so in their own text rather
than letting a reader assume an RFI table exists. Building a separate RFI model
was considered and rejected as inventing a capability the platform had
deliberately not built.

## Two containments

**The tool runtime** stops an agent reading what its *caller* may not read.
Every call goes through `call_tool`, which validates arguments, then project
access, then the tool's permission, before any handler runs.

**The tool grant** stops an agent calling a tool it was not given, even when
the caller could call that tool directly. The Schedule Risk Agent holds no
document tools, so it cannot read a contract however it is prompted. This is a
hard gate in `AgentContext.call`, not advice in a prompt.

An agent has no database session for project data. Everything arrives through
granted tools, and every call is recorded on the run for review.

## Claims, and what an agent may assert

The distinction the layer exists to enforce. A finding states what *kind* of
claim it is, and confidence is capped accordingly:

| Certainty | Meaning | Max confidence |
| --- | --- | --- |
| `FACT` | Read directly from a record | 1.0 |
| `DETECTED` | A rule fired on real data | 0.9 |
| `INFERRED` | A conclusion that could be wrong | 0.7 |
| `RECOMMENDATION` | A suggested next step, never performed | 0.7 |
| `UNCERTAIN` | The agent looked and could not tell | 0.3 |

Two rules are enforced in `AgentFinding.__post_init__` rather than by
convention:

- **A claim that is not `UNCERTAIN` must carry evidence.** An agent cannot
  assert something it cannot show.
- **Confidence cannot exceed its certainty's ceiling.** An inference drawn from
  project data is never as certain as a value read out of a row, and Phase 8
  keys notification policy off these numbers.

`UNCERTAIN` is the one kind allowed without evidence, because "nothing found"
and "could not look" are different answers and a reader deciding whether to
check personally needs to know which one they have.

## Output

Findings become `AIInsight` rows carrying: type, category `AGENT_FINDING`,
severity, confidence, title, description, `reason`, `recommended_action`,
`potential_impact`, affected entities, related task and issue ids, and
`source_engine` naming which agent produced it. `evidence_json` holds the
certainty, the claims with their source records, and whether human
confirmation is required.

Sources are registered through `ai_traceability_service.register_insight_source`,
giving citations and stale-insight invalidation for free.

Re-running updates a finding in place rather than duplicating it, keyed on what
the finding is *about* rather than its wording. A finding a person has already
resolved is left alone.

## Agent-to-agent

Agents do not call each other. They share the finding table: one agent's output
is another's potential input on a later run. Orchestration between them is
Phase 7 work, and building it here would have coupled five independent analysts
into one pipeline before there was a reason to.

## Voice

No second capability registry. Voice answers questions and proposes actions
through `voice_capabilities`; agents produce findings. The shared substrate is
the tool layer and `AIInsight`, exactly as Phase 5 established. Voice is
untouched by this phase.

## Proactive-compatible, not proactive

Each agent declares `subscribes_to` — the domain events that should eventually
wake it. Every declared event is one `domain_event_dispatcher.IMPORTANT_EVENTS`
already emits, asserted by test, so no subscription is dead wiring.

**Nothing is wired to the dispatcher in Phase 6.** Agents run when asked, via
`POST /projects/{id}/agents/{name}/run`. Making them run automatically is
Phase 8, and the declarations are what that phase will read.

| Agent | Wakes on |
| --- | --- |
| Site Report | `FIELD_SUBMISSION_CREATED`, `FIELD_SUBMISSION_VERIFIED` |
| Document Consistency | `DOCUMENT_UPLOADED` |
| Revision Impact | `IFC_UPLOADED`, `IFC_REVISION_CREATED`, `DESIGN_CHANGE_CREATED` |
| RFI | `DESIGN_CHANGE_CREATED`, `CONSULTANT_REVIEW_COMPLETED` |
| Schedule Risk | `TASK_UPDATED`, `TASK_PROGRESS_CHANGED`, `TASK_COMPLETED` |

## What is not here

- **No language model.** Every finding is a deterministic rule over tool
  results, so each one can name the records it fired on. LLM interpretation
  layered *above* these findings is Phase 7; it would sit on top, not replace
  them.
- **No cross-document contradiction detection.** The Document Consistency Agent
  establishes relationships and retrieves requirements with citations, but
  comparing two passages for contradiction is not implemented, and it says so
  in the finding rather than implying it did.
- **No agent-initiated writes**, by design.
- **No scheduling recomputation.** `cpm_service` remains the authority; the
  Schedule Risk Agent reads task state and does not recompute dates.

## Orchestration (Phase 7)

`orchestrate()` runs a set of agents as one governed pass: it decides which
should run, runs them one at a time, isolates each from the others, and records
what happened. It does **not** chain agents, feed one's output into another's
input, or run anything in the background.

### Isolation, twice

`run_agent` catches its own analysis failure *and*, separately, its persist
failure — storing is a different failure domain from analysing, and an agent
that reasoned correctly then hit a database problem must not take the pass down
with it. `orchestrate` catches anything that still escapes. One agent failing
leaves every other agent's results intact and reported.

The response separates **ran / skipped / failed**. A skip is not a failure: an
agent the caller may not run, or one that just ran, is a normal outcome, and
conflating the two would make a healthy pass look broken.

### Run records

`agent_runs` records which agent ran, what triggered it, whose authority it
used, which tools it called, what it produced, its status and its duration.
Two things this exists for that findings alone cannot give:

- **An agent that ran and found nothing** leaves no `AIInsight`, and is
  otherwise indistinguishable from an agent that never ran.
- **"Why is this in my queue?"** — the first question asked about a finding
  nobody requested — is answered by `trigger_type` and `trigger_reason`.

A preview pass (`persist=false`) records nothing: it changed nothing, and a log
full of previews would bury the runs that mattered.

### Event subscriptions — architecture, not execution

`subscriptions.py` resolves declarations in both directions and decides whether
a matched agent should actually run. **Nothing executes anything**: there is no
scheduler, no worker, no dispatcher hook. A test asserts the dispatcher
contains no agent wiring, so turning proactive analysis on stays a deliberate
Phase 8 decision rather than something that drifts in.

`decide()` separates "subscribes to this event" from "should run now", because
an agent can match an event and still be skipped — the caller may lack its
permission, or the same agent may have run minutes ago. Event-triggered runs
have a **10-minute cooldown per agent per project**: ten documents uploaded in
a minute is one action by a person, not ten analyses. Manual runs ignore it —
somebody asking for analysis has a reason.

`orchestrate_for_event()` is the entry point Phase 8 will call. It exists and
is tested now so that enabling proactive analysis is a matter of calling it
rather than designing it.

### Controlled agent-to-agent

Agents still never call each other. Where one genuinely needs another's
conclusions, it reads them through the `get_findings` tool — the same
authorization as the review queue, gated on `ai.view_insights`, and only if
that agent was granted the tool. Two agents hold it: **Revision Impact**
(existing IFC findings bear on impact) and **Schedule Risk** (the Site Report
Agent's recorded delays bear on schedule risk).

The Schedule Risk Agent uses it to report when site reports record delays that
the schedule does not reflect — an inference, labelled as one, citing the other
agent's findings as `AI_INSIGHT` evidence.

## The Organization / RBAC redesign (done)

Phase 7 deferred this and recorded what it would need. It has since been
implemented — see [RBAC.md](RBAC.md) and
[CONSULTING_OFFICE_REDESIGN.md](CONSULTING_OFFICE_REDESIGN.md). What the note
predicted held up: **no agent, orchestrator, tool or knowledge-routing decision
keyed on a role**, so the redesign changed configuration and two foreign keys
rather than agent code. Not one line of `analyzers.py`, `orchestrator.py`,
`runtime.py` or the tool registry was touched.

What changed around the agents:

| Change | Effect here |
| --- | --- |
| `UserRole` / `EngineerDiscipline` enums replaced by `roles` / `disciplines` tables | An agent's `permission_code` now resolves against a role an office configured. No agent knows this happened. |
| `ifc.view` became enforcing | `can_ifc` used to hold a private role dict, so the Revision Impact Agent's declared permission governed nothing. It does now. |
| Discipline became many-to-many, with an IFC mapping | `Discipline.ifc_disciplines` joins the organization vocabulary to the IFC one, so a finding tagged `PLUMBING` can be routed to somebody scoped to `mep`. The two were unrelated before. |
| Workers stopped being users | The Site Report Agent reads the same evidence; the author is a Site Engineer. |
| External participants exist | Agent findings are internal review material and are never notified to an outside party. |

The analysis principal is unchanged: an event-triggered run borrows the
project's assigned Project Manager's authority, and a project without one is
skipped rather than analysed with more power. That reasoning survives the
redesign intact — and improves, because Project Manager is now a configurable
role, so an office that concentrates authority in a Technical Director can say
so without the agents changing.

## Autonomous detection (Phase 8)

Analysis that starts because something happened, rather than because someone
clicked. `emit_domain_event` calls `process_event` synchronously, so the hook is
inline — no worker, no queue, no scheduler — and it is wrapped so a failure in
analysis can never fail the upload or task update that triggered it. Secondary
products do not break primary ones.

**Off by default.** `AGENT_AUTO_ANALYSIS_ENABLED` defaults to false. Proactive
analysis writes into people's notification queues, and switching that on is an
operator's decision rather than a deployment default.

### Whose authority does an automatic run use?

The question Phase 7 left open. A run started by a person borrows that person's
permissions; a run started by an event has no person. Three answers were
considered:

| Option | Verdict |
| --- | --- |
| The actor who caused the event | **Rejected.** A worker filing evidence has worker-level visibility, so the Site Report Agent would see almost nothing and report "analysed, nothing found" — under-detection presented as a clean bill of health. |
| A new system superuser | **Rejected.** The only principal whose reach nobody granted, carrying authority no real person holds. |
| The project's assigned Project Manager | **Chosen.** Accountable for the project, the recipient of the findings, and already holding the visibility the agents need — a real authority a real administrator granted. |

An automatic run therefore can never read anything a real person could not. A
project with **no active assigned manager is skipped**, explicitly: the absence
of an accountable person is a reason not to analyse, never a reason to analyse
with more power. Attribution stays honest — the run is recorded as
`EVENT`-triggered with the event id, so the log says the system started it on
that person's authority rather than implying they asked.

### Which findings reach a person

Recording and notifying are separate decisions. Every finding is stored and
reviewable; only some interrupt somebody.

| Band | Condition | Result |
| --- | --- | --- |
| `URGENT` | confidence ≥ 0.85 **and** severity HIGH/CRITICAL | Notification, `IMPORTANT`, requires action |
| `REVIEW_RECOMMENDED` | confidence ≥ 0.6, or any recommendation | Notification, normal priority |
| `INFORMATIONAL` | confidence < 0.6, or `UNCERTAIN` | **Stored, not pushed** |

Two deliberate consequences. A confident finding about something trivial is
still trivial, so severity and confidence must *both* qualify for urgency. And
an `UNCERTAIN` finding is never pushed — turning "I could not tell" into an
alert is how a channel loses its credibility.

Notifications carry what was detected, where, severity, confidence, how many
source records back it, which agent found it, and the suggested next step —
because a notification saying only "an issue was detected" makes the reader
open the app to find out whether it mattered.

### Not being told twice

One notification per finding, ever, via a `dedupe_key` on the insight id.
Re-analysis refreshes a finding in place; it does not re-announce it. A finding
whose status is `RESOLVED`, `DISMISSED`, `FALSE_POSITIVE` or `ACTIONED` never
notifies again — being told twice about something you dismissed is how people
learn to ignore the channel.

### Still nothing is done

Automatic analysis produces findings with status `NEW` and no applied entity.
Acting on one remains a person's move through the existing promotion path.
