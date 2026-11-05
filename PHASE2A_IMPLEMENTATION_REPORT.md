# Phase 2A implementation report

Date: 2026-11-05. Branch: `codex/phase2a-ai-reliability-correctness`.
Starting branch/revision: clean `main`, `200c06f5e18bc7717016c7f7681d4de02a3d071f`.
Isolated worktree: `/workspace/construction-phase2a`; original checkout `/tmp/construction-ai-audit` remains unchanged. No merge, push, deployment or production data/configuration changes.

## Baseline verification

Fetched origin before creating the worktree. Remote main still matched the November 4 audit revision. Compared source against the saved gap analysis, roadmap and probe evidence. Reliability improvements `fe489dc` and `0a82f53` are already ancestors of main and were not blindly reimplemented. `codex/phase01-reliability-audit` is absent from fetched refs; its exact fix set/integration cannot be verified.

New pre-fix regression tests reproduced six failures and one supported-answer pass against the baseline: delay negation/masked fields, unsupported numeric/non-numeric answers, invalid citations and unstable identities. Exact logs are retained in the verification package. This phase changes implementation; it does not repeat the general audit.

## Changes by finding

### G01 — execution ownership and stale publication

Root cause: completion/heartbeat/failure updated job IDs without matching ownership; nested domain sessions committed without checking the lease. A maintenance heartbeat could keep a blocked handler alive indefinitely.

- `backend/app/services/jobs/ownership.py` uses the existing monotonic `attempts` counter plus `locked_by` as the lease generation. Ownership requires RUNNING, matching owner/generation, fresh heartbeat and an execution deadline.
- SQLAlchemy `before_flush` and `before_commit` hooks fence every domain session within the execution context. The ownership row is locked **inside the publication transaction**, serializing publication against recovery/transfer. A separate pre-flight check alone would not close the check/commit race.
- Queue settlement, rejection, failure and renewal require the actual ClaimedJob owner/generation. Expired heartbeats cannot be revived. Expired execution deadlines are reaped even if the process remains alive.
- Production JobRunner executes built-in handlers in spawned processes, monitors ownership, and terminates/kills a stuck or superseded child. Spawn avoids inheriting pooled connections/locks from worker threads. Existing IFC parse/geometry limits remain.
- RAG source publication/failure additionally checks the committed source claim timestamp under a row lock, so an older forced-index attempt cannot delete or fail a newer source index.
- Inline `run_pending` remains a synchronous test/drain helper; use the production JobRunner for process termination guarantees. Its domain commits still use lease fencing. External providers can have accepted an operation before a connection/process dies; exactly-once external effects are not claimed.

Files: `jobs/{ownership,queue,runner,handlers}.py`, `db/database.py`, `core/config.py`, `rag/ingestion.py`. No migration: queue generation, owner and source-claim fields already existed. New setting `JOB_MAX_EXECUTION_SECONDS` defaults to 1800 and must be positive. All workers must be drained/restarted together before a future rollout; an old binary does not acquire new fencing behavior automatically.

### G02 — evidence acceptance

Root cause: any nonempty non-sentinel model text became found=True and every retrieved passage became a citation, irrespective of support.

- `rag/validation.py` accepts only full extractive source sentences/passages with valid context citation IDs. Every attached citation must support its claim. Missing/invalid markers, invented numbers/units, omitted negation/applicability, unsupported arithmetic/approval prose and malformed structured claims abstain.
- Explicit outcomes: SUPPORTED_EXCERPTS, UNSUPPORTED, INVALID_OUTPUT, CONFLICTING_EVIDENCE and INSUFFICIENT_EVIDENCE. Same-wording numerical conflicts are detected conservatively; this is not a general semantic contradiction engine.
- Only supporting citations are returned; their inline numbers are remapped to the returned list. Structured extractive output is rendered as excerpts, not raw model JSON.
- The API explicitly returns `verified=false`. Source support is not engineering truth, compliance or approval. Document Agent retrieved text is a RECOMMENDATION requiring review, not FACT/1.0.
- Access is checked again after the provider call, refreshing ORM permission/membership state. Sensitive provider prose is never an authorization decision.
- The document assistant labels unverified excerpts. This deliberately sacrifices paraphrase acceptance; fluent unsupported explanations are not a compatibility requirement.

