# Phase 2A security review

Branch `codex/phase2a-ai-reliability-correctness`; baseline `200c06f5e18bc7717016c7f7681d4de02a3d071f`.

## Security decisions

1. **Execution ownership is checked in the publication transaction.** Job ID alone is insufficient. Owner/attempt/status/heartbeat/deadline must match under a database row lock; recovery cannot transfer ownership and then accept an old transaction's publication. Built-in worker execution is process-bounded. Source-index claim checks prevent old failure handlers deleting newer chunks.
2. **Evidence is untrusted content.** A source passage may contain misleading engineering text or prompt injection. It cannot grant a tool, project access, verified status or an engineering approval. Extractive acceptance checks membership and complete source wording; `verified=false` is explicit.
3. **Derived data retains source restrictions.** An analysis principal is not an authorization grant to its readers. Source checks cover document/file policy, scoped tasks, field evidence, IFC/project permissions, related findings, missing sources and cycles. A whole insight is denied if any required source is unreadable, rather than exposing a partial title/summary that may reveal the hidden part.
4. **Delayed delivery reauthorizes.** Notifications and delayed push are not permanently readable merely because the user was once a recipient. RAG rechecks access after the provider call and refreshes ORM state. Previously delivered remote/offline content cannot be recalled.
5. **Promotion is not automatic declassification.** Default issue/task text contains a protected-insight reference, not copied requirements/snippets. Explicit task payload text is a deliberate human publication through existing permissions. Reviewers must understand that distinction. Source-level access plus action permissions are required before promotion, and competing promotions serialize.

## Boundaries and exercised tests

| Boundary | Verification |
|---|---|
| Cross-project retrieval and tool access | Existing RAG API/store/tool/RBAC suites; source policy also checks source.project_id even if an ID is supplied from elsewhere. |
| Restricted document -> stored insight | Real DB regression creates a manager-derived insight from a structural source; an electrical-scoped reader cannot read it or reach it through get_findings. |
| Source access revocation | Regression changes a reader's discipline assignment; prior insight/notification access becomes denied, with 404 on individual notification. |
| Read/promotion authority | Existing IFC/AI/RBAC tests plus source-gated insight mutation. HIGH promotion retains priority; duplicate/concurrent promotion produces one work item. |
| Restricted content in new work | Regression promotes private numerical content and verifies it is absent from default public work title/description; protected reference retained. |
| Stale ownership and crash recovery | Expired/paused old owners cannot settle, renew or publish; nested session publication is rejected. A current spawned worker can publish; a blocked spawned child is terminated at deadline. |
| Prompt/output abuse | Invalid markers, missing evidence, invented grade/unit/approval, omitted negation/applicability, malformed structured claims and detectable conflicting values abstain in deterministic cases. This is not a live adversarial-model success-rate measurement. |
| Event replay/partial failure | Cooldown deferral/trailing event, analyzer failure, run-record failure, notification failure, duplicate idempotency keys and current-state replay tests. |
| Offline providers | Original failing indexing path uses deterministic embeddings; provider-error tests are retained. |

The expanded router checks require complete source metadata in tests as in production. Eight old routing tests initially used a two-field _Insight fake with no project/identity/provenance. Their fixtures were expanded to explicitly represent project-scoped, source-free uncertainty metadata; external-party/permission assertions remain. No production bypass for incomplete objects was added. Exact executed results are in the test-results report.

## Remaining concerns / release checks

- Full semantic prompt-injection resistance is not proven. Backend authority gates and refusal of non-extractive claims are defenses; raw documents can themselves be wrong, malicious or outdated.
- Document-family/effective-revision/approval precedence remains G04/Phase 2B. A literal source excerpt is not a governing engineering requirement without that policy and human review.
- Historical work items or messages explicitly published/copied before this change may already contain derived material. This implementation does not rewrite production records or recall prior device/push copies. Inventory and classify existing promoted content before rollout.
- Source-free legacy findings are restricted conservatively. Validate that assigned managers can review them and that expected specialists are not silently losing necessary access. Add missing trustworthy provenance deliberately; do not widen read permissions to compensate.
- Multiple source-policy queries can make large insight lists expensive. No permission-unsafe cache is introduced. Load-test filtering and optimize with equivalent SQL predicates after correctness is established.
- All live workers must move to the same fenced implementation. Rolling mixed old/new workers is not a supported security guarantee.
- External push/provider side effects are at-least-once/best effort at the provider boundary. Durable intent and dedupe reduce repeats; a remote operation accepted before a process/connection dies cannot be made exactly once by a local transaction.
- RBAC changes racing after the final access check are governed by normal request transaction boundaries. No global serializable transaction across a remote model/provider and every ACL row is claimed.
- No production grants, provider credentials, production infrastructure, data residency/retention configuration or real user notifications were inspected/changed in Phase 2A.

Security disposition: review the implementation and run manual revocation/publication/worker-rollout checks before authorizing a merge or deployment. Passing tests do not constitute construction safety certification.


## Final verification record

Final complete backend regression: 2,852 passed, 1 intentional skip, 0 failures/errors. Final frontend: 312 passed; typecheck/build passed. Source digests match before/after the backend run. The 8 intermediate fixture failures are retained in the evidence, not concealed; their corrected fixtures were included in the final clean run. Security/manual gates and historical-publication limitations above remain; no production penetration test or safety certification is implied.
