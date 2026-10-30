"""Chapter 5 (implementation and testing), Chapter 6 (business and evaluation), appendices."""

D = "../diagrams/png/"

CPM_LISTING = '''def _start_offset(dependency, predecessor, successor) -> int:
    """Convert a precedence relationship into a successor-start constraint."""
    lag = int(dependency.lag_days or 0)
    relation = _dependency_type(dependency)
    if relation == "start_to_start":
        return lag
    if relation == "finish_to_finish":
        return _duration(predecessor) + lag - _duration(successor)
    if relation == "start_to_finish":
        return lag - _duration(successor)
    return _duration(predecessor) + lag      # finish_to_start (default)

for task_id in order:                         # topological order, cycles rejected
    constraints = [earliest_start[p] + _start_offset(dep, by_id[p], by_id[task_id])
                   for p, dep in predecessors[task_id]]
    earliest_start[task_id] = max(0, max(constraints, default=0))
    earliest_finish[task_id] = earliest_start[task_id] + _duration(by_id[task_id])'''

AUTHZ_LISTING = '''def effective_permissions(db, user, project_id=None) -> set[str]:
    if user.status != UserStatus.ACTIVE:
        return set()
    granted = rbac.resolved_permissions(db, user, project_id)    # office + project role
    granted = _apply_user_overrides(db, user, project_id, granted)
    if rbac.holds_office_admin_role(db, user):                   # lockout protection
        granted |= {item.code for item in CATALOGUE if item.admin_locked}
    if rbac.is_external_participant(db, user, project_id):       # ceilings, after overrides
        granted -= rbac.NON_PROJECT_SCOPED
        granted -= rbac.NEVER_EXTERNAL
    ...                                                          # project reachability filter
    return granted'''

COMPARE_LISTING = '''base_items   = {e.global_id: e for e in elements_of(base)}
target_items = {e.global_id: e for e in elements_of(target)}
for gid in base_items.keys() - target_items.keys():   changes.append(REMOVED)
for gid in target_items.keys() - base_items.keys():   changes.append(ADDED)
for gid in base_items.keys() & target_items.keys():
    old, new = base_items[gid], target_items[gid]
    if delta(old.properties, new.properties) or delta(old.quantities, new.quantities) \\
       or location_delta(old, new) or old.geometry_hash != new.geometry_hash or identity_delta:
        record = MODIFIED (MOVED if location changed)
        record.severity = HIGH if old.entity_type in {IfcColumn, IfcBeam, IfcSlab, IfcFooting} \\
                          and (geometry or location changed) else MEDIUM
# impact: linked items -> confidence 1.0; otherwise up to 20 same-discipline tasks -> 0.65'''

CLAIM_LISTING = '''SELECT pg_advisory_xact_lock(:claim_key);                 -- serialise claimers
SELECT count(*) FROM background_jobs WHERE queue = :q AND status = 'RUNNING';
-- refuse when the fleet-wide ceiling is reached, otherwise:
UPDATE background_jobs
   SET status = 'RUNNING', attempts = attempts + 1, locked_by = :worker,
       started_at = now(), heartbeat_at = now()
 WHERE id = (SELECT id FROM background_jobs
              WHERE queue = :q AND status = 'QUEUED' AND run_after <= now()
              ORDER BY run_after, created_at
              FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING id, kind, payload, attempts;'''