Files: `rag/{validation,answering}.py`, `schemas/{rag,knowledge}.py`, `api/{rag,knowledge}.py`, `ai_tools/read_tools.py`, document-assistant UI/types/locales. No new model or provider is introduced.

### G03 — Document Agent/tool contract

Root cause: whitespace was used as a list-all query even though search strips it and requires at least two characters; rejected input became empty successful evidence.

Added `list_documents` with explicit limit/offset, stable ordering, authorized total and AVAILABLE / NO_DOCUMENTS / NO_AUTHORIZED_DOCUMENTS source state. It reuses existing source visibility, not a broader agent policy. Document Agent uses this tool. Internal tool failures/invalid arguments raise a typed ToolReadFailure and produce FAILED/DATA_RETRIEVAL_FAILED rather than “no documents.” Permission-refused optional evidence is explicitly partial. Tests exercise actual tool registration, schema, source scoping, readable short titles and retrieval of controlled engineering passages through the real vector store.

Files: `ai_tools/{arguments,registry,read_tools}.py`, `agents/{registry,context,analyzers,runtime}.py`.

### G05 — narrative delay correctness

Root cause: substring matching ignored negation and `delays or issuesSummary` hid the second field. Narrative delay was labelled FACT/1.0.

Fields are checked independently. Negation and conditional/future language are excluded from established reported-delay detection, with English/Arabic rules. Potential/conditional reports have a distinct INFERRED finding; positive narrative delay is DETECTED/.9 and explicitly not a computed project delay. Existing task-date arithmetic remains deterministic. No duration, float or project consequence is invented. These conservative lexical rules cannot provide complete multilingual semantics.

File: `agents/analyzers.py`; regression/evaluation cases cover independent fields, negation and potential language. Human-confirmed source state and general causal analysis remain outside this phase.

### G06 — severity, lifecycle and promotion

Added a shared canonical contract: CRITICAL/HIGH/MEDIUM/LOW/INFO; legacy WARNING/ATTENTION/SUGGESTION/INFORMATION remain readable aliases. ORM insight persistence normalizes new/updated rows. APIs accept legacy severity queries, notifications interpret aliases, and web filters include MEDIUM/LOW.

Acknowledged findings are active and can be refreshed. Resolved/dismissed/actioned/outdated decisions remain terminal until an explicit human reopen; reopen clears resolved_at. Review/promotion use row locking and populate-existing state; concurrent promotions cannot each create a work item. Issue severity preserves HIGH/CRITICAL. Task promotion requires both task.create and ai.promote_insight. Automatic promotion text points to the source-gated insight instead of copying technical evidence to a broad project work item; human-supplied task text is an explicit publication choice.

Files: `services/insight_contract.py`, `models/ifc.py`, `agents/runtime.py`, `ai_insight_engine.py`, `api/ai_intelligence.py`, notification policy and frontend filters/status presentation.

### G07 — stable identities

Root cause: current affected-list contents/order and event ID were used as condition identity.

Known project-aggregate checks now have stable project/rule identity; entity-specific checks use explicit subject keys (task/change/phrase/discipline), with canonical sorted collections otherwise. This intentionally does not merge different agent/rule meanings into an Evidence Case. Advisory locks serialize discovery/creation of the same condition. Existing legacy rows are adopted when identifiable; redundant unreviewed aggregate rows are marked OUTDATED, not deleted. Human decisions remain preserved. Domain-rule findings key on project/code/subjects and retain associated event IDs, so repeated events update one active condition.

Recurrence policy: no automatic reopening of resolved conditions. Reviewers can explicitly reopen; future case-level recurrence history is Phase 3. This policy favors respecting a decision over silently re-announcing it.

### G08 — durable event delivery

