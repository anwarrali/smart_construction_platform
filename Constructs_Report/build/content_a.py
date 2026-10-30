"""References, abstract, Chapter 1 (Introduction) and Chapter 2 (Literature)."""

# Verified on 24 Oct 2026: DOIs via the Crossref API, arXiv ids via the arXiv
# API, RFCs via rfc-editor.org, ISBNs via Open Library, product capabilities via
# the vendors' own help/support pages (see EVIDENCE_AND_VERIFICATION_SUMMARY.md).
REFERENCES = {
    "mgi2017": 'McKinsey Global Institute, "Reinventing construction: A route to higher productivity," McKinsey & Company, Feb. 2017. [Online]. Available: https://www.mckinsey.com/capabilities/operations/our-insights/reinventing-construction-through-a-productivity-revolution',
    "shen2010": 'W. Shen _{et al.}_, "Systems integration and collaboration in architecture, engineering, construction, and facilities management: A review," _{Advanced Engineering Informatics}_, vol. 24, no. 2, pp. 196-207, 2010, doi: 10.1016/j.aei.2009.09.001.',
    "oraee2019": 'M. Oraee, M. R. Hosseini, D. J. Edwards, H. Li, E. Papadonikolaki, and D. Cao, "Collaboration barriers in BIM-based construction networks: A conceptual model," _{International Journal of Project Management}_, vol. 37, no. 6, pp. 839-854, 2019, doi: 10.1016/j.ijproman.2019.05.004.',
    "pmbok": "Project Management Institute, _{A Guide to the Project Management Body of Knowledge (PMBOK Guide)}_, 7th ed. Newtown Square, PA, USA: PMI, 2021, ISBN 978-1-62825-664-2.",
    "kelley1959": 'J. E. Kelley and M. R. Walker, "Critical-path planning and scheduling," in _{Proc. Eastern Joint IRE-AIEE-ACM Computer Conf.}_, Boston, MA, USA, Dec. 1959, pp. 160-173, doi: 10.1145/1460299.1460318.',
    "sacks2018": "R. Sacks, C. Eastman, G. Lee, and P. Teicholz, _{BIM Handbook: A Guide to Building Information Modeling for Owners, Designers, Engineers, Contractors, and Facility Managers}_, 3rd ed. Hoboken, NJ, USA: Wiley, 2018, ISBN 978-1-119-28753-7.",
    "azhar2011": 'S. Azhar, "Building information modeling (BIM): Trends, benefits, risks, and challenges for the AEC industry," _{Leadership and Management in Engineering}_, vol. 11, no. 3, pp. 241-252, 2011, doi: 10.1061/(ASCE)LM.1943-5630.0000127.',
    "iso16739": "International Organization for Standardization, _{ISO 16739-1:2018 Industry Foundation Classes (IFC) for data sharing in the construction and facility management industries - Part 1: Data schema}_, Geneva, Switzerland, 2018 (withdrawn 2024; superseded by ISO 16739-1:2024).",
    "akponeware2017": 'O. Akponeware and Z. A. Adamu, "Clash detection or clash avoidance? An investigation into coordination problems in 3D BIM," _{Buildings}_, vol. 7, no. 3, p. 75, 2017, doi: 10.3390/buildings7030075.',
    "awe2025": 'M. Awe, A. Malhi, M. Budka, N. Mavengere, and B. Dave, "Towards 4D BIM: A systematic literature review on challenges, strategies and tools in leveraging AI with BIM," _{Buildings}_, vol. 15, no. 7, p. 1072, 2025, doi: 10.3390/buildings15071072.',
    "wefki2024": 'H. Wefki, M. Elnahla, and E. Elbeltagi, "BIM-based schedule generation and optimization using genetic algorithms," _{Automation in Construction}_, vol. 164, p. 105476, 2024, doi: 10.1016/j.autcon.2024.105476.',
    "sandhu1996": 'R. S. Sandhu, E. J. Coyne, H. L. Feinstein, and C. E. Youman, "Role-based access control models," _{Computer}_, vol. 29, no. 2, pp. 38-47, Feb. 1996, doi: 10.1109/2.485845.',
    "ferraiolo2001": 'D. F. Ferraiolo, R. Sandhu, S. Gavrila, D. R. Kuhn, and R. Chandramouli, "Proposed NIST standard for role-based access control," _{ACM Trans. Information and System Security}_, vol. 4, no. 3, pp. 224-274, 2001, doi: 10.1145/501978.501980.',
    "owasp": 'OWASP Foundation, "OWASP Top 10:2021." [Online]. Available: https://owasp.org/Top10/',
    "saka2024": 'A. Saka _{et al.}_, "GPT models in construction industry: Opportunities, limitations, and a use case validation," _{Developments in the Built Environment}_, vol. 17, p. 100300, 2024, doi: 10.1016/j.dibe.2023.100300.',
    "erfani2026": 'A. Erfani and A. Mansouri, "Applications of multimodal large language models in construction industry," _{Advanced Engineering Informatics}_, vol. 69, p. 103909, 2026, doi: 10.1016/j.aei.2025.103909.',
    "zheng2023": 'J. Zheng and M. Fischer, "Dynamic prompt-based virtual assistant framework for BIM information search," _{Automation in Construction}_, vol. 155, p. 105067, 2023, doi: 10.1016/j.autcon.2023.105067.',
    "lewis2020": 'P. Lewis _{et al.}_, "Retrieval-augmented generation for knowledge-intensive NLP tasks," in _{Advances in Neural Information Processing Systems 33 (NeurIPS 2020)}_, 2020. arXiv:2005.11401.',
    "gao2023": 'Y. Gao _{et al.}_, "Retrieval-augmented generation for large language models: A survey," arXiv:2312.10997, Dec. 2023.',
    "ji2023": 'Z. Ji _{et al.}_, "Survey of hallucination in natural language generation," _{ACM Computing Surveys}_, vol. 55, no. 12, pp. 1-38, 2023, doi: 10.1145/3571730.',
    "malkov2020": 'Y. A. Malkov and D. A. Yashunin, "Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs," _{IEEE Trans. Pattern Analysis and Machine Intelligence}_, vol. 42, no. 4, pp. 824-836, 2020, doi: 10.1109/TPAMI.2018.2889473.',
    "rfc7519": 'M. Jones, J. Bradley, and N. Sakimura, "JSON Web Token (JWT)," IETF RFC 7519, May 2015.',
    "rfc6749": 'D. Hardt, Ed., "The OAuth 2.0 Authorization Framework," IETF RFC 6749, Oct. 2012.',
    "rfc9106": 'A. Biryukov, D. Dinu, D. Khovratovich, and S. Josefsson, "Argon2 memory-hard function for password hashing and proof-of-work applications," IETF RFC 9106, Sep. 2021.',
    "fielding2000": 'R. T. Fielding, "Architectural styles and the design of network-based software architectures," Ph.D. dissertation, Univ. of California, Irvine, CA, USA, 2000. [Online]. Available: https://ics.uci.edu/~fielding/pubs/dissertation/top.htm',
    "fowler2002": "M. Fowler, _{Patterns of Enterprise Application Architecture}_. Boston, MA, USA: Addison-Wesley, 2002, ISBN 978-0-321-12742-6.",
    "gof1994": "E. Gamma, R. Helm, R. Johnson, and J. Vlissides, _{Design Patterns: Elements of Reusable Object-Oriented Software}_. Reading, MA, USA: Addison-Wesley, 1994, ISBN 978-0-201-63361-0.",
    "cohn2010": "M. Cohn, _{Succeeding with Agile: Software Development Using Scrum}_. Upper Saddle River, NJ, USA: Addison-Wesley, 2010, ISBN 978-0-321-57936-2.",
    "osterwalder2010": "A. Osterwalder and Y. Pigneur, _{Business Model Generation}_. Hoboken, NJ, USA: Wiley, 2010, ISBN 978-0-470-87641-1.",
    "pg_select": 'PostgreSQL Global Development Group, "SELECT - The locking clause," _{PostgreSQL 15 Documentation}_. [Online]. Available: https://www.postgresql.org/docs/15/sql-select.html',
    "pg_locks": 'PostgreSQL Global Development Group, "Explicit locking - Advisory locks," _{PostgreSQL 15 Documentation}_. [Online]. Available: https://www.postgresql.org/docs/15/explicit-locking.html',
    "pg_notify": 'PostgreSQL Global Development Group, "NOTIFY," _{PostgreSQL 15 Documentation}_. [Online]. Available: https://www.postgresql.org/docs/15/sql-notify.html',
    "whatwg_sse": 'WHATWG, "HTML Living Standard - Server-sent events." [Online]. Available: https://html.spec.whatwg.org/multipage/server-sent-events.html',
    "pgvector": 'A. Kane and contributors, "pgvector: Open-source vector similarity search for Postgres," GitHub repository. [Online]. Available: https://github.com/pgvector/pgvector',
    "ifcopenshell": 'IfcOpenShell contributors, "IfcOpenShell - The open source IFC toolkit and geometry engine." [Online]. Available: https://ifcopenshell.org/',
    "fastapi": 'S. Ramirez, "FastAPI documentation." [Online]. Available: https://fastapi.tiangolo.com/',
    "react": 'Meta Platforms, Inc., "React documentation." [Online]. Available: https://react.dev/',
    "flutter": 'Google LLC, "Flutter documentation." [Online]. Available: https://docs.flutter.dev/',
    "openai_emb": 'OpenAI, "Vector embeddings," _{OpenAI Platform Documentation}_. [Online]. Available: https://platform.openai.com/docs/guides/embeddings',
    "procore_assist": 'Procore Technologies, Inc., "More about Assist," _{Procore Support}_. [Online]. Available: https://support.procore.com/products/online/user-guide/project-level/assist/more-about-assist',
    "procore_models": 'Procore Technologies, Inc., "View coordination issues in the model viewer," _{Procore Support}_. [Online]. Available: https://support.procore.com/products/online/user-guide/project-level/models/tutorials/view-coordination-issues-in-the-model-viewer',
    "procore_home": 'Procore Technologies, Inc., "Procore - Construction management software," product website. [Online]. Available: https://www.procore.com/',
    "acc_coord": 'Autodesk, Inc., "About Model Coordination," _{Autodesk Help}_. [Online]. Available: https://help.autodesk.com/cloudhelp/ENU/Coord-GS/files/About_Model_Coord.html',
    "acc_assistant": 'Autodesk, Inc., "GCs, meet Autodesk Assistant - a smart tool that can help you find answers," _{Autodesk Construction Blog}_. [Online]. Available: https://www.autodesk.com/blogs/construction/gcs-meet-autodesk-assistant-a-smart-tool-that-can-help-you-find-answers/',
    "acc_home": 'Autodesk, Inc., "Autodesk construction solutions (Autodesk Construction Cloud / Forma)," product website. [Online]. Available: https://construction.autodesk.com/',
    "aconex": 'Oracle Corporation, "Oracle Aconex," product website. [Online]. Available: https://www.oracle.com/construction-engineering/aconex/',
    "p6": 'Oracle Corporation, "Primavera P6 Enterprise Project Portfolio Management," product website. [Online]. Available: https://www.oracle.com/construction-engineering/primavera-p6/',
}


