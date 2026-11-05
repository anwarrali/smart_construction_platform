# Phase 2A merge readiness

Starting checkout: clean `main` at `200c06f5e18bc7717016c7f7681d4de02a3d071f`.
Working branch: `codex/phase2a-ai-reliability-correctness`.
Worktree: `/workspace/construction-phase2a`.
Previous reliability branch: unavailable; exact integration cannot be certified. Existing merged reliability commits were inspected before editing.

No merge, push, deployment or production changes are authorized/performed. Work is preserved locally for human review. Final HEAD/working-tree state and exact verified test totals are recorded in the verification package and final task output; uncommitted changes must not be mistaken for a different committed SHA.

## Changed-file scope

- Backend worker queue/ownership/process execution and source-index fencing.
- RAG evidence validation, explicit outcomes, citation selection/numbering and post-provider access checks.
- Agent/tool document listing, delay interpretation, completeness, stable identities, lifecycle and event recovery.
- Source-derived insight/read/notification/promotion authorization; promotion defaults avoid copying restricted technical content.
- Site-report event emissions and durable AI push intent.
- Shared severity/status contract, API schemas and relevant web types/filters/status/evidence wording.
- Regression tests, offline embedding/answer fixtures and the synthetic evaluation dataset/harness.
- These five Phase2A reports. The verification package includes the complete changed-file manifest/diff; no unrelated framework or architecture upgrade is included.

## Migration / compatibility

No schema migration is required. Existing job attempts/owner/heartbeat/start fields and source indexing timestamps support the new guards. New job kinds (`events.process`, `push.deliver_notification`) and ClaimedJob ownership requirements are **worker-code compatibility changes**: drain/restart all workers as one reviewed rollout before enabling them. Do not let an old worker reject new kinds or continue unfenced publication.

Legacy severity/status values are accepted as aliases; new/updated insights normalize canonical values. Reviewed terminal decisions are preserved. Human reopen is explicit. Additional response fields are additive; unverified source excerpt/refusal behavior is intentionally stricter than free-form model prose. Read-time source restrictions and default protected promotion pointers are behavior changes needing reviewer/client validation.

## Manual validation checklist

1. In an isolated staging copy, run all migrations/role seeding and the documented backend/evaluation/frontend commands. Confirm no provider key is required for ordinary tests.
2. Upload two representative authorized engineering documents; run Document Agent. Repeat with no documents, no authorized sources, a failing tool and >100 documents; verify distinct status and PARTIAL warnings.
3. Exercise exact source-supported quotes, unsupported grade/unit, conflicting numeric values, invalid citation, empty evidence and a source access revocation during generation. No unsupported response may appear verified.
4. File “no delay expected,” a conditional delay and a real reported delay in independent fields. Check labels, review requirement and that no computed project duration appears.
5. Acknowledge/reassess, resolve/rerun, explicitly reopen; promote HIGH/CRITICAL once and concurrently. Verify priority, one work item and no private technical text copied by defaults.
6. Use manager, scoped specialist, external party and other-project user. Verify insight list/details/sources/history/get_findings/notifications/promotion and delayed push after revocation; inspect historical publication policy separately.
7. In disposable workers, pause/expire/reclaim a job and resume the old worker, including a transaction opened before transfer. Verify no stale DB publication; force a source re-index and verify old failure cannot delete new chunks. Confirm blocked child termination and approved workload timeout settings.
8. Emit a burst during cooldown; let no further events arrive. Confirm trailing analysis executes. Interrupt analyzer/run-record/notification publication and replay; check one active condition and durable delivery intent. Test site-report filing/review triggers.
9. Review permission-query latency and shared queue capacity on realistic project/model sizes. Synthetic/local test timing is not a production SLO.

## Recommendation

**Prepare for human code/security review; do not merge automatically.** Automated verification is necessary but does not complete the manual policy/legacy-content/worker-rollout gates above. Production deployment and engineering qualification are not approved by this report. Exact final automated status and unresolved environmental limits are in PHASE2A_TEST_RESULTS.md; do not infer readiness from the intermediate runs.

Human approval is required before any merge, as requested. This task stops after implementation, verification and delivery of reviewable artifacts.


## Final recorded state

Ending HEAD SHA: `200c06f5e18bc7717016c7f7681d4de02a3d071f` (same as starting SHA). **Implementation and reports are uncommitted changes in the isolated worktree**; no commit or push was made. The delivery includes a patch and changed-file snapshots so this state is concrete and reviewable rather than represented as a different committed revision.

Final backend: 2,852 passed, 1 intentionally skipped, zero failures/errors across 120 files; frozen backend source digest verified unchanged. Final frontend: 312 passed; typecheck and build exit 0. `git diff --check` passed. Original main remains clean at the starting SHA. No new migrations or dependency manifest/lock changes.

Disposition: **ready for human review, not automatically cleared for merge/deployment**. Review the conservative excerpt/publication/legacy-visibility policies and execute the manual gates above. In particular, the synthetic baseline is not independently adjudicated construction evidence, a default npm install still has existing peer conflicts, and a mixed old/new worker rollout is not supported. No merge will occur without explicit approval.
