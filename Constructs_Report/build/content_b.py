"""Chapter 3 (requirements and analysis) and Chapter 4 (design and architecture)."""

D = "../diagrams/png/"
I, P, U = "Implemented", "Partial", "Implemented, disabled by default"

# (id, short title, requirement text, actors, implementation evidence, automated tests, status, source)
FR_GROUPS = [
    ("Authentication, authorization and administration", [
        ("FR-01", "Sign-in and sessions", "Users sign in with e-mail and password and receive a 30-minute access token and a single-use, rotating 7-day refresh token; logout and password reset are supported; self-registration is disabled.",
         "All users", "api/auth.py, core/security.py", "test_auth_refresh_concurrency, test_login_rate_limiting, test_bootstrap_admin", I, "Proposal 13"),
        ("FR-02", "Step-up verification", "A first-login password change is forced, and sensitive operations require an e-mailed one-time code verified within a short window.",
         "All users", "api/step_up.py, services/step_up_service.py", "test_step_up_security", I, "Proposal 13"),
        ("FR-03", "Configurable roles", "An office administrator manages accounts, roles, role permissions, disciplines and memberships, starting from seeded role templates, without code changes.",
         "Office Administrator", "api/organization.py, api/users.py, core/role_templates.py", "test_rbac_customization, test_role_templates, test_configurable_account_creation", I, "Proposal 2"),
        ("FR-04", "Per-person exceptions", "An administrator grants or denies a single permission to one person, everywhere or on one project, and can see which rule decided each permission.",
         "Office Administrator", "services/authorization.py, api/permissions.py", "test_authorization, test_permission_capabilities", I, "Proposal 2"),
        ("FR-05", "External-party isolation", "External participants see only project-scoped data explicitly shared with their party and can never hold certification or access-governance permissions.",
         "Client, Contractor", "services/authorization.py, services/document_access.py", "test_external_party_isolation, test_entity_sharing, test_rbac_security_regression", I, "Proposal 2"),
    ]),
    ("Project and stakeholder management", [
        ("FR-06", "Projects", "Authorised users create, edit and delete projects, with a deletion-impact preview and a configurable consultant approval workflow.",
         "Project Manager, General Manager", "api/projects.py", "test_project_deletion_authorization, test_get_project_by_id", I, "Proposal 1"),
        ("FR-07", "Members and parties", "Project managers assign members with project roles and organise external parties (client, main contractor, subcontractors).",
         "Project Manager", "api/projects.py", "test_project_team_assignment", I, "Proposal 1"),
        ("FR-08", "Dashboards and budget view", "Users see project summaries, an owner dashboard and action-centre counts; projects hold budget total and spent values, and cost validation requests are reviewed with variance and risk level.",
         "Owner, Project Manager", "api/dashboard.py, api/projects.py, api/cost_validations.py", "test_action_center_counts, test_cost_validation_access", P, "Proposal 10"),
    ]),
    ("Tasks, dependencies and schedules", [
        ("FR-09", "Task management", "Project managers create, assign, prioritise, reorder and edit tasks with planned and actual dates, durations, disciplines and milestones.",
         "Project Manager", "api/tasks.py, api/milestones.py", "test_task_update_reliability, test_milestone_authorization", I, "Proposal 1"),
        ("FR-10", "Task execution and review", "A task starts only from TODO when predecessors are done and no blocker is open; assignees report progress and blockers, submit for review, and reviewers approve, reject with corrections or request clarification.",
         "Engineer, Reviewer", "api/tasks.py, services/task_progress_service.py", "test_consultant_approval_policy, test_task_update_reliability", I, "Proposal 1, 9"),
        ("FR-11", "Dependencies and CPM", "Tasks are linked by FS, SS, FF or SF dependencies with lag; cycles are rejected; the system provides Gantt data, a connected critical path, delay analysis and schedule shifting.",
         "Project Manager", "api/scheduling.py, services/cpm_service.py", "test_cpm_service, test_schedule_dates, test_rbac_schedule_and_ai_insights", I, "Proposal 1"),
    ]),
    ("Documents and engineering information", [
        ("FR-12", "Document library", "Members upload, search, download and delete documents through authenticated endpoints and share individual documents with an external party.",
         "Project members", "api/documents.py, services/private_storage.py", "test_file_download_authorization, test_private_storage", I, "Proposal 3"),
        ("FR-13", "File ingestion", "Uploaded files (PDF, DOC/DOCX, XLS/XLSX, IFC, images, ZIP, TXT) are validated, checksummed, de-duplicated, classified and processed asynchronously; DWG/DXF files are stored but not parsed.",
         "Project members", "api/ingestion.py, services/ingestion/", "test_ingestion_pipeline, test_ingestion_classification, test_ingestion_archives, test_ingestion_reliability", I, "Proposal 3"),
        ("FR-14", "Design changes and requests", "Engineers propose design changes with cost and schedule impact, linked to a task; reviewers approve, reject or mark them implemented; clients raise owner requests.",
         "Engineer, Reviewer, Client", "api/design_changes.py, api/collaboration.py", "test_authorization, test_entity_sharing, test_accountable_collaboration_policy", I, "Proposal 9"),
    ]),
    ("BIM/IFC processing and coordination", [
        ("FR-15", "IFC processing", "IFC files are uploaded into model groups and versions and parsed in an isolated process into spatial hierarchy, elements, properties and quantities, with quality checks.",
         "BIM Engineer", "api/ifc.py, services/ifc_processing_service.py, ifc_parser.py", "test_ifc_parser, test_ifc_workflow, test_ifc_upload_reliability, test_ifc_corpus", I, "Proposal 8"),
        ("FR-16", "Model-derived suggestions", "Processing proposes construction tasks per element class and per-storey milestones, flagged for duplicate risk; accepting a suggestion creates the task or milestone.",
         "Project Manager", "services/ifc_processing_service.py, api/ifc.py", "test_ifc_workflow", I, "Proposal 8"),
        ("FR-17", "Revision comparison and impact", "Two versions of one model group are compared by GlobalId into added, removed, modified and moved elements; impact suggestions are created on linked items or same-discipline tasks and are acknowledged or dismissed.",
         "BIM Engineer, Project Manager", "services/ifc_processing_service.compare_versions, api/ifc.py", "test_ifc_workflow", I, "Proposal 8"),
        ("FR-18", "Coordination findings", "Structural/service interference candidates are computed from element bounding boxes and can be turned into project issues, ignored or marked false positive.",
         "BIM Engineer", "services/ifc_interference.py, api/ifc.py", "test_ifc_interference, test_ifc_interference_pipeline, test_ifc_findings_pagination", I, "Proposal 8"),
        ("FR-19", "3D viewing", "Viewer geometry is generated server-side per version for display in a 3D web viewer.",
         "Project members", "services/ifc_geometry_service.py; frontend IFCViewer.tsx (last commit only)", "test_ifc_geometry, test_ifc_geometry_result_size", P, "Proposal 8"),
    ]),
    ("AI-assisted analysis and retrieval", [
        ("FR-20", "Grounded document answers", "Questions are answered only from documents and files the user may read, with citations to document and page, and a not-found answer when the context is insufficient.",
         "Project members", "api/rag.py, services/rag/", "test_rag_pipeline, test_rag_api, test_rag_unified_retrieval, test_rag_pgvector", I, "Proposal 6"),
        ("FR-21", "Question routing", "A question is routed deterministically to structured project data, IFC data or document retrieval, defaulting to documents when unsure.",
         "Project members", "api/knowledge.py, services/knowledge_router.py", "test_knowledge_router, test_knowledge_query", I, "Proposal 6"),
        ("FR-22", "Rule-based insights and agents", "Deterministic analyzers produce evidence-carrying findings: five agents (site report, document consistency, revision impact, RFI, schedule risk) on demand, and a model-to-execution alignment score.",
         "Project Manager", "services/agents/, services/ai_insight_engine.py", "test_agent_orchestration, test_agents_integration, test_ai_insight_engine", I, "Proposal 7"),
        ("FR-23", "Event-driven agent analysis", "Agents run automatically when domain events occur, under the project manager's authority.",
         "System", "services/agents/event_subscriber.py", "test_agent_autonomous_detection", U, "Proposal 7"),
    ]),
    ("Site execution and reporting", [
        ("FR-24", "Site reports and evidence", "Site staff submit daily reports and field evidence with directional photographs; authorised engineers verify or return them; photos are archived by category.",
         "Site Engineer, Contractor", "api/site_reports.py, api/field_submissions.py, api/photo_archive.py", "test_site_report_verification, test_field_submission_policy, test_photo_archive_policy", I, "Proposal 4"),
        ("FR-25", "Voice-to-action", "Spoken Arabic or English is transcribed and analysed; questions are answered; proposed changes become drafts executed only after confirmation and a fresh permission check.",
         "Site Engineer, Engineer", "api/voice.py, app/ai/, services/voice_*", "test_voice_command_workflow, test_voice_human_authority, test_voice_router, test_voice_intent_routing", I, "Proposal 5"),
        ("FR-26", "Issues, visits and reminders", "Issues with severity and status are linked to tasks; site visits are scheduled with participants; reminder rules send automatic reminders.",
         "Engineer, Project Manager", "api/issues.py, api/collaboration.py, services/reminder_service.py", "test_site_visit_scheduling, test_reminder_workflow, test_permission_capabilities", I, "Proposal 9, 11"),
    ]),
    ("Communication, notification and traceability", [
        ("FR-27", "Messaging", "Members exchange direct, group, project and contextual messages with acknowledgement, response tracking and forwarding.",
         "All project members", "api/messages.py, services/messaging_policy.py", "test_messaging_policy, test_message_forwarding", I, "Proposal 11"),
        ("FR-28", "Notifications", "Users are notified in-app, by push (Firebase) and by e-mail; the web client receives live update hints over server-sent events.",
         "All users", "services/notification_service.py, services/push/, api/events.py", "test_notification_api, test_push_notifications, test_realtime", I, "Proposal 11"),
        ("FR-29", "Audit and AI history", "Important actions are recorded in audit logs and domain events; AI-initiated changes are stored with before and after state and can be reverted.",
         "Administrator, Project Manager", "services/audit_service.py, api/ai_actions.py", "test_domain_event_emission, test_ai_traceability_policy", I, "Proposal 12"),
        ("FR-30", "Bilingual interface", "Web and mobile interfaces are available in English and Arabic with right-to-left layout.",
         "All users", "frontend/src/i18n, mobile_app/lib/l10n", "IFCActionTabs.i18n.test.ts, test_ai_insight_localization", I, "Proposal 14"),
    ]),
]