def front_abstract(E):
    return [
        ("p", "Construction projects are delivered by owners, consulting engineers, contractors and specialist disciplines that "
              "exchange large volumes of interdependent information: building models, drawings, specifications, schedules, site "
              "evidence and decisions. Because this information usually lives in separate tools and conversations, a change in "
              "the design is often discovered on site rather than in the plan. This report presents **Constructs**, a web and "
              "mobile platform that keeps design information and project execution in one permission-controlled record and "
              "provides concrete mechanisms that connect them."),
        ("p", "Constructs is implemented as a FastAPI backend with PostgreSQL and the pgvector extension, a durable job worker, a "
              "React web client and a Flutter mobile client. Its design-to-execution mechanisms are: IFC model processing that "
              "extracts spatial structure and elements and proposes tasks and milestones; revision comparison by IFC GlobalId with "
              "impact suggestions on linked or same-discipline tasks; interference candidates that can be turned into issues; "
              "retrieval-augmented question answering over authorised documents whose citations are built from retrieved records; "
              "and a bilingual voice workflow that converts spoken site reports into confirmed task updates. A single "
              "permission-resolution function governs every one of these paths, with ceilings that keep external parties away "
              "from certification and access-governance authority."),
        ("p", f"The automated test suites were executed for this report: {E['backend_summary']}; {E['frontend_summary']}; and "
              f"{E['mobile_summary']}. These results verify behaviour at the unit and API-integration level; end-to-end user "
              "workflows, live AI-provider behaviour, performance and usability have not yet been systematically evaluated, and "
              "the report states these limits explicitly."),
        ("p", "**Keywords:** construction management, design-to-execution integration, BIM, IFC, role-based access control, "
              "critical path method, retrieval-augmented generation."),
    ]


