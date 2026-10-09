# Background jobs

Heavy work runs off the request path on a durable queue in PostgreSQL:

| Kind | What runs | Queued by |
| --- | --- | --- |
| `ifc.process_version` | IFC parse, hierarchy, elements, quality checks | model upload, retry |
| `ifc.generate_geometry` | tessellation, then the interference pass | "generate geometry" |
| `ingestion.process_file` | the file ingestion pipeline | upload, reprocess |
| `rag.index_file` | embedding one ingested file | ingestion settling a file with text (`RAG_AUTO_INDEX_ENABLED`), "index" |
| `rag.project_reindex` | a project-wide re-index run | "re-index", the RAG reaper |
| `agents.handle_event` | automatic agent analysis of a domain event | `process_event`, when `AGENT_AUTO_ANALYSIS_ENABLED` |

Code: `app/services/jobs/` (`queue.py`, `runner.py`, `handlers.py`),
`app/models/background_job.py`, `app/worker.py`.

## How a job moves

```
request transaction ─ INSERT background_jobs (QUEUED) ─ COMMIT
                                     │
worker:  claim ─ UPDATE … FOR UPDATE SKIP LOCKED → RUNNING, attempts+1 ─ COMMIT
         run the handler (its own sessions; the domain row records progress)
         SUCCEEDED  │  error → QUEUED again after 30s·2ⁿ, or FAILED at max_attempts
         heartbeat every JOB_HEARTBEAT_SECONDS while running
reaper:  RUNNING with a heartbeat older than JOB_STALE_SECONDS → QUEUED (or FAILED)
```

- **Enqueued in the causing transaction.** A job exists exactly when its
  upload or event committed; a rolled-back upload leaves no work behind.
- **Durable.** A restart loses nothing queued. A job running when its worker
  dies is handed back by the reaper once its heartbeat goes stale.
- **No duplicates.** A `dedupe_key` (e.g. `ifc.process:<version>`) is unique
  among live jobs by a partial index, so a second request joins the first.
- **Recovery before retry.** A worker that died mid-job left its domain row
  looking in progress (an IFC version reading `PARSING`). On attempt 2+, a
  handler first resets that state, then lets the domain code start over.
- **The domain row stays the authority.** A parse that fails records FAILED on
  the IFC version and returns normally; the job reads SUCCEEDED, meaning the
  work ran. The job table answers "was this handed to a worker, and did it
  finish", not "did it succeed".

## The ceiling

`IFC_MAX_CONCURRENT_PROCESSING` is enforced **by the database across every
process**: a claim takes a transaction-scoped advisory lock and refuses while
that many jobs are RUNNING in the queue. The in-memory pool this replaced
bounded each process separately, so two uvicorn workers allowed twice the
memory the setting exists to cap.

## Where it runs

| Deployment | Runner | Setting |
| --- | --- | --- |
| Docker Compose | the `worker` service, `python -m app.worker` | backend `JOB_RUNNER_EMBEDDED=false` |
| Single container (Railway today) | threads inside the API process | `JOB_RUNNER_EMBEDDED=true` (default) |

Both may run at once; the queue, not the process, enforces the ceiling. The
dedicated worker does not migrate: it waits until the database is at the head
revision its code expects, so it can start before the API without running new
code against an old schema. On SIGTERM it stops claiming and gives running jobs
`SHUTDOWN_GRACE_SECONDS` (compose allows 60s); anything still running is
handed back by the reaper.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `JOB_QUEUE` | `default` | which queue a process produces to and consumes |
| `JOB_RUNNER_EMBEDDED` | `true` | run the runner inside the API process |
| `JOB_POLL_INTERVAL_SECONDS` | `2` | idle wait between looks for work |
| `JOB_HEARTBEAT_SECONDS` | `15` | heartbeat interval for running jobs |
| `JOB_STALE_SECONDS` | `120` | heartbeat age after which a job is presumed abandoned (≥ 3 heartbeats) |
| `JOB_MAX_ATTEMPTS` | `3` | attempts before a job is FAILED |
| `IFC_MAX_CONCURRENT_PROCESSING` | `2` | jobs running at once, fleet-wide |

## Tests

The suite shares the development database, so each test session uses a private
`JOB_QUEUE` (`tests/conftest.py`) and the embedded runner is off. A test that
wants its jobs run calls `app.services.jobs.runner.run_pending()`, which drains
that queue in the test's thread through the same claim-and-execute path.
`tests/test_job_runner.py` pins the queue's guarantees.

## Operating it

```sql
-- what is queued, running, failing
SELECT kind, status, count(*) FROM background_jobs GROUP BY 1, 2 ORDER BY 1, 2;
-- recent failures
SELECT kind, attempts, last_error, finished_at FROM background_jobs
WHERE status = 'FAILED' ORDER BY finished_at DESC LIMIT 20;
```

A FAILED job is not retried automatically; the domain action that queued it
(retry an IFC version, reprocess a file, re-index) queues a fresh one.
