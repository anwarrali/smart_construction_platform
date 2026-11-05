# Phase 2A test results

Baseline: `200c06f5e18bc7717016c7f7681d4de02a3d071f`; branch `codex/phase2a-ai-reliability-correctness`.

## Environment and safety

All source/test commands run from the isolated worktree. Tests use a disposable local pgvector/PostgreSQL16 container (`construction-phase2a-db`, loopback55440), throwaway databases, temporary uploads, and the existing Python3.12 virtual environment with repository requirements. No production connection or live OpenAI key is configured. Push and embedded workers are disabled except explicitly stubbed test cases. Existing fixtures disable natural language generation/outbound push and use a private queue. Full-suite shards each migrate and seed a separate new database, then drop only their own generated database names.

No dependency was added to application manifests. Frontend `npm ci` initially failed because its default cache was outside writable roots; retrying with a temporary cache exposed existing peer conflicts (React19 vs gantt-task-react18 peer; Vite8 vs Vitest3 peer range). Installation used the existing lockfile with `--legacy-peer-deps --ignore-scripts --cache /tmp/phase2a-npm-cache`. Manifests/lockfile were not changed. This is an environment/peer-compatibility limitation, not a verified clean install under default npm settings.

## Executed runs

These runs overlap and **must not be summed** into a test count.

| Run | Actual result | Meaning |
|---|---|---|
| New correctness regressions before implementation | 6 failed, 1 passed; 3.62s | Baseline defects reproduced; supported excerpt control passed. |
| First worker/agent/RAG focused run | 121 passed, 3 failed; 74.64s | Old tests expected FACT/1.0 delay and generic no-doc status. Assertions updated to the new explicit contract. |
| Second agent/event/API focused run | 168 passed, 1 failed; 26.94s | Old event inventory asserted14; two site-report event types now have emission paths. Updated the inventory assertion without dropping coverage. |
| Worker/agent/event/review/contracts focused run | 248 passed; 54.31s | Transaction/ownership and existing agent/review behavior. |
| RAG/API/tool/orchestration/push/notification focused run | 213 passed; 67.61s | Extraction acceptance, permission paths, current API behavior. |
| Initial synthetic evaluation harness | 45 passed; 15.47s | Mechanism acceptance/recovery/security; not real model accuracy. |
| Expanded evaluation harness | 51 passed | Additional publication/source/promotion regressions included; raw timing in JUnit/log. |
| Spawned-worker publication test | 1 passed; 6.66s | A real child process commits a finding under its current lease. |
| Broad intermediate backend run | 2,839 passed, 8 failed, 1 skipped; 1,166 warnings; 1,443.37s | Eight routing fixtures lacked project/provenance fields required by the stricter policy. Preserved as a non-green intermediate run. |
| Intermediate routing rerun with old already-loaded fixtures | 40 passed, 8 failed; 39.81s | Retained; not used as final verification. |
| Representative routing tests after fixture correction | 2 passed; 62.18s under concurrent load | No production authorization bypass; routing metadata fixtures now include explicit project/identity/provenance. |
| Intermediate two-shard run, deliberately interrupted | 30 passed before interruption; shard exits1/2 | Stopped to correct routing fixtures before the frozen-source run. Not reported as full or green. |
| Initial complete frontend suite | 310 passed /33 files; 158.54s | Existing client regression coverage. |
| Final complete frontend suite | 312 passed /33 files; 222.13s | Added partial-coverage and failed-result presentation regressions. |
| TypeScript build/typecheck | Passed (exit 0), including final rerun | `npm run typecheck`; see raw log. |

## Final complete backend verification

**2,852 passed, 1 skipped, 0 failed, 0 errors** across all **120** backend test files in two disjoint fresh databases. Both shard exit codes were 0.

| Final shard | Passed | Failed/errors | Skipped | Warnings | Pytest elapsed |
|---|---:|---:|---:|---:|---|
| 0 | 1,529 | 0 | 1 | 360 | 985.83s (16:25) |
| 1 | 1,323 | 0 | 0 | 813 | 1,286.85s (21:26) |

The shard durations overlap and are not a sequential wall-clock total. Warning counts include Pydantic/SQLAlchemy/httpx/dependency warnings; raw logs preserve them. The single skip is `tests/test_ifc_worker_failure.py::test_a_real_truncated_ifc_is_reported_as_corrupt_not_as_a_timeout`, explicitly opted out because a real IfcOpenShell worker may segfault. It was not forced on and is not counted as a pass.