def chapter5(E):
    g = E["groups"]
    grp_rows = [[name, str(v[4]), str(v[0]), str(v[1]), str(v[2]), str(v[3])] for name, v in g.items() if v[0]]
    grp_rows.append(["Total", str(E["be_test_files"]), str(E["be_total"]), str(E["be_passed"]), str(E["be_failed"]), str(E["be_skipped"])])
    return [
        ("h1", "Chapter 5: Implementation and Testing"), ("chap", "5"),
        ("lead", "This chapter describes the tools used, explains the technically significant modules from the code, describes "
                 "version control, and reports the testing strategy and the results of running the automated suites for this "
                 "report. Simple create-read-update-delete endpoints are not described in detail."),
        ("h2", "5.1 Development Environment and Tools"),
        ("table", "tools", "Verified technology choices (versions from the dependency manifests)",
         ["Area", "Technology", "Version / note"],
         [
             ["Backend", "Python, FastAPI, Uvicorn", "Python 3.11 image; FastAPI 0.104.1; Uvicorn 0.24"],
             ["Persistence", "PostgreSQL, SQLAlchemy, Alembic, pgvector", "PostgreSQL 15; SQLAlchemy 2.0.23; Alembic 1.12.1; pgvector 0.3.6"],
             ["Security", "python-jose (JWT), passlib (Argon2), Pydantic", "HS256 tokens; Pydantic 2.5"],
             ["AI and documents", "OpenAI SDK, tiktoken, pypdf", "embedding and answer models configurable; defaults text-embedding-3-small and gpt-4.1-mini"],
             ["BIM", "IfcOpenShell", "0.8.5"],
             ["Web client", "React, TypeScript, Vite, Tailwind CSS, TanStack Query, Zustand", "React 19.2; TypeScript 6.0; Vite 8"],
             ["Mobile client", "Flutter, Dart, Riverpod, go_router, Dio", "Flutter 3.32.2; Dart 3.8.1"],
             ["Testing", "pytest, Vitest with Testing Library, flutter_test", "pytest 8.3.4; Vitest 3.2"],
             ["Runtime", "Docker Compose, nginx", "five services (one behind a profile)"],
         ], [1.4, 2.6, 2.5], 9.5),
        ("p", "Development took place on Windows 11 with Docker Desktop for the database, API and worker, Node.js for the web "
              "client and the Flutter SDK for the mobile client. The backend image is built rather than bind-mounted, so new code "
              "is tested by mounting the source into a throwaway container."),
        ("h2", "5.2 Implementation Details, Key Algorithms, and Code Structure"),
        ("p", "Constructs separates **deterministic logic** from **language-model behaviour** deliberately. Only six modules call "
              "the OpenAI API: four in the voice pipeline (transcription, structured analysis, action analysis and response "
              "phrasing) and two in RAG (embeddings and answering). Everything else described below - permissions, scheduling, "
              "IFC comparison and interference, question routing, the five agents and the alignment score - is deterministic code "
              "whose output can be reproduced and checked. A configuration key for IFC analysis with a model exists but is not "
              "used by any module."),
        ("h3", "5.2.1 Permission resolution"),
        ("p", f"**Purpose.** Decide what a person may do in a given project. **Input:** user, permission code, optional project. "
              f"The permission catalogue declares {E['permissions']} codes, each with default roles and flags (`project_scoped`, "
              "`admin_locked`, `office_only`, `never_external`). **Processing** ({lst:authz}): role permissions are resolved, "
              "overrides applied, administrator lockout prevented and the external ceilings enforced last. **Output:** a set of "
              "codes; FastAPI dependencies raise 403 when the required code is absent, and `explain_permissions` reports which "
              "rule decided each code for the Access Control page. **Testing:** 437 tests in the RBAC and authorization group, "
              "including dedicated suites for external-party isolation and security regressions."),
        ("code", "authz", "Effective permission resolution (abridged from services/authorization.py)", AUTHZ_LISTING),
        ("h3", "5.2.2 Critical path calculation"),
        ("p", "`cpm_service.calculate_dependency_cpm` orders tasks topologically with Kahn's algorithm, sorting ready tasks by "
              "display order and name so results are deterministic, and rejects cyclic graphs. Each dependency type is converted "
              "into a start offset ({lst:cpm}), so one forward and one backward pass handle all four types with lags. Total float "
              "is LS - ES. Rather than marking every zero-float task, the algorithm reconstructs one connected driving path by "
              "walking backwards from the zero-float task that finishes last, following only tight constraints; a long task "
              "without dependencies is never reported as a critical path. `test_cpm_service` covers the four types, lags and "
              "cycle detection."),
        ("code", "cpm", "Dependency-type conversion and forward pass (abridged from services/cpm_service.py)", CPM_LISTING),
        ("h3", "5.2.3 Durable job queue"),
        ("p", "IFC processing and geometry, file ingestion, RAG indexing and agent analysis run through `services/jobs`. Seven job "
              "kinds are registered. {lst:claim} shows how a worker claims work. The handler separates a **bad input** (recorded "
              "as failed on the domain row; the job completes and is not retried) from a **broken run** (raised, then retried "
              "with a 30 s x 2^n backoff up to three attempts). A heartbeat is written every 15 seconds and a reaper returns jobs "
              "whose heartbeat is older than 120 seconds to the queue. `test_job_runner` pins these guarantees."),
        ("code", "claim", "Claiming the next job under a fleet-wide ceiling (simplified from services/jobs/queue.py)", CLAIM_LISTING),
        ("h3", "5.2.4 File ingestion"),
        ("p", "**Input:** an uploaded file. **Validation:** size, extension and content signature; SHA-256 checksum; duplicate "
              "detection. **Processing:** classification into a file category, then dispatch to a registered processor - PDF, "
              "Office documents, IFC (bridged into the IFC pipeline), ZIP packages whose members become child files, and other "
              "types. **Output:** READY, PARTIAL or FAILED with extracted metadata. PARTIAL means the file is usable but a "
              "capability was unavailable, such as a scanned PDF without text or a DWG that is stored only. When a file with "
              "text settles and automatic indexing is on (the default), an indexing job is queued. **Failure handling:** every "
              "state change passes the transition table ({fig:st_ing}); a retry re-enters the queue."),
        ("h3", "5.2.5 Retrieval-augmented answering"),
        ("p", "Indexing splits text into chunks of about 500 tokens with a 75-token overlap, embeds them and stores them in "
              "`document_chunks.embedding vector(1536)` with an HNSW cosine index. The classes involved are shown in "
              "{fig:class_rag}: `retrieve()` depends on the `VectorStore` protocol, implemented by `PgVectorStore` with pgvector's "
              "cosine-distance operator so that ranking and the top-k limit (default 5) run inside PostgreSQL."),
        ("fig", "class_rag", D + "17_class_rag.png", "Class diagram - retrieval and answering services"),
        ("p", "Grounding is enforced by three mechanisms that do not depend on the model behaving well. The system prompt "
              "forbids outside knowledge and requires the sentinel token `INSUFFICIENT_CONTEXT` when the passages do not support "
              "an answer. Citations are constructed from the retrieved chunk records, never parsed from the model's text, so a "
              "citation cannot point to a page that was not retrieved. And `found` is computed: when nothing readable is "
              "retrieved, no model call is made at all. Before retrieval, `knowledge_router` sends questions about progress, "
              "site reports or model findings to structured data instead, because a similarity search over PDFs cannot answer them."),
        ("h3", "5.2.6 IFC processing, revision comparison and interference"),
        ("p", "**Processing.** The parser runs in a separate process with a timeout and an address-space cap, so a malformed model "
              "cannot exhaust the API or worker. It extracts the spatial hierarchy, elements with GlobalId, class, discipline, "
              "properties, quantities and materials, and runs quality checks; each status change passes `VERSION_TRANSITIONS` "
              "({fig:st_ifc}). Processing also creates task suggestions per element class (for example footings to "
              "\"Foundation installation\") and per-storey milestone suggestions, each marked with its duplicate risk."),
        ("p", "**Comparison** ({lst:compare}, {fig:revision}). Elements of both versions are keyed by GlobalId. Content changes are "
              "detected by comparing stable hashes of properties and quantities, placement and storey/space location, geometry "
              "and identity fields. When elements lack stable GlobalIds, the comparison is flagged LOW confidence instead of "
              "silently mis-reporting identity changes as additions and removals. The comparison runs synchronously within the "
              "request."),
        ("code", "compare", "Revision comparison and impact logic (pseudocode of ifc_processing_service.compare_versions)", COMPARE_LISTING),
        ("p", "**Interference.** Geometry generation records an axis-aligned bounding box per element. `detect_interferences` "
              "compares structural elements with service elements using a spatial grid to limit comparisons, converts lengths "
              "with the model's declared unit and refuses to run when the unit is unknown, and reports what it analysed and why "
              "analysis was limited, because \"no findings\" and \"could not look\" must not look the same. Severity and "
              "confidence follow from penetration depth; results are stored as findings that can become issues. Bounding boxes "
              "over-approximate real shapes, so these are candidates for review, not confirmed clashes."),
        ("h3", "5.2.7 Model-to-execution alignment score"),
        ("p", "`ai_insight_engine.calculate_alignment` computes a transparent score from counts: the share of modelled elements "
              "whose discipline is covered by tasks (weight 40%), discipline coverage (25%), tasks linked to model locations "
              "(15%), issues linked to model elements (10%) and verified evidence linked to the model (10%). The weights are "
              "returned with the score so that a user can see how it was computed. The score is a design aid; its weights have "
              "not been calibrated against project outcomes."),
        ("h3", "5.2.8 Voice assistant and agents"),
        ("p", "The voice pipeline stores audio privately, transcribes it and requests a structured analysis from the model. "
              "Routing between a question and a change is deterministic and corroborates several independent signals, so one "
              "imperfect field cannot turn a question into a modification; an empty action list never becomes an action. A "
              "change becomes drafts with a ten-minute confirmation token; on confirmation, permissions are re-checked and "
              "each action is executed and recorded with an audit entry, its before and after state and a domain event. The "
              "five agents are rule-based analyzers over permission-checked tools; each finding carries evidence a reader can "
              "re-check, and each agent runs in isolation so that one failure does not affect the others."),
        ("h2", "5.3 Version Control and Change Management"),
        ("p", f"The project is versioned with Git and hosted on GitHub. The current branch history contains {E['commits']} "
              f"commits between {E['first_commit']} and {E['last_commit']}, organised in feature and fix branches merged through "
              "pull requests (for example the RBAC migration and the single start sequence). Schema changes are Alembic "
              f"migrations ({E['migrations']} files) applied automatically at container start. The RBAC redesign was staged: the "
              "new model ran beside the old one, an equivalence comparison was run for every account, and only then were the "
              "retired columns dropped. The working branch currently carries a large set of uncommitted changes; this report "
              "describes and tests that working tree."),
        ("h2", "5.4 Testing Strategy"),
        ("p", "Testing follows the test pyramid {cite:cohn2010}: many fast tests of pure logic, a large layer of API-level "
              "integration tests against a real database, and a few system-level checks."),
        ("h3", "5.4.1 Unit Testing"),
        ("p", "Unit tests exercise pure functions and contracts: CPM, schedule-date arithmetic, ingestion transition tables and "
              "classification, chunking, AI tool and agent contracts, voice routing and rules, and interference geometry on "
              "synthetic elements. On the clients, Vitest with Testing Library tests components such as modal focus behaviour "
              "and permission guards, and `flutter_test` tests Dart logic such as voice outcome semantics and audio format "
              "detection."),
        ("h3", "5.4.2 Integration Testing"),
        ("p", "Most backend tests call FastAPI endpoints through a test client with real tokens and a real PostgreSQL database "
              "with pgvector, and assert both responses and database state. Dedicated suites cover external-party isolation, "
              "authorization equivalence, AI tool authorization, file download authorization, the job runner, realtime delivery "
              "and IFC failure paths such as corrupt files, worker crashes and oversized results."),
        ("h3", "5.4.3 System Testing"),
        ("p", "System-level verification consists of `test_start_sequence` (every environment uses the same start sequence), "
              "whole-workflow tests such as `test_ifc_workflow` and `test_voice_pipeline_wiring`, and a manual QA plan "
              "(`docs/MANUAL_QA_TEST_PLAN.md`) with prioritised smoke, authentication, project, task, document, IFC and AI cases. "
              "The manual plan's result boxes are unticked, so no manual system-test results are claimed."),
        ("h2", "5.5 Test Results and Analysis"),
        ("p", "The three automated suites were executed on 24 October 2026 against the current working tree; no source file "
              "changed between the runs and the writing of this report. The backend suite ran in a throwaway container against a "
              "separate, freshly migrated `pgvector/pgvector:pg15` database, so the development database was not touched, and no "
              "OpenAI key was provided. Logs and the JUnit file are in the `evidence` folder. {tab:results_be} groups the "
              "backend results by functional area, assigned by test-module name."),
        ("table", "results_be", "Backend test results by functional area (pytest)",
         ["Area", "Modules", "Tests", "Passed", "Failed", "Skipped"], grp_rows, [2.6, 0.75, 0.75, 0.8, 0.8, 0.8], 9.5),
        ("table", "results_status", "Test outcomes by status across all suites",
         ["Status", "Count", "Details"],
         [
             ["Executed and passed", f"{E['be_passed']} + {E['fe_passed']} + {E['mobile_tests']}", "backend + web (full parallel run) + mobile"],
             ["Executed and failed", f"1 + {E['fe_failed']}", "backend: one test needing a live OpenAI key; web: timeouts under load, all 65 tests in the affected files passed when re-run serially"],
             ["Skipped", "1", "IFC worker-crash test that runs only when explicitly enabled"],
             ["Blocked by environment", "1", "the backend failure above; not re-run with a real key, to avoid sending data to a paid external service"],
             ["Not executed", "-", "manual QA plan; live AI-provider calls; push delivery through Firebase; performance, load and security penetration tests"],
         ], [1.6, 1.3, 3.6], 9.5),
        ("p", f"The backend suite collected {E['be_total']} test cases (the {E['be_test_funcs']} test functions expand through "
              "parametrisation) and took about 15 minutes. The single failure, "
              "`test_rag_ingested_files::test_the_background_job_indexes_and_closes_its_own_session`, raised \"OPENAI_API_KEY is "
              "not configured on this server\": unlike neighbouring tests, it calls the real embedding service. It is an "
              "environment-dependent failure, not a pass, and it also reveals a test-isolation weakness - the test should inject "
              "a fake embedding service."),
        ("p", f"In the web suite, {E['fe_passed']} of {E['fe_tests_run']} tests passed in the full parallel run; all "
              f"{E['fe_failed']} failures were interaction tests exceeding the default 5-second timeout while the mobile suite ran "
              "on the same machine, and the 65 tests in the nine affected files all passed when re-run serially. This indicates "
              "machine load rather than defects, but also that several tests are close to their timeout. The mobile suite passed "
              f"all {E['mobile_tests']} tests."),
        ("p", "**What these results do and do not show.** They verify behaviour at unit and API-integration level, including "
              "the authorization rules, the state machines and the design-to-execution mechanisms. They do not demonstrate that "
              "complete user journeys work in the browser or on a phone, that answers from the live model are accurate, or that "
              "the system meets any performance target. Code coverage was not measured, so no coverage figure is claimed."),
    ]