def chapter1(E):
    return [
        ("h1", "Chapter 1: Introduction"), ("chap", "1"),
        ("lead", "This chapter introduces Constructs, defines the problem it addresses and why that problem matters, states the "
                 "project's objectives and scope, and lists the constraints under which it was developed."),
        ("h2", "1.1 Project Overview"),
        ("p", "Constructs is a construction intelligence and collaboration platform for a consulting engineering office that "
              "supervises building projects together with its client and its contractors. It began as the \"Smart Construction "
              "Platform\" proposal and is referred to in parts of its user interface as StructIQ; this report uses the official "
              "project name, Constructs, throughout."),
        ("p", "The platform's central idea is that design information and execution information should not live in separate "
              "worlds. A building model revision, a clause in a specification or a design change should be connected to the tasks, "
              "issues and milestones it affects, and a report from the site should update the plan it refers to. {fig:concept} "
              "summarises the mechanisms that Constructs implements for this purpose; each is described in detail in Chapters 4 "
              "and 5."),
        ("fig", "concept", "../diagrams/png/00_concept.png", "Design-to-execution mechanisms implemented in Constructs"),
        ("p", "The system is organised as a monorepo with four runtime parts: a REST API built with FastAPI {cite:fastapi}; a "
              "PostgreSQL 15 database with the pgvector extension {cite:pgvector}; a background worker that executes long-running "
              "jobs such as IFC parsing and document indexing; and two clients - a React 19 web application {cite:react} for office "
              "work and a Flutter application {cite:flutter} for field work. Both clients support English and Arabic with "
              "right-to-left layout."),
        ("p", f"The implementation is substantial for a graduation project. At the time of writing, the backend contains "
              f"{E['py_modules']} Python modules (about {E['backend_loc']} lines), exposes {E['routes']} HTTP route handlers and "
              f"declares {E['tables']} database tables managed by {E['migrations']} Alembic migrations; the web client has "
              f"{E['fe_files']} TypeScript files and the mobile client {E['dart_files']} Dart files. These figures were counted from "
              "the working tree and are reported to convey scale, not quality."),
        ("h2", "1.2 Objectives and Scope"),
        ("p", "The objectives below restate the proposal's goals in a form that can be checked against the implementation. "
              "Chapter 6 evaluates each of them."),
        ("bullets", [
            "**O1 - One connected project record:** projects, parties, members, tasks, milestones, documents, models, site reports, issues, design changes and messages are stored and related in one system.",
            "**O2 - Configurable, safe access:** an office defines its own roles and permissions, and external parties see only what is shared with them, without code changes.",
            "**O3 - Schedule control:** tasks with all four dependency types and lags, critical path calculation and delay analysis.",
            "**O4 - Design-to-execution links:** IFC models are processed, compared across revisions and connected to tasks, issues and milestones through reviewable suggestions.",
            "**O5 - Document-grounded assistance:** questions about project documents are answered only from authorised sources, with citations a reader can check.",
            "**O6 - Field feedback:** site staff report progress, evidence and problems from a phone, including by voice in Arabic or English, with confirmation before any change.",
            "**O7 - Traceability:** important actions, AI-initiated changes and decisions are recorded and attributable to a person.",
        ]),
        ("p", "**In scope** are the web and mobile clients, the API, the database, the job worker and the AI-assisted workflows above, "
              "deployed with Docker Compose. **Out of scope** are DWG/DXF interpretation (such files are stored but not parsed), "
              "payment, ERP and accounting integrations, a production cloud deployment, iOS release builds, and autonomous AI "
              "behaviour without a human trigger."),
        ("h2", "1.3 Problem Statement"),
        ("p", "Construction is one of the largest sectors of the economy, yet its productivity has grown slowly compared with other "
              "industries; fragmentation, opacity and misaligned incentives between parties are among the reasons repeatedly "
              "identified {cite:mgi2017}. Research on systems integration in architecture, engineering and construction describes "
              "the same structural difficulty from a technical angle: many organisations and tools must create and use shared "
              "information across the project lifecycle {cite:shen2010}, and even teams that adopt BIM face persistent "
              "collaboration barriers {cite:oraee2019}."),
        ("p", "The proposal for this project observed these problems in local practice. Project information is scattered across "
              "files, messaging groups and personal phones; records that belong together - a task, the photograph that proves it, "
              "the drawing it implements and the decision that changed it - are not linked; permission checks are inconsistent, "
              "so external parties are either over- or under-informed; and when a design changes, its effect on scheduled work is "
              "recognised late."),
        ("p", "The problem this project addresses is therefore stated as: _{how can design information (models, documents, design "
              "changes) and execution information (tasks, schedules, site evidence, issues) be held in one permission-controlled "
              "system with explicit, reviewable links between them, so that design changes and site conditions reach the plan "
              "quickly, without giving AI or external parties authority they should not have?}_ Section 2.4 refines this into a "
              "specific research gap after the literature and existing products have been examined."),
        ("h2", "1.4 Significance of the Project"),
        ("p", "For a consulting office, the practical significance is a single place where a project manager can see whether the "
              "current model, the current documents and the current plan agree, and where an external contractor can participate "
              "without being able to certify their own work. For the field, it shortens the path from an observation on site to "
              "an update in the plan."),
        ("p", "Technically, the project is significant because it combines three bodies of knowledge - BIM and IFC "
              "{cite:sacks2018,iso16739}, critical path scheduling {cite:kelley1959} and role-based access control "
              "{cite:sandhu1996} - with a disciplined use of large language models. Hallucination is a documented property of "
              "generative models {cite:ji2023}; Constructs therefore uses retrieval-augmented generation {cite:lewis2020} with "
              "safeguards enforced in code, and uses deterministic rules wherever a decision can be computed rather than "
              "interpreted."),
        ("h2", "1.5 Project Constraints and Assumptions"),
        ("bullets", [
            "**Team and time:** one student developer over one academic term (the Git history shows a single author identity under two names); depth in core workflows was prioritised over breadth.",
            "**Infrastructure:** no funded hosting; development on a personal Windows workstation with Docker Desktop, so the deployment is a single-host Docker Compose stack.",
            "**External services:** AI features depend on the paid OpenAI API and push notifications on Firebase; both are optional and behind configuration switches, and the settings validator refuses incoherent configurations.",
            "**Data:** no access to real client project data; development and testing use generated fixtures and an optional demo seed.",
            "**Standards:** engineering models are exchanged as IFC, parsed with IfcOpenShell {cite:ifcopenshell}; proprietary DWG is out of scope.",
            "**Assumption - field conditions:** site users have Android or iOS phones with intermittent connectivity; the server remains the source of truth.",
            "**Assumption - AI output can be wrong:** every AI proposal is confirmed by a person and re-authorised by the backend before it changes data.",
        ]),
    ]