The application/test/migration/evaluation source digest was identical before and after execution:
`7a8b5c125c85852bb8be3ce00238bca69d0f40179fa1021e5778e6ef4b780fad`.
The test-file lists, both JUnit files, setup logs and summary are retained. This is the final result, superseding the preserved intermediate failures without erasing them. All 51 Phase2A evaluation/correctness/integration cases were included in the complete suite. Registry additions also expand existing parameterized coverage; do not infer the total merely by adding51 to the Phase1 total.

Final client verification: **312 passed /33 files**, TypeScript exit 0, and production build exit 0 (`vite build`, built in 1m 4s). The build retained dependency annotation/plugin-timing warnings. No assets were deployed. Node v24.22.1 and npm11.9.0 were used.

The original offline background-indexing test passed in the final suite without an OpenAI key. No known automated failure remains in the executed final regression scope. This does not override the stated skip, npm default peer-resolution limitation or unexecuted live-provider/manual/engineering validation. No partial run is represented as a completed suite.

## Reproduction

Use a new disposable database; these fixtures write/delete records and create/drop private migration templates. Set a disposable SECRET_KEY and DATABASE_URL, OPENAI_API_KEY empty, PUSH_ENABLED=false, JOB_RUNNER_EMBEDDED=false, and temporary UPLOAD_DIR/PRIVATE_UPLOAD_DIR. From backend:

```sh
python -m alembic upgrade head
python -c 'from app.db.database import SessionLocal; from app.services.rbac import seed_roles,seed_disciplines; db=SessionLocal(); seed_roles(db); seed_disciplines(db); db.commit(); db.close()'
python -m pytest -q -p no:cacheprovider --junitxml=/tmp/phase2a-full.xml
PHASE2A_EVAL_ISOLATED=1 python scripts/evaluate_phase2a.py --output /tmp/phase2a-evaluation.json
```

Full verification in this environment divides the complete test-file inventory into two disjoint, independently migrated/seeded disposable databases. Each file is run once in that final batch; combined totals come from their actual JUnit files. This avoids cross-shard permission/role/queue interference. The external verification package contains file lists, setup logs, per-shard JUnit/logs, source digests and the temporary orchestration script.

Frontend:

```sh
npm ci --ignore-scripts --legacy-peer-deps --cache /tmp/phase2a-npm-cache
npm test -- --reporter=verbose
npm run typecheck
```

## Regression coverage

- Matching worker owner/generation, heartbeat expiration, renewal refusal, paused old attempt after transfer, concurrent claims, fresh spawned publication, process deadline termination, nested-session fencing and forced-source-index recovery.
- Unsupported numbers/units/approval/arithmetic, missing/invalid citations, omitted negation/applicability, malformed structured output, whole-sentence extractive support, citation renumbering, numeric conflicts, empty evidence and English/Arabic synthetic evidence.
- Real Document Agent -> authorized list -> tool/runtime -> controlled vector retrieval -> supported excerpt; missing vs inaccessible documents; failed tool vs empty source; bounded scan PARTIAL.
- Narrative negation, independent fields and reported vs hypothetical impact; no invented computed project delay.
- HIGH promotion, acknowledged reassessment, explicit terminal/reopen policy, changing evidence order/growth, duplicate/current-state events and concurrent promotion.
- Durable cooldown/trailing execution, failed analyzer retry, run-record/notification publication rollback and durable rollback-safe push intent.
- Restricted-source derived insight, cross-project reader, revocation through get_findings/notification, protected promotion defaults, existing broader source/API/RBAC tests.
- Original failing offline background-indexing test with real READY/chunk assertions; deterministic provider and retained provider-error cases.

## Limits

No real OpenAI transcription/embedding/generation call, semantic retrieval benchmark, independent construction-engineer adjudication, production load/soak test or live push delivery was performed. Synthetic acceptance counts are not precision/recall, engineering accuracy or model hallucination rates. The existing real IfcOpenShell truncated-file segfault test is opt-in and remains a skip if the suite reports it; simulated worker-failure coverage does not turn that skip into a pass. Exact skip/failure details belong to the final JUnit results.