def chapter6(E):
    return [
        ("h1", "Chapter 6: Business Analysis and Project Evaluation"), ("chap", "6"),
        ("lead", "This chapter analyses how Constructs could create value for its users using the Business Model Canvas "
                 "{cite:osterwalder2010}, discusses costs and impacts qualitatively, and evaluates the project against its "
                 "objectives. No commercial deployment, customer or partnership exists, so the business analysis is prospective "
                 "and contains no invented figures."),
        ("h2", "6.1 Business Model Canvas"),
        ("h3", "6.1.1 Key Partners"),
        ("p", "A hosting provider for the containers and database; an AI model provider for transcription, embeddings and "
              "answers (replaceable, because model access is isolated behind service classes); Firebase for push notifications; "
              "and, for validation, universities and engineering associations able to host pilot projects."),
        ("h3", "6.1.2 Key Activities"),
        ("p", "Completing the partial features, security maintenance, onboarding each office (configuring roles, disciplines and "
              "templates) and supporting users."),
        ("h3", "6.1.3 Value Propositions"),
        ("bullets", [
            "One project record that external parties can safely join, with permissions the office controls and contractors cannot use to certify their own work.",
            "Explicit, reviewable links from model revisions to the tasks, issues and milestones they may affect.",
            "Answers from contracts and specifications with citations that can be checked.",
            "Field reporting by voice in Arabic or English, confirmed before it changes the plan.",
            "A self-hosted deployment that an office can operate itself.",
        ]),
        ("h3", "6.1.4 Customer Relationships"),
        ("p", "Assisted onboarding, because every office configures its own roles and processes, followed by support and periodic "
              "updates."),
        ("h3", "6.1.5 Customer Segments"),
        ("p", "Primary: small and medium consulting engineering offices that supervise building projects with several external "
              "parties. Secondary users - clients and contractors - join through the office's projects."),
        ("h3", "6.1.6 Key Resources"),
        ("p", "The code base and its automated test suite, the permission catalogue and role templates, the documentation and "
              "the domain knowledge encoded in workflows such as task review and IFC coordination."),
        ("h3", "6.1.7 Channels"),
        ("p", "Direct relationships with offices, demonstrations, professional and academic networks, and the Android and iOS app "
              "stores (an iOS release requires a macOS build environment)."),
        ("h3", "6.1.8 Cost Structure"),
        ("p", "Development and maintenance effort, hosting (compute, database, storage), variable AI usage and small costs for "
              "push and e-mail; Section 6.2 discusses them."),
        ("h3", "6.1.9 Revenue Streams"),
        ("p", "Options for future validation rather than tested pricing: a subscription per office or per active project, a "
              "usage-based tier for AI features whose cost scales with use, and installation and support contracts for offices "
              "that host the system themselves."),
        ("h2", "6.2 Cost Structure and Budget Analysis"),
        ("p", "No money was spent on software licences: every framework and tool used is open source or free for development, "
              "and the development machine was the author's own. The only potentially paid service used was the OpenAI API, whose "
              "usage was not metered for this report. Operating costs would consist of:"),
        ("bullets", [
            "**Fixed and recurring effort** - development, maintenance and support; not time-tracked during the project.",
            "**Hosting** - compute for the API, worker and web server, plus database and file storage; driven by the number of offices, projects, documents and models. Not measured, since only local deployment exists.",
            "**AI usage** - variable, driven by tokens for transcription, embeddings and answers. Not metered, but every provider call is logged in `ai_provider_calls` with model, latency and outcome, so a pilot could measure it exactly.",
            "**Push, e-mail and store accounts** - low, driven by notification volume and publication.",
        ]),
        ("p", "A quantitative budget would require at least a pilot deployment with a known number of users and projects; the "
              "AI cost should be measured from the call log before any pricing decision."),
        ("h2", "6.3 Impact Analysis"),
        ("h3", "6.3.1 Social Impact"),
        ("p", "Arabic interfaces and spoken-Arabic input lower the barrier for site staff who are more comfortable speaking than "
              "typing in English. Permission-controlled sharing gives owners direct visibility of progress and evidence, which "
              "can strengthen trust between parties, and every change remains traceable to a person rather than to an AI."),
        ("h3", "6.3.2 Economic Impact"),
        ("p", "Expected benefits are less time spent searching for and re-entering information, earlier recognition of schedule "
              "risk through dependency-driven CPM and blocker tracking, earlier recognition of model changes that affect planned "
              "work, and fewer disputes thanks to an auditable record. These are consistent with the productivity levers "
              "identified for the sector {cite:mgi2017} but have not been measured; no savings figure is claimed."),
        ("h3", "6.3.3 Environmental Impact"),
        ("p", "Digital reporting can reduce printing and some site visits, and recognising coordination problems before "
              "construction can reduce rework and waste, a benefit generally associated with BIM {cite:azhar2011}. Hosting and AI "
              "inference consume energy. No environmental measurement was performed."),
        ("h2", "6.4 Project Evaluation and Lessons Learned"),
        ("h3", "6.4.1 Achievement of objectives"),
        ("bullets", [
            "**O1 - connected project record:** achieved (FR-06 to FR-14, FR-24 to FR-29).",
            "**O2 - configurable, safe access:** achieved and strongly tested (FR-03 to FR-05; 437 passing RBAC tests).",
            "**O3 - schedule control:** achieved (FR-09 to FR-11).",
            "**O4 - design-to-execution links:** largely achieved (FR-15 to FR-18); the 3D viewer is in transition (FR-19).",
            "**O5 - document-grounded assistance:** achieved at code level (FR-20, FR-21); answer quality with the live model has not been evaluated.",
            "**O6 - field feedback:** achieved (FR-24, FR-25); not trialled on a real site.",
            "**O7 - traceability:** achieved (FR-29); push delivery requires Firebase configuration.",
        ]),
        ("h3", "6.4.2 Strengths"),
        ("bullets", [
            "One centrally tested authorization path with ceilings that configuration cannot override.",
            "AI constrained by architecture: deterministic routing, record-built citations, mandatory confirmation and full action history.",
            "Design-to-execution links that are explicit, reviewable and audited rather than automatic.",
            "Correct behaviour with several API workers through database-level locking and transactional fan-out.",
            f"A large backend regression suite ({E['be_passed']} passing tests) executed for this report.",
        ]),
        ("h3", "6.4.3 Limitations"),
        ("lead", "_{Partially implemented:}_"),
        ("bullets", [
            "Budget and expense tracking linked to evidence (FR-08).",
            "3D model viewing, removed from the current working tree (FR-19).",
        ]),
        ("lead", "_{Implemented but not yet verified end to end:}_"),
        ("bullets", [
            "Complete user journeys in the browser and on a phone; the manual QA plan has not been executed.",
            "Answer quality of RAG and voice with the live model; no evaluation set exists.",
            "Push delivery through Firebase in a real deployment.",
            "Performance, load behaviour and security under attack; no measurements or penetration tests exist.",
        ]),
        ("lead", "_{Design limitations and dependencies:}_"),
        ("bullets", [
            "Interference detection uses bounding boxes and over-approximates shapes; the discipline fallback for impact suggestions is a heuristic with a fixed confidence of 0.65.",
            "Uploaded files are stored in host-local volumes, so the backend cannot yet scale horizontally; only a local storage implementation exists.",
            "The web client keeps tokens in localStorage, and one signing key serves every token type without rotation.",
            "Docker Compose defaults are development-grade (default database password, published database port); no CI pipeline exists.",
            "AI features depend on the OpenAI API; one backend test depends on a live key.",
        ]),
        ("h3", "6.4.4 Future work"),
        ("nums", [
            "Execute the manual QA plan and add automated browser tests for the main journeys.",
            "Build an evaluation set of project questions with expected citations to measure retrieval and answer quality.",
            "Decide on the 3D viewer and complete expense tracking linked to evidence.",
            "Move refresh tokens to HttpOnly cookies, add signing-key identifiers, and implement S3-compatible storage.",
            "Add CI with coverage reporting, and run a pilot with a consulting office to measure usability, AI cost and time saved.",
        ]),
        ("h3", "6.4.5 Lessons learned"),
        ("p", "Authorization must be one function with tests that attack it, because a permission check copied into many places "
              "eventually diverges. Using the database for queueing, locking and messaging is a sound choice for a small team when "
              "each mechanism is chosen for correctness under several processes. AI features are trustworthy only when their "
              "guarantees are enforced in code - making citations impossible to fabricate and confirmation mandatory proved more "
              "reliable than instructing the model - and many problems that look like AI problems, such as routing a question or "
              "detecting a schedule risk, are better solved deterministically. Finally, documentation drifts: several statements "
              "in the project's own documents were out of date, which is why this report was written from the code."),
    ]