# (id, category, statement, evidence class, evidence)
NFR = [
    ("NFR-01", "Security", "Passwords hashed with Argon2; typed tokens (access, refresh, SSE ticket) that cannot substitute for one another; single-use refresh rotation.", "Supported by implementation and tests", "test_auth_refresh_concurrency"),
    ("NFR-02", "Security", "Every subsystem resolves permissions through one function; ceilings are applied after overrides; the server re-checks every operation regardless of client state.", "Supported by implementation and tests", "RBAC test group (437 passed)"),
    ("NFR-03", "Security", "Database-backed rate limits on login, one-time-code sending and verification, and MCP tool calls, correct across several API workers.", "Supported by implementation and tests", "test_login_rate_limiting, test_mcp_hardening"),
    ("NFR-04", "Confidentiality", "Documents, IFC sources, geometry and audio are stored privately and streamed only through authenticated endpoints.", "Supported by implementation and tests", "test_file_download_authorization"),
    ("NFR-05", "Reliability", "Background jobs are enqueued in the causing transaction, de-duplicated, retried with exponential backoff and reclaimed after a stale heartbeat.", "Supported by implementation and tests", "test_job_runner"),
    ("NFR-06", "Reliability", "Secondary products (geometry, agents, push, indexing) cannot fail the primary operation that triggered them.", "Supported by implementation and tests", "test_ifc_secondary_product_failure"),
    ("NFR-07", "Consistency", "Notifications and realtime events are written in the caller's transaction and delivered only after commit.", "Supported by implementation and tests", "test_realtime"),
    ("NFR-08", "Resource safety", "IFC parsing is bounded by timeouts, memory caps and vertex limits; uploads are size-limited.", "Implemented; limits configured, not load-tested", "ifc_processing_service, config"),
    ("NFR-09", "Scalability", "Correct behaviour with several API workers (advisory locks, LISTEN/NOTIFY); HNSW vector index; fleet-wide processing ceiling.", "Architectural goal; not measured", "-"),
    ("NFR-10", "Performance", "No response-time or throughput target is specified and none was measured.", "Not verified", "-"),
    ("NFR-11", "Maintainability", "Layered packages with one-way dependencies, typed ORM models, versioned migrations and a large regression suite.", "Partially evidenced by structure and tests", "-"),
    ("NFR-12", "Usability and localisation", "English/Arabic interfaces with RTL and explicit empty, loading and error states.", "Implemented; no usability study", "-"),
    ("NFR-13", "Accessibility", "Modal focus management is tested; no WCAG conformance audit has been performed.", "Not verified", "Modal.focus.test.tsx"),
    ("NFR-14", "Configuration safety", "The settings validator refuses to start when a feature is enabled without its required configuration.", "Supported by implementation", "core/config.py"),
    ("NFR-15", "AI governance", "AI proposes, a person confirms, the backend authorises and executes; provider calls and AI actions are recorded.", "Supported by implementation and tests", "test_ai_traceability_policy, test_voice_human_authority"),
]