- New events during cooldown defer their existing durable job to a due time, rather than succeed and discard work. Attempts remain monotonic fencing generations; deferrals do not consume the failure budget.
- Retries of a durable event bypass cooldown after it is due. Processing reads current accepted records, so old event payloads do not overwrite current state.
- Agent failures are raised to the queue. Agent findings/run records/in-app notifications publish in one outer event transaction; per-agent savepoints contain persistence failures. Run-record and notification failures retry publication instead of being hidden successes.
- Domain-rule RETRY states get an `events.process` job; rule failures use savepoints so they do not poison the primary write. Duplicate event keys serialize safely.
- AI push intent is queued transactionally as `push.deliver_notification`; delivery rechecks access and retries transient failures. Push provider exactly-once delivery is not promised. Nested savepoint commits do not dispatch pending external pushes.
- Site report creation/review/update now emits events subscribed by the Site Report Agent, addressing the prior mismatch with field-submission-only triggers.

Files: `domain_event_dispatcher.py`, `jobs/{deferred,queue,runner,handlers}.py`, `agents/{runtime,orchestrator,subscriptions,event_subscriber,registry}.py`, `push/dispatcher.py`, `api/site_reports.py`.

### G11 — completeness

Agent responses expose COMPLETE/PARTIAL/FAILED and coverage reasons. Tool-call records retain returned/total/complete information when available; bounded lists at their limit are conservatively partial when a total is unavailable. Inspecting only 15 report bodies is explicitly partial when more headers were read. Failed tools do not imply a clean project. Run records persist PARTIAL rather than SUCCEEDED for partial coverage; the client labels it and does not toast complete success. This phase exposes limits rather than adding unbounded scans or pretending all evidence has been covered.

### G17 — derived evidence boundaries

`services/insight_access.py` reauthorizes normalized and embedded source references, related tasks/issues/field evidence and model revisions. Unknown, missing, foreign or cyclic provenance fails closed. Source-free legacy records without explicit uncertainty are restricted to the accountable project manager. Reads of insight lists/overview/sources, review/promotion, get_findings, run history, notifications and delayed push apply the policy. Source revocation hides derived material; permissions are never obtained from prompts. New automatic task/issue promotion text does not copy private source facts. See security review for scope, tests and historical-publication limitations.

### G21 — offline provider isolation

The previously failing background-indexing test now injects the existing deterministic embedding provider into the actual background entry path. Success/READY/chunk assertions remain. Other canned-answer fixtures now return actual source excerpts; the adversarial citation test asserts refusal rather than accepting fabricated markers with unrelated citations. Real provider failure tests remain; the suite does not substitute success for a provider exception.

### G15 — initial evaluation baseline

`backend/evaluation/phase2a_cases.json` defines developer-authored synthetic construction evidence cases. `tests/test_phase2a_evaluation.py` exercises real acceptance code. `scripts/evaluate_phase2a.py` runs these and the worker/security/agent regressions only with an explicit disposable-environment opt-in, records JUnit/logs and measured mechanism counts. It is not an independent engineering benchmark or a real-model/semantic retrieval score. No RAPTOR, GraphRAG, new vector database or ML model was introduced.

## Scope and limitations

Version-authority semantics, full immutable provenance, OCR/table extraction, general contradiction/root-cause analysis, dependency-impact joining and the Evidence Case engine remain Phase 2B/2C/3. Exact extraction can abstain on legitimate paraphrases; that is intentional until a measured support verifier exists. Source authorization currently favors correctness over query-count efficiency. Existing historical manually published/copied work content and already delivered push/offline copies cannot be retroactively declassified or erased by a read guard; review those before rollout. No production engineering reliability claim is made.

Verification details and exact latest totals are authoritative in PHASE2A_TEST_RESULTS.md. Human review and manual validation requirements are in PHASE2A_MERGE_READINESS.md.


## Final verification disposition

Complete backend regression: 2,852 passed/1 intentional skip/0 failures; 51 Phase2A mechanism cases included. Frontend: 312 passed; TypeScript and production build passed. Frozen backend source digest remained unchanged. Required reports and source changes remain uncommitted on the isolated branch; HEAD is still the starting SHA. The verification package includes the review patch, changed-file snapshots, exact logs and manifests. Implementation is delivered for human review; live provider quality, engineering qualification and manual release gates are not declared complete by these test results.