GLOSSARY = [
    ("AABB", "Axis-aligned bounding box: the smallest box aligned with the coordinate axes that encloses an element."),
    ("BIM", "Building information modelling: an object-based digital representation of a facility."),
    ("CPM", "Critical path method: scheduling based on earliest and latest times and float."),
    ("Embedding", "A numeric vector representing the meaning of a text passage, used for similarity search."),
    ("FS / SS / FF / SF", "Finish-to-start, start-to-start, finish-to-finish and start-to-finish dependency types."),
    ("GlobalId", "The globally unique identifier that IFC assigns to each object."),
    ("HNSW", "Hierarchical navigable small world graph, an approximate nearest-neighbour index."),
    ("IFC", "Industry Foundation Classes, the open BIM exchange schema (ISO 16739-1)."),
    ("JWT", "JSON Web Token, a signed token carrying claims (RFC 7519)."),
    ("MCP", "Model Context Protocol, through which external AI clients call tools (disabled by default)."),
    ("RAG", "Retrieval-augmented generation: answering from retrieved passages."),
    ("RBAC", "Role-based access control."),
    ("RFI", "Request for information about design or contract documents."),
    ("RTL", "Right-to-left text direction, used for Arabic."),
    ("SSE", "Server-sent events: one-way streaming from server to browser."),
    ("Step-up", "Additional verification required before a sensitive operation."),
]