def _fr_blocks():
    out = []
    for title, items in FR_GROUPS:
        out.append(("h3", title))
        out.append(("bullets", [f"**{i} - {t}.** {txt} _{{Status: {st}.}}_" for (i, t, txt, _a, _e, _x, st, _s) in items]))
    return out


def chapter3(E):
    nfr_by_class = {}
    for i, c, txt, cls, _e in NFR:
        nfr_by_class.setdefault(cls, []).append(f"**{i} ({c}).** {txt}")
    order = ["Supported by implementation and tests", "Supported by implementation", "Implemented; limits configured, not load-tested",
             "Partially evidenced by structure and tests", "Implemented; no usability study", "Architectural goal; not measured", "Not verified"]
    nfr_blocks = []
    for cls in order:
        if cls in nfr_by_class:
            nfr_blocks += [("lead", f"_{{{cls}:}}_"), ("bullets", nfr_by_class[cls])]
    return [
        ("h1", "Chapter 3: System Requirements and Analysis"), ("chap", "3"),
        ("lead", "Requirements were derived from the original proposal and checked against the implemented code. Each requirement "
                 "carries a status: **Implemented** means code and automated tests exist; **Partial** means part of it is missing "
                 "or in transition; **disabled by default** means the capability exists but is switched off. The traceability "
                 "workbook (Constructs_Traceability_Matrix.xlsx) maps every requirement to source files and tests."),
        ("h2", "3.1 Stakeholder Analysis"),
        ("p", "{fig:context} places Constructs in its environment. Internal users belong to the consulting office; external users "
              "belong to other organisations on a project and are always constrained by the party they represent. OpenAI, "
              "Firebase Cloud Messaging and SMTP are optional external services; the platform runs without them, with the "
              "corresponding features reported as unavailable."),
        ("fig", "context", D + "01_context.png", "System context of Constructs"),
        ("p", "The stakeholders correspond to the role templates seeded by the system. An office may rename or re-permission any "
              "template except the undeletable Office Administrator, so the list below describes defaults rather than fixed roles."),
        ("bullets", [
            "**Office administrator (internal)** - accounts, roles and access governance; does not take part in project work by default.",
            "**Office leadership (internal: General Manager, Technical Director)** - oversight of every project and technical approval authority such as approving design changes.",
            "**Project manager (internal)** - plans the project, assigns members and tasks, edits the schedule and reviews work.",
            "**Engineers (internal: senior, engineer, BIM engineer, CAD technician, surveyor)** - carry out assigned tasks, report progress and issues, upload models and documents; drafting roles hold no review authority by default.",
            "**Site engineer (internal)** - reports from the field with site reports, photographs and voice.",
            "**Document control and administrative staff (internal)** - maintain the document library.",
            "**Client representative (external)** - follows progress, spending and evidence and raises owner requests.",
            "**Main contractor and subcontractors (external)** - update assigned work and submit evidence; can never certify work or grant access.",
            "**External reviewer (external)** - reviews shared material without certification authority.",
        ]),
        ("h2", "3.2 Functional Requirements"),
        ("p", f"Thirty functional requirements are grouped by functional area. Twenty-seven are implemented and tested; FR-08 and "
              "FR-19 are partial, and FR-23 is implemented but disabled by default. Requirements from the proposal that were not "
              "built are listed at the end of this section rather than presented as capabilities."),
    ] + _fr_blocks() + [
        ("p", "**Partial and disabled requirements.** FR-08: budget fields and cost-validation review exist, but the proposal's "
              "expense records linked to evidence, with an owner-facing spending breakdown, are not implemented. FR-19: geometry "
              "generation is implemented and tested, and the last commit contains a Three.js viewer, but the current working tree "
              "deletes the viewer component and its dependency (an uncommitted change), so 3D viewing is in transition. FR-23: "
              "event-driven analysis is tested but switched off (`AGENT_AUTO_ANALYSIS_ENABLED=false`)."),
        ("p", "**Proposal items not implemented.** Expense tracking linked to evidence (above), DWG interpretation (explicitly "
              "excluded in the proposal), detection of contradictions between two documents (the document-consistency agent "
              "states that this is not implemented), and an additional Telegram notification channel, which is declared in an "
              "enumeration but has no provider."),
        ("h2", "3.3 Non-Functional Requirements"),
        ("p", "No numerical quality targets were specified in the proposal, and none are invented here. The non-functional "
              "requirements below are grouped by the strength of the available evidence."),
    ] + nfr_blocks + [
        ("h2", "3.4 System Models and Diagrams"),
        ("h3", "3.4.1 Use case diagrams"),
        ("p", "The use cases are split into two diagrams to keep them legible. {fig:uc1} covers project execution and "
              "collaboration, and {fig:uc2} covers engineering information, AI assistance and administration. Each actor stands "
              "for \"a user whose effective permissions include the required permission\", because roles are configurable."),
        ("fig", "uc1", D + "02a_usecase_project.png", "Use cases - project execution and collaboration"),
        ("fig", "uc2", D + "02b_usecase_intelligence.png", "Use cases - engineering information, AI assistance and administration"),
        ("h3", "3.4.2 Key use case descriptions"),
        ("lead", "**UC-A: Submit a task for review and decide.**"),
        ("bullets", [
            "_{Actors:}_ assigned engineer; reviewer holding `task.review`.",
            "_{Precondition:}_ the task is IN_PROGRESS or REWORK_REQUIRED and requires review.",
            "_{Main flow:}_ the engineer submits with a completion note; the status becomes UNDER_REVIEW and the reviewer is notified; the reviewer starts the review and approves; the status becomes DONE and an audit entry is written.",
            "_{Alternatives:}_ the reviewer rejects with required corrections (REWORK_REQUIRED) or requests clarification, which the engineer answers before the decision.",
            "_{Postcondition:}_ the review history remains in `task_reviews`; progress cannot change while the task is under review or done.",
        ]),
        ("lead", "**UC-B: Compare model revisions and review their impact.**"),
        ("bullets", [
            "_{Actors:}_ BIM engineer (compare permission); project manager (review permission).",
            "_{Precondition:}_ both versions belong to the same model group and have finished processing.",
            "_{Main flow:}_ the engineer requests the comparison; the system records element changes, creates impact suggestions and notifies the project manager; the project manager acknowledges or dismisses each suggestion and adjusts the affected tasks.",
            "_{Alternatives:}_ versions from different groups or still processing are rejected; a model without stable GlobalIds yields a comparison marked LOW confidence.",
        ]),
        ("lead", "**UC-C: Ask a question about project documents.**"),
        ("bullets", [
            "_{Actors:}_ any project member; OpenAI API as secondary actor.",
            "_{Precondition:}_ RAG is enabled and the project has indexed sources the user may read.",
            "_{Main flow:}_ the system determines readable sources, embeds the question, retrieves the top passages from those sources only, and returns the model's answer with citations built from the retrieved records.",
            "_{Alternatives:}_ with no readable sources, a not-found answer is returned without any model call; if the model reports insufficient context, the user sees that the information was not found.",
        ]),
        ("h3", "3.4.3 Activity diagram - task execution and review"),
        ("p", "{fig:act_task} models UC-A including the blocker loop and the two completion paths. Its guard conditions are "
              "the checks performed by the task endpoints."),
        ("fig", "act_task", D + "03_activity_task_review.png", "Activity diagram - task execution and review"),
        ("h3", "3.4.4 State machine diagrams"),
        ("p", "Three entities have lifecycles whose transitions are enforced in code. Tasks ({fig:st_task}) follow the transitions "
              "of the task endpoints. IFC model versions ({fig:st_ifc}) and ingested files ({fig:st_ing}) are governed by "
              "explicit transition tables that reject any unlisted change, which prevents a late or duplicated worker from "
              "overwriting a terminal state."),
        ("fig", "st_task", D + "09_state_task.png", "State machine - task status"),
        ("fig", "st_ifc", D + "10_state_ifc.png", "State machine - IFC model version processing status"),
        ("fig", "st_ing", D + "11_state_ingestion.png", "State machine - ingested file status (PARTIAL is a usable outcome with reduced capability)"),
    ]