def chapter2(E):
    return [
        ("h1", "Chapter 2: Literature Review and Theoretical Framework"), ("chap", "2"),
        ("lead", "This chapter reviews the research that frames the problem, explains the theory used in the implementation, "
                 "compares established products using their own documentation, and derives the specific gap that Constructs "
                 "addresses."),
        ("h2", "2.1 Review of Relevant Literature"),
        ("h3", "2.1.1 Fragmentation and collaboration in construction"),
        ("p", "Project management standards describe delivery as the coordinated planning, measurement and control of work, "
              "stakeholders and risk {cite:pmbok}. Construction makes this coordination unusually hard because each project "
              "assembles a temporary network of independent organisations. Shen et al. review two decades of systems-integration "
              "and collaboration technology in architecture, engineering, construction and facilities management, and frame the "
              "goal as integrating \"people, processes, business systems, and information\" across the project lifecycle "
              "{cite:shen2010}. More recently, Oraee et al. analysed 73 journal articles on BIM-based construction networks and "
              "concluded that, although BIM's value depends on collaboration among dispersed, multi-organisation teams, members "
              "still struggle to collaborate {cite:oraee2019}. The lesson for this project is that adding a model viewer or a "
              "document store does not by itself connect people and decisions; the links between records must be designed."),
        ("h3", "2.1.2 BIM, IFC and design-to-execution integration"),
        ("p", "Building information modelling represents a facility as structured, object-based data rather than drawings "
              "{cite:sacks2018}. Azhar summarises the benefits - visualisation, clash detection, quantity take-off, better "
              "coordination - together with risks around ownership, interoperability and process change {cite:azhar2011}. The "
              "vendor-neutral exchange schema is the Industry Foundation Classes (IFC), standardised as ISO 16739-1 "
              "{cite:iso16739}; it defines spatial structure (site, building, storey, space), physical elements, properties and "
              "quantities, and gives each object a globally unique identifier (GlobalId) - the property Constructs relies on to "
              "compare revisions."),
        ("p", "Connecting models to execution is an active research area. 4D BIM adds time to the model to anticipate delays and "
              "optimise workflows; a 2025 systematic review notes that dedicated reviews of 4D BIM remain scarce and identifies "
              "lean integration, predictive strategies and ontology frameworks as key strategies {cite:awe2025}. Other work "
              "generates and optimises construction schedules directly from BIM data {cite:wefki2024}. Coordination research also "
              "warns that geometric clash detection after the fact is only part of the answer, and argues for coordinated "
              "processes that avoid clashes {cite:akponeware2017}. Constructs follows this view: interference results are "
              "presented as candidates for review, and model changes become suggestions that a responsible person accepts or "
              "dismisses."),
        ("h3", "2.1.3 Large language models and document-grounded answers"),
        ("p", "Reviews of generative AI in construction identify opportunities across the project lifecycle together with "
              "challenges that limit adoption, and validate prototypes for specific tasks {cite:saka2024}; recent surveys extend "
              "this to multimodal models in construction {cite:erfani2026}. Zheng and Fischer propose a prompt-based virtual "
              "assistant for searching BIM information {cite:zheng2023}, illustrating the interest in natural-language access to "
              "engineering data. The main technical obstacle is reliability: language models can produce fluent but unsupported "
              "statements {cite:ji2023}. Retrieval-augmented generation (RAG) conditions the answer on passages retrieved from an "
              "external corpus {cite:lewis2020}, and later surveys describe how chunking, retrieval and post-processing improve "
              "such pipelines {cite:gao2023}. Dense retrieval relies on vector embeddings {cite:openai_emb} and approximate "
              "nearest-neighbour indexes such as HNSW {cite:malkov2020}."),
        ("h3", "2.1.4 Access control and web security"),
        ("p", "Role-based access control assigns permissions to roles and roles to users, simplifying administration and "
              "supporting least privilege {cite:sandhu1996}; the NIST model formalised core RBAC, hierarchies and "
              "separation-of-duty constraints {cite:ferraiolo2001}. Broken access control is ranked first in the OWASP Top 10 "
              "{cite:owasp}. In a multi-party construction project two extensions are needed: authority that depends on the "
              "project (the same engineer may lead one project and be absent from another), and constraints no configuration may "
              "override - most importantly, a contractor must not be able to approve its own work."),
        ("h2", "2.2 Theoretical Framework"),
        ("h3", "2.2.1 Critical path method"),
        ("p", "The critical path method models a project as a directed acyclic graph of activities with durations and "
              "precedence constraints {cite:kelley1959}. A forward pass computes each activity's earliest start (ES) and "
              "earliest finish (EF = ES + d); a backward pass computes latest start (LS) and latest finish (LF); total float is "
              "TF = LS - ES, and zero-float activities form the critical path. With predecessor duration d(p), successor "
              "duration d(s) and lag L, each precedence type becomes a constraint on the successor's start:"),
        ("bullets", [
            "Finish-to-start (FS): ES(s) >= ES(p) + d(p) + L, the default construction relation;",
            "Start-to-start (SS): ES(s) >= ES(p) + L;",
            "Finish-to-finish (FF): ES(s) >= ES(p) + d(p) + L - d(s);",
            "Start-to-finish (SF): ES(s) >= ES(p) + L - d(s).",
        ]),
        ("p", "This conversion lets one forward and one backward pass handle all four types; Section 5.2 shows the implementation."),
        ("h3", "2.2.2 Permission resolution with ceilings"),
        ("p", "The authorization model can be written as a function P(u, p) returning the permissions of user u in project p: the "
              "union of the user's office-role and project-role permissions, modified by explicit allow and deny overrides (user-"
              "wide first, then project-specific), and finally restricted by ceilings that overrides cannot lift. Applying the "
              "ceilings last is what turns a configuration mistake into a refusal rather than a security breach."),
        ("h3", "2.2.3 Grounded answering"),
        ("p", "An answer is produced as a = G(q, R(q, D(u))), where R retrieves the k passages nearest to the question embedding "
              "by cosine distance, 1 - (x . y)/(||x|| ||y||), and D(u) is the part of the corpus user u may read. Restricting the "
              "corpus before retrieval, rather than filtering afterwards, guarantees that unauthorised text never reaches the model."),
        ("h3", "2.2.4 Software architecture principles"),
        ("p", "The API follows the REST style {cite:fielding2000}; login uses the OAuth 2.0 password form {cite:rfc6749}, tokens "
              "are JSON Web Tokens {cite:rfc7519} and passwords are hashed with Argon2 {cite:rfc9106}. The backend is layered and "
              "uses enterprise patterns such as Service Layer and Unit of Work {cite:fowler2002} and object-oriented patterns "
              "such as Strategy {cite:gof1994}. Asynchronous work relies on PostgreSQL row locking with SKIP LOCKED "
              "{cite:pg_select}, advisory locks {cite:pg_locks} and LISTEN/NOTIFY {cite:pg_notify}; live updates use server-sent "
              "events {cite:whatwg_sse}."),
        ("h2", "2.3 Existing Solutions and Comparative Analysis"),
        ("p", "Four established products were selected because each covers part of Constructs' scope: Procore and Autodesk's "
              "construction platform (now marketed under the Forma name) as integrated construction-management suites, Oracle "
              "Aconex for document control and correspondence, and Primavera P6 as a dedicated CPM scheduler. Capabilities were "
              "checked against the vendors' own help or product pages on 24 October 2026. \"Documented\" means the consulted page "
              "describes the capability; \"Not found\" means it was not found on the consulted pages, which is not evidence that "
              "the product lacks it."),
        ("table", "compare", "Capabilities documented by vendors, compared with Constructs (sources accessed 24 Oct 2026)",
         ["Capability", "Procore", "Autodesk (ACC / Forma)", "Oracle Aconex", "Primavera P6", "Constructs"],
         [
             ["Multi-party project workflows", "Documented {cite:procore_home}", "Documented {cite:acc_home}", "Documented {cite:aconex}", "Documented {cite:p6}", "Implemented"],
             ["CPM scheduling", "Scheduling shown {cite:procore_home}", "Schedule insights {cite:acc_home}", "Via Primavera integration {cite:aconex}", "Core capability {cite:p6}", "Implemented"],
             ["Model coordination / clashes", "Coordination issues in model viewer {cite:procore_models}", "Automatic clash detection incl. IFC {cite:acc_coord}", "BIM model coordination {cite:aconex}", "Not found", "Interference candidates (bounding boxes)"],
             ["Q&A over project documents with source links", "Assist: answers with links, respects permissions {cite:procore_assist}", "Autodesk Assistant on specifications (vendor blog) {cite:acc_assistant}", "Not found", "Not found", "RAG with record-built citations"],
             ["Model revision changes linked to scheduled tasks", "Not found", "Not found", "Not found", "Not found", "Impact suggestions by element link or discipline"],
             ["Arabic interface and spoken-Arabic input", "Not found", "Not found", "Not found", "Not found", "Implemented"],
             ["Deployment", "SaaS", "SaaS", "SaaS", "On-premise / cloud", "Self-hosted (Docker)"],
         ], [1.3, 1.05, 1.15, 1.0, 0.85, 1.15], 8.5),
        ("p", "The established products are clearly stronger in maturity, scale, integration ecosystems and depth of each "
              "individual capability. Autodesk documents automatic clash detection across RVT, DWG, NWC and IFC models with a "
              "workflow to turn clashes into issues {cite:acc_coord}; Procore documents an AI assistant that answers questions "
              "from RFIs, submittals, drawings, specifications and documents, links to its sources and respects user permissions "
              "{cite:procore_assist}. Constructs does not match these products on breadth, and its interference detection is a "
              "simpler bounding-box method."),
        ("p", "Two observations nevertheless matter for this project. First, document-grounded AI with source links is "
              "becoming a standard expectation, which supports the design choice of retrieval with verifiable citations rather "
              "than free generation. Second, on the pages consulted, none of the products documents an explicit mechanism that "
              "turns a difference between two model revisions into a reviewable suggestion on the scheduled tasks it affects. "
              "Such functionality may exist through add-ons or integrations; the claim here is limited to what the vendors' own "
              "documentation states."),
        ("h2", "2.4 Research Gap and Positioning of Constructs"),
        ("p", "The literature and the product survey separate five levels that should not be confused:"),
        ("nums", [
            "**General problem.** Construction information is fragmented across organisations and tools, and collaboration remains difficult even with BIM {cite:shen2010,oraee2019}.",
            "**Gap.** Research links BIM to schedules mainly through 4D simulation and schedule generation {cite:awe2025,wefki2024}, and commercial suites document coordination and AI search as separate tools. A lightweight, auditable link from a model revision to the specific execution records it may affect - together with permission-aware, citation-grounded document answers - is not documented as one workflow in the sources examined. This is a practical integration gap, not a claim that no such system exists.",
            "**Specific problem for Constructs.** Within one consulting office's projects, keep model revisions, documents, tasks, issues and site evidence connected, and make every cross-link reviewable by an authorised person.",
            "**Contribution.** An implemented platform in which GlobalId-based revision comparison produces impact suggestions on linked or same-discipline tasks, model processing proposes tasks and milestones, interference candidates become issues, document answers carry record-built citations, voice reports become confirmed updates, and all paths share one permission function with external-party ceilings.",
            "**Limitations.** The mechanisms are verified by automated unit and integration tests, not by field trials; the discipline fallback is a heuristic; interference detection uses bounding boxes; no user study, performance measurement or live-AI evaluation has been carried out (Section 6.4).",
        ]),
    ]