def appendices(E, references_rendered, fig_index):
    from content_b import FR_GROUPS
    rtm_rows = []
    for _title, items in FR_GROUPS:
        for (i, t, _txt, _a, _e, tests, st, _s) in items:
            rtm_rows.append([i, t, tests.split(",")[0] + (" (+more)" if "," in tests else ""), st])
    blocks = [
        ("h1", "Appendices"), ("chap", "A"),
        ("h2", "Appendix A: Glossary of Terms"),
        ("bullets", [f"**{t}** - {d}" for t, d in GLOSSARY]),
        ("h2", "Appendix B: References"),
    ]
    blocks += [("ref", n, text) for n, text in references_rendered]
    blocks += [
        ("h2", "Appendix C: Supporting Materials"),
        ("p", "**Feature switches.** Optional behaviour is controlled by settings in `backend/app/core/config.py`: "
              "`RAG_ENABLED` (false in code, true in docker-compose), `RAG_AUTO_INDEX_ENABLED` (true), `VOICE_FEATURE_ENABLED` "
              "(false), `AGENT_AUTO_ANALYSIS_ENABLED` (false), `PUSH_ENABLED` (false), `REALTIME_ENABLED` (true), `MCP_ENABLED` "
              "(false), `JOB_RUNNER_EMBEDDED` (true; false under Compose, where the worker service runs jobs) and "
              "`IFC_MAX_CONCURRENT_PROCESSING` (2)."),
        ("p", "**Diagram sources.** Every diagram is provided as editable source in `diagrams/src` (PlantUML `.puml` files and "
              "one Python script) with its rendered image in `diagrams/png`; `diagrams/README.md` maps each figure number to its "
              "files. **Evidence.** Raw test logs and the JUnit file are in `evidence`."),
        ("pagebreak",),
        ("h2", "Appendix D: Requirements Traceability Summary"),
        ("p", "{tab:rtm} lists each functional requirement with a representative automated test and its status. The complete "
              "matrix, including all test modules, implementation files, related figures and the non-functional requirements, "
              "is provided in Constructs_Traceability_Matrix.xlsx."),
        ("table", "rtm", "Functional requirements with representative tests", ["ID", "Requirement", "Representative test", "Status"],
         rtm_rows, [0.6, 1.9, 2.6, 1.4], 8.5),
        ("h2", "Appendix E: Test Execution Details"),
        ("bullets", [
            "**Backend:** a copy of `backend/` mounted into a container built from the project's backend image plus pytest 8.3.4; a separate `pgvector/pgvector:pg15` container on a private Docker network; `alembic upgrade head`, role bootstrap, then `python -m pytest tests/ --junitxml`; no OpenAI key; `RAG_ENABLED=false` at process level (tests enable it where needed).",
            "**Web:** `npx vitest run` (Node 22, jsdom); serial re-run of the nine affected files with `--no-file-parallelism`.",
            "**Mobile:** `flutter test` with the host Flutter SDK.",
            "**To complete later:** a run with a test OpenAI key for the one environment-dependent test, and execution of the manual QA plan.",
        ]),
    ]
    return blocks