def chapter4(E):
    return [
        ("h1", "Chapter 4: System Design and Architecture"), ("chap", "4"),
        ("lead", "This chapter reconstructs the architecture from the repository: tiers and components, deployment, the data "
                 "model, interfaces, the main data flows, end-to-end scenarios and the design patterns the code actually uses."),
        ("h2", "4.1 High-Level Architecture"),
        ("p", "Constructs is a three-tier client-server system ({fig:arch}). The web and mobile clients call one FastAPI backend "
              "over HTTPS with JSON and bearer tokens. Inside the backend, the API layer handles routing, validation and status "
              "codes; the service layer holds all domain logic, policies and integrations; and the data layer consists of typed "
              "SQLAlchemy models. A separate worker process runs the same code against the same database and executes queued "
              "jobs, so heavy work never runs on the request path."),
        ("fig", "arch", D + "13_architecture.png", "High-level architecture"),
        ("p", "One deliberate decision shapes the whole design: PostgreSQL is used not only for data but also as the job queue, "
              "the lock service, the realtime message bus and the vector index. This keeps the operation of the system to a "
              "single stateful service, which suits a small team. The cost is that throughput is bounded by the database; the "
              "code mitigates this with `SKIP LOCKED` claiming, advisory locks and an HNSW index, and the storage interfaces "
              "(`VectorStore`, `PrivateStorage`) leave room to move to external services later."),
        ("p", "{fig:components} shows the main backend components. API modules depend on domain services; domain services use "
              "three cross-cutting services - authorization, the job queue and audit/domain events. Authorization is called on "
              "every protected path, including voice, AI tools, agents and RAG; drawing all those edges would make the diagram "
              "unreadable, so they are summarised in a note."),
        ("fig", "components", D + "14_components.png", "Backend component diagram"),
        ("p", "The deployment in `docker-compose.yml` is shown in {fig:deploy}. Four services start by default - database, API, "
              "worker and web frontend; a fifth, `flutter-tools`, runs only under the `mobile-tools` profile for repeatable mobile "
              "builds. Named volumes hold the database and uploaded files, and the Firebase credential is mounted read-only from "
              "a git-ignored directory. The single container start sequence - wait for the database, migrate, seed roles, "
              "optional demo seed, serve - is guarded by a test so that every environment starts the same way."),
        ("fig", "deploy", D + "15_deployment.png", "Deployment diagram (Docker Compose)"),
        ("h2", "4.2 Detailed Design, Data Design, and Interface Design"),
        ("h3", "4.2.1 Backend structure"),
        ("p", "The backend packages have one-way dependencies (API, then services, then models). `app/api` contains only the HTTP "
              "surface; `app/schemas` holds Pydantic request and response contracts; `app/services` contains the domain logic "
              "and integrations; `app/models` declares the ORM entities; `app/core` holds configuration, security primitives, "
              "dependencies and the permission catalogue; `app/ai` contains the model-facing parts of the voice pipeline; and "
              "`app/db` contains session management, the administrator bootstrap and the demo seed."),
        ("h3", "4.2.2 Data design"),
        ("p", f"The database declares {E['tables']} tables with consistent conventions: UUID primary keys, creation and update "
              "timestamps from mixins, JSONB for open-ended payloads such as IFC properties and AI evidence, check constraints for "
              "closed vocabularies, and partial unique indexes for rules such as \"unique per organisation\". The four "
              "entity-relationship diagrams below cover the core of each domain and abbreviate attributes to those that carry "
              "relationships or business meaning; the complete schema is defined by the migrations."),
        ("fig", "er_id", D + "16a_er_identity.png", "ER diagram - identity, organisation and RBAC"),
        ("p", "In {fig:er_id}, every user has exactly one office role (`users.org_role_id` is mandatory and is the only source of "
              "office authority). `role_permissions` stores configurable grants and `user_permission_overrides` stores explicit "
              "allow or deny decisions, optionally limited to one project."),
        ("fig", "er_proj", D + "16b_er_projects.png", "ER diagram - projects, parties, tasks and field records"),
        ("p", "In {fig:er_proj}, `project_members.party_id` is empty for office staff and points to a `project_parties` row for "
              "an external participant; this single column is how the authorization service decides whether a person is "
              "external on a given project. `task_dependencies` stores the precedence network used for CPM."),
        ("fig", "er_doc", D + "16c_er_documents.png", "ER diagram - documents, ingestion, retrieval chunks and jobs"),
        ("p", "{fig:er_doc} shows that a retrieval chunk belongs either to a library document or to an ingested file and carries "
              "the project id, so retrieval can filter by project and by readable source in one indexed query. The embedding is a "
              "`vector(1536)` column with an HNSW cosine index. `document_party_shares` implements deny-by-default external "
              "access: without a row, a contractor cannot see a document."),
        ("fig", "er_ifc", D + "16d_er_ifc.png", "ER diagram - IFC model groups, versions, elements and analysis results"),
        ("p", "In {fig:er_ifc}, a model group (for example the structural model) holds numbered versions. Elements keep their IFC "
              "GlobalId, which allows two versions to be compared element by element. Comparison output is normalised into "
              "change records, impact suggestions and coordination findings, each reviewable individually. `ifc_entity_links` "
              "(not drawn, to keep the diagram readable) links an element to a task, issue, milestone, document, site report, field "
              "submission or media asset; these links drive the high-confidence impact suggestions."),
        ("h3", "4.2.3 Interface design"),
        ("p", f"The REST API is mounted under `/api/v1` and exposes {E['routes']} route handlers in {E['router_modules']} router "
              "modules. Login uses the OAuth2 password form; every other call carries a bearer access token. The largest groups "
              "are IFC (53 handlers: model groups, versions, hierarchy, elements, geometry, comparisons, impacts, links, "
              "suggestions, findings), tasks (31), projects (20), collaboration (17), messages (16), users and site reports "
              "(14 each) and voice (13). Live updates use `POST /events/ticket` followed by `GET /events/stream`, because a "
              "browser `EventSource` cannot send an authorization header."),
        ("p", "The web client is organised by feature (`src/features/<domain>`), with 23 feature folders, TanStack Query for "
              "server state, Zustand stores and lazily loaded routes under one URL scheme per project, so navigation does not "
              "depend on role names. Route guards hide what a user cannot do, but they are presentation only: the server "
              "re-checks every call. The mobile client has 17 feature folders - tasks, site reports, field evidence, voice, IFC "
              "list, messages, notifications and others - and uses Riverpod, go_router and Dio, keeping tokens in secure storage."),
        ("h2", "4.3 Data Flow and Process Models"),
        ("p", "Every protected request passes through permission resolution ({fig:authz}). Overrides are applied before the "
              "ceilings, so even a mistaken grant to an external participant is removed before the check is made."),
        ("fig", "authz", D + "19_activity_authz.png", "Activity diagram - effective permission resolution"),
        ("p", "{fig:seq_auth} shows login and transparent token refresh. Because refresh tokens are single-use, the web client "
              "shares one in-flight refresh among concurrent requests that receive a 401 response; otherwise the second request "
              "would present an already revoked token."),
        ("fig", "seq_auth", D + "05_seq_auth.png", "Sequence diagram - login, authorised request and token refresh"),
        ("p", "{fig:seq_jobs} shows the background job lifecycle. A job row is inserted in the same transaction as the upload or "
              "event that caused it, so a rolled-back request leaves no orphan work; workers claim jobs with `FOR UPDATE SKIP "
              "LOCKED`, and a transaction-scoped advisory lock enforces a fleet-wide concurrency ceiling."),
        ("fig", "seq_jobs", D + "08_seq_jobs.png", "Sequence diagram - durable background job processing"),
        ("p", "{fig:dfd} is a level-1 data flow diagram of file ingestion and document question answering. The only data that "
              "leaves the platform is text sent to the OpenAI API for embedding and answering, and only when RAG is enabled."),
        ("fig", "dfd", D + "18_dfd_ingestion.png", "Level-1 data flow diagram - file ingestion and document question answering"),
        ("p", "{fig:act_ifc} follows an IFC upload from the request into the worker. The upload transaction stores the file and "
              "queues a job; parsing happens later in an isolated subprocess, so a malformed or oversized model cannot exhaust "
              "the API process. {fig:revision} then shows what happens when two processed versions are compared."),
        ("fig", "act_ifc", D + "04_activity_ifc.png", "Activity diagram - IFC upload, processing and coordination"),
        ("fig", "revision", D + "21_revision_impact.png", "Activity diagram - revision comparison and impact suggestions"),
        ("h2", "4.4 End-to-End Scenarios"),
        ("p", "The following scenarios show how modules cooperate along paths that exist in the code. They are described from "
              "the implementation and its integration tests; they have not been validated with real users."),
        ("h3", "4.4.1 Scenario 1 - from a contract PDF to a cited answer"),
        ("nums", [
            "A document controller uploads a contract PDF; the ingestion pipeline validates it, computes its checksum, classifies it and queues processing (FR-13).",
            "The worker extracts the text layer; because automatic indexing is on, an indexing job splits the text into overlapping chunks, embeds them and stores them with page numbers (FR-20).",
            "An engineer asks what retention percentage applies. The knowledge router recognises a document question (FR-21); authorization computes which documents the engineer may read; retrieval searches only those chunks.",
            "The model answers from the numbered passages; Constructs attaches citations built from the retrieved chunk records, so each citation points to a real document and page ({fig:seq_rag}).",
        ]),
        ("h3", "4.4.2 Scenario 2 - from a model revision to affected work"),
        ("nums", [
            "A BIM engineer uploads revision B of the structural model; the worker parses it and the version becomes READY (FR-15).",
            "The engineer compares revision A with B. Elements are matched by GlobalId; a column whose placement changed is recorded as MOVED with HIGH severity (FR-17).",
            "The column is linked to a task, so an impact suggestion with confidence 1.0 is created on that task; changed elements without links produce lower-confidence discipline suggestions. The project manager is notified.",
            "The project manager acknowledges the suggestion and reschedules the task; a coordination finding on a duct crossing a beam is turned into an issue linked back to the element (FR-18).",
        ]),
        ("h3", "4.4.3 Scenario 3 - from a voice report on site to an updated plan"),
        ("nums", [
            "A site engineer records, in Arabic, that the ground-floor slab formwork is seventy percent complete (FR-25).",
            "The audio is stored privately, transcribed and analysed; the router identifies a progress update rather than a question, and the matcher resolves the task ({fig:seq_voice}).",
            "The engineer reviews the proposed draft and confirms it within ten minutes; the action service re-checks permissions and updates the task, recording an audit entry and the before and after state.",
            "The project manager receives a notification and the open web client refreshes through a realtime hint ({fig:seq_notify}).",
        ]),
        ("landscape", True),
        ("p", "The three sequence diagrams referenced by the scenarios are wide and are therefore placed on landscape pages. "
              "{fig:seq_rag} shows retrieval-augmented answering: authorization is resolved first and passed into retrieval as two "
              "explicit id sets, which have no default of \"all documents\"."),
        ("fig", "seq_rag", D + "06_seq_rag.png", "Sequence diagram - retrieval-augmented document question answering"),
        ("p", "{fig:seq_voice} shows a voice command. The model determines intent and entities; deterministic routing decides "
              "between a question and a change; a change is executed only after confirmation and a fresh permission check."),
        ("fig", "seq_voice", D + "07_seq_voice.png", "Sequence diagram - voice command to confirmed action"),
        ("p", "{fig:seq_notify} shows notification fan-out. The notification row and the realtime event are written in the "
              "caller's transaction; PostgreSQL delivers NOTIFY messages only after commit, and events carry only identifiers so "
              "that clients re-fetch data through authorised REST calls."),
        ("fig", "seq_notify", D + "20_seq_notify.png", "Sequence diagram - notification, realtime and push fan-out"),
        ("landscape", False),
        ("h2", "4.5 Design Patterns and Justifications"),
        ("p", "Patterns are named only where the code clearly matches their intent."),
        ("bullets", [
            "**Layered architecture** - `app/api` to `app/services` to `app/models`; the same services are reused by REST, voice, the MCP tool surface and agents.",
            "**Service Layer** {cite:fowler2002} - each business rule lives in one service (for example `authorization`, `task_progress_service`, `notification_service`) regardless of the entry point.",
            "**Unit of Work** {cite:fowler2002} - one SQLAlchemy session per request; a domain change, its audit entry, its job and its event commit together.",
            "**Strategy through protocols** {cite:gof1994} - `VectorStore` with `PgVectorStore`, `PrivateStorage` with a local implementation, and a push provider base; tests substitute fakes without touching callers.",
            "**Registry / table-driven dispatch** - 20 declared AI tools, 5 declared agents, ingestion processors and job handlers; anything not registered is unreachable.",
            "**State machine as transition table** - `VERSION_TRANSITIONS`, the ingestion `TRANSITIONS` table and the voice command transitions reject illegal state changes centrally.",
            "**Publish-subscribe** - domain events feed agents and the realtime publisher without coupling producers to consumers.",
            "**Transactional outbox (simplified)** - jobs and notifications are written in the causing transaction and acted on only after commit.",
            "**Interceptor** - the web and mobile HTTP clients attach tokens and perform single-flight refresh in one place.",
        ]),
    ]
