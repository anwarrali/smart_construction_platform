# Remaining gaps and limits

Phase 2A implements bounded reliability/correctness controls in the existing architecture. It does not establish production engineering competence from functional test counts.

## Phase 2A validation still requiring a person

1. Review the final test results, transaction/fencing design and the changed source-authorization policy before merge. Verify representative site/report/agent/insight workflows through the real browser/mobile clients. Automated UI tests are not field usability validation.
2. Confirm the publication policy: default promotions carry a protected-insight reference; explicitly supplied task text is a human publication decision. Review historical already-published/copied work content before rollout. No production records were rewritten.
3. Validate legacy finding visibility. Unattributed non-uncertain findings are restricted to the assigned manager; add trustworthy provenance rather than widening policy. Existing terminal reviewed decisions remain suppressed until a person reopens them.
4. Validate production worker deployment: drain/restart every worker to avoid mixed unfenced/fenced versions; choose JOB_MAX_EXECUTION_SECONDS appropriate to approved IFC/RAG workloads; verify child-process permissions/memory and queue throughput. No deployment was attempted.
5. Resolve/accept the pre-existing npm peer constraint before relying on a standard clean CI installation. This phase tested the existing dependency lock with legacy peer resolution and did not upgrade unrelated frameworks.

These are explicit release/manual gates, not passed tests. Final automated totals and any unresolved failures are in PHASE2A_TEST_RESULTS.md.

## Known implementation tradeoffs

- **Extractive answers only.** Legitimate paraphrases, synthesis and calculations can abstain. A source may be wrong, malicious or outdated; quoting it does not verify it. No general semantic entailment, contradiction or source-authority engine was added.
- **Conflict detection is narrow.** Same-wording numeric disagreement is a deterministic refusal case. Different wording, unit conversion, technical applicability and authoritative document precedence require Phase 2B/2C evidence semantics and a real benchmark. Do not describe this as complete contradiction detection.
- **Conservative narrative rules.** English/Arabic lexical negation/conditional handling fixes tested examples but cannot cover all technical speech, mixed clauses or implied delays. Narrative findings remain reported/detected/inferred, never computed project consequences.
- **Completeness is visible, not unlimited.** Agents still use bounded snapshots; a PARTIAL result is not a clean project assessment. Pagination exists for authorized documents but the agent is deliberately bounded. Future incremental/watermark analysis can improve coverage without hiding limits.
- **Identity is rule/subject based.** Project-wide aggregates intentionally group one rule's current condition; entity-specific rules remain separate. Cross-agent/root-problem consolidation and automatic recurrence history require Evidence Cases. No automatic reopening of a terminal human decision occurs.
- **Legacy duplicate cleanup is conservative.** Identifiable unreviewed duplicate aggregates can become OUTDATED; reviewed records are not deleted. Historical terminal records can still appear in explicit historical/all-state queries.
- **Authorization prioritizes correctness.** Read-time source checks can cause many queries; list filtering before final pagination can be expensive. Optimize only with equivalent permission tests, not a stale global visibility cache.
- **External effects are not exactly once.** Durable push intent, current authorization and retry/dedupe do not recall an already delivered push or prove exactly-once remote provider behavior.
- **Process limits have scope.** Production JobRunner uses bounded spawned handlers; synchronous test/drain helpers execute inline and should not replace the production runner. Database publication still remains fenced in those helpers. Trusted future code using raw independent connections must not bypass the guarded session contract.
- **No production data remediation.** Already published historical copies and offline clients require operator review; this work does not erase production history.

## Deferred dependencies

| Phase | Gap / required work | Why deferred |
|---|---|---|
| 2B | G04 authoritative document families/revisions/effectivity/supersession | Source lifecycle/domain workflow, not a Phase2A claim-validation shortcut. |
| 2B | G09 consistent embedding model/index generations | Semantic space management and measured migration/rollback. |
| 2B | G10 immutable content/version provenance and source-complete invalidation/reassessment | Larger evidence/history contract; Phase2A read authorization does not replace it. |
| 2B | G13 complete provider token/cost/latency budgets/telemetry | No real provider economics measured here. |
| 2C | G14 OCR, structured tables/XLSX cells/drawing evidence | Missing technical inputs cannot be fabricated by stronger prompts. |
| 2C | G15 independent engineer-adjudicated retrieval/claim benchmark | Current developer-authored synthetic mechanism harness is only an initial baseline. |
| 3 | G12 dependency-aware revision impact using existing CPM/IFC links | Must distinguish declared impact from calculated delay/float and missing link assumptions. |
| 3 | G16 Evidence Case lifecycle, supporting/conflicting claims and decision history | Intentionally not introduced; requires stable evidence and authority semantics. |
| 3/4 | G18 bounded engineering interpretation and root-cause hypotheses | Needs complete, versioned, evaluated evidence and human judgment. |
| Research only | G19 hybrid/reranking/RAPTOR/GraphRAG | Adopt complexity only for measured residual failures. No new graph/vector/model stack added. |

Recommended next action: review/validate Phase2A behavior and legacy publication policy, then complete governing evidence/version/provenance and the engineering benchmark. Do not expand proactive rollout based solely on green tests or treat source excerpts as approved engineering decisions.


## Final automated status

All known failures observed during implementation were resolved in the final complete regression: 2,852 backend passes, one intentionally skipped real-worker segfault test, no failures/errors;312 frontend passes; typecheck/build passed. These are scoped automated results, not a claim that every possible production interleaving or engineering judgment is verified. The manual/release/Phase2B+ items above remain explicit limitations and next actions.
