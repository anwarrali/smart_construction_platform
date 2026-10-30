# Module inventory and future test scenarios

## Verified module inventory (working tree, 24 Oct 2026)

| Module | Main files | Uses an LLM? | Tests (modules) | Status |
| --- | --- | --- | --- | --- |
| Authentication, step-up | `api/auth.py`, `api/step_up.py`, `core/security.py` | No | auth/security group: 18 modules, 298 passed | Implemented |
| Authorization, RBAC | `services/authorization.py`, `services/rbac.py`, `core/permission_catalogue.py` (59 codes) | No | RBAC group: 19 modules, 437 passed | Implemented |
| Projects, tasks, CPM | `api/projects.py`, `api/tasks.py`, `api/scheduling.py`, `services/cpm_service.py` | No | 17 modules, 222 passed | Implemented |
| Ingestion | `services/ingestion/` (state, pipeline, processors) | No | in ingestion/RAG group | Implemented |
| RAG and knowledge routing | `services/rag/`, `services/knowledge_router.py` | Embeddings and answering only | ingestion/RAG group: 16 modules, 831/832 passed | Implemented (1 env-dependent failure) |
| IFC processing and comparison | `services/ifc_processing_service.py`, `ifc_parser.py`, `ifc_interference.py`, `ifc_geometry_service.py` | No (`IFC_AI_MODEL` unused) | 14 modules, 178 passed, 1 skipped | Implemented; 3D viewer partial |
| Voice | `app/ai/*`, `services/voice_*` | Transcription, analysis, action analysis, phrasing | in voice/AI group | Implemented |
| Agents, insights, AI tools | `services/agents/`, `services/ai_insight_engine.py`, `services/ai_tools/` | No (deterministic rules) | voice/AI group: 25 modules, 675 passed | Implemented; auto mode off |
| Jobs | `services/jobs/`, `app/worker.py` | No | `test_job_runner` | Implemented |
| Notifications, realtime, messaging | `services/notification_service.py`, `services/push/`, `services/realtime/`, `api/messages.py` | No | 8 modules, 155 passed | Implemented; push needs Firebase |
| Web client | `frontend/src/features` (23 features) | — | 33 files, 310 tests | Implemented |
| Mobile client | `mobile_app/lib/features` (17 features) | — | 10 files, 141 tests | Implemented |

## Future test scenarios (not yet executed)

1. **Browser end-to-end:** log in as the project manager, create a project and tasks with dependencies, check the critical path; log in as the engineer, start a task, submit it for review; log in as the reviewer, reject it, then approve it.
2. **External isolation end-to-end:** log in as the contractor; confirm that unshared documents, office-only pages and approval actions are unavailable both in the UI and through direct API calls.
3. **Design-to-execution:** upload two IFC revisions with a moved column linked to a task; compare them; check the HIGH impact suggestion on the linked task and the lower-confidence discipline suggestions; acknowledge one and dismiss another; verify the audit entries.
4. **RAG quality:** build a set of 30–50 questions over sample contracts and specifications with expected answers and pages; measure citation correctness and the not-found rate with the live model.
5. **Voice:** run recorded Arabic and English site reports through the pipeline; measure correct routing (question vs. change) and correct task matching; confirm that nothing changes without confirmation.
6. **Push:** with Firebase configured, verify delivery to Android and the web after commit, and confirm that nothing is delivered for a rolled-back transaction.
7. **Load:** measure API latency and job throughput with several concurrent users and two IFC uploads at once; confirm that the processing ceiling holds across workers.
8. **Security:** an OWASP-guided review of token storage (localStorage), CORS, upload validation and rate limits.
9. **Fix the isolation weakness:** make `test_the_background_job_indexes_and_closes_its_own_session` inject a fake embedding service, then re-run the backend suite.
