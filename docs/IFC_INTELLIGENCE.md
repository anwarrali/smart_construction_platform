# IFC Intelligence module

The IFC workspace turns immutable IFC uploads into project-scoped facts for coordination and construction execution. It complements BIM authoring tools: geometry and design remain authoritative in Revit or the source authoring application.

## Architecture and parser choice

The module follows the existing FastAPI → service → SQLAlchemy → PostgreSQL architecture. Source files are private objects; parsing results are normalized records used by React, Flutter, task/issue workflows, notifications, and audit history. Deterministic parsing and comparisons never call an LLM.

IfcOpenShell 0.8.5 was selected because it is the mature Python IFC toolkit, publishes Python 3.12 wheels for Windows and Linux, supports the required IFC schema families, works in container images without a separate service, and is licensed under LGPL-3.0-or-later. Its installed wheel adds roughly 23 MB before transitive numeric/geometry packages. The production Dockerfile already installs `requirements.txt`, so pinning the wheel there is sufficient; no host-native IFC library is required.

## What is implemented

- Private, signature-checked `.ifc` uploads with configurable size limits and SHA-256 duplicate prevention.
- Immutable model groups and numbered versions, including active and baseline designations and optimistic locking for metadata.
- Deterministic parsing through IfcOpenShell 0.8.5 for IFC2x3, IFC4, and IFC4x3 files.
- Spatial extraction for projects, sites, buildings, storeys, spaces, and zones.
- Element classes, disciplines, systems, types, materials, property sets, quantities, placements, and representation fingerprints.
- Exact GlobalId comparison with added, removed, modified, and moved records; property, placement, and representation evidence is retained.
- Project impact proposals through explicit IFC-to-task/issue/milestone links and lower-confidence discipline matches.
- Reviewable task suggestions. Accepting a task suggestion requires the assigned Project Manager and commits the task, review decision, audit records, and task counter in one transaction.
- Deterministic coordination data-quality findings, plus structural/service interference detected from measured per-element geometry. A confirmed clash is never claimed: box overlap is reported as a candidate for review, with the verification step and a capped confidence.
- Project-scoped notifications and audit records for uploads, processing, failures, comparisons, links, and review decisions.
- React project workspace with Overview, Model Hierarchy, Elements, Disciplines, Properties and Quantities, Georeferencing, 3D Viewer, Compare Revisions, Findings, Suggestions, and advanced Technical Data views.
- Readable project overview, category statistics, model-completeness metrics, source indicators, discipline evidence, georeferencing impact, and grouped property/quantity presentation. Raw JSON is confined to collapsed advanced developer views.
- Per-tab loading, empty, partial-data, error and retry states with an error boundary, including defensive Suggestions parsing so one failed tab cannot blank or freeze the IFC workspace.
- Normalized model-quality findings grouped by rule and affected elements, plus filtered element CSV export and low-confidence revision comparison warnings when stable identifiers are unavailable.
- Flutter read-only model/version status for field users. Upload and detailed review stay on web.
- Deterministic space semantics from `IfcSpace` name, long name, object type, description, and property evidence. Every result stores category, evidence, source, confidence, and method; unmatched spaces remain `UNKNOWN`.
- Conservative normalization of generic proxy/flow elements using names, type objects, predefined types, systems, and object types. Exact IFC classes remain authoritative, and low-evidence records remain unclassified.
- A human-first version overview and spatial-detail API. Building/storey/space selection returns descendant counts, element categories, disciplines, measurement provenance, linked project-activity counts, and affected element IDs.
- A structured model-intelligence narrative generated only from parser analytics, with explicit strengths, missing information, next steps, source, and engineering-review notice.
- A redesigned React landing experience with building/storey/space summaries first, room categories, useful element categories, an interactive hierarchy inspection panel, project-activity links, measurement provenance, and technical BIM data one level deeper.

## Processing states

`UPLOADED → QUEUED → PARSING → BUILDING_HIERARCHY → EXTRACTING_ELEMENTS → EXTRACTING_PROPERTIES → QUALITY_CHECKS → ANALYZING → READY | READY_WITH_WARNINGS`

The web workflow maps these durable states to uploading, validation, schema reading, hierarchy extraction, element extraction, property and quantity extraction, model-quality checks, summary generation, and completion. Intermediate progress is committed so polling reports real server-side stage changes. Failed processing never reports a successful 100% state.

Failures retain a safe error code and support-log ID. A retry reuses the durable idempotent processing job rather than creating duplicate work.

The current background mechanism uses FastAPI background tasks and a durable database job record. For multi-node or high-volume production deployments, run the same `process_version` service from a dedicated queue worker (Celery, RQ, or a managed queue) and keep API containers stateless.

### When the parser worker dies

IfcOpenShell is a native library and does not always raise. A truncated IFC — what an interrupted export or transfer leaves behind — segfaults it, so the isolated worker exits without putting anything on the result queue.

The parent therefore polls the worker's liveness alongside the queue rather than waiting on the queue alone. A worker that has exited without reporting is classified from its exit code: `SIGKILL` becomes `IFC_PARSER_OUT_OF_MEMORY`, since the OS reclaiming a process is a memory problem and not a file problem; anything else becomes `IFC_FILE_CORRUPTED`. After the exit is seen the queue is drained for `PARSE_EXIT_GRACE_SECONDS`, because `Queue.put` is served by a feeder thread and a real result can still be in flight.

`IFC_PARSE_TIMEOUT` is now reserved for a worker that is genuinely still running at the deadline. Previously a crash consumed the entire window — ten minutes at the default `IFC_PARSE_TIMEOUT_SECONDS` — and was then reported as a timeout, which told the user to upload a smaller discipline model for a file that was never readable at any size.

### Secondary products cannot fail the model

Once extraction is committed, `process_version` produces two optional artefacts: the project-intelligence pass and the viewer geometry. Both run inside their own handlers. Neither can move an already-committed `READY` version to `FAILED`; a geometry failure is recorded as `GEOMETRY_FAILED` on the version and the hierarchy/property intelligence stays available.

## Upload and version workflow

Before selecting a file the client reads `GET /projects/{projectId}/ifc/upload-constraints`, which reports the server's own maximum file size, accepted extensions, entity limit and supported schemas. The browser refuses a wrong extension, an empty file, or a file over the limit while it is still local, so a site engineer is not asked to transmit several hundred megabytes to be told the wrong file was picked. Only checks the browser can make with certainty are made there; the STEP signature and every other rule are still enforced server-side, and a client that cannot load the constraints defers size entirely to the server rather than guessing a limit.

The web client creates a model group and posts multipart data to its versions endpoint. The backend authenticates the caller, confirms project membership/role, checks extension/MIME/STEP signature/size, streams to private storage, computes SHA-256, rejects project-wide duplicates, locks the group while assigning the next version number, commits the immutable source record, and queues parsing. Metadata may be edited with `rowVersion`; changing the source file is impossible. Only a processed version can become active or baseline. Archiving is reversible data retention, not physical deletion.

Hierarchy and element records are rebuilt idempotently on retry. The isolated parser process is terminated after `IFC_PARSE_TIMEOUT_SECONDS`, and entity count limits are checked before extraction. Original files remain available after parsing failures.

## Viewer, floors, rooms, and elements

The React workspace provides navigable hierarchy and searchable element/property/quantity views plus a real Three.js BIM mesh viewer. Storey and space IDs are stable database identifiers backed by IFC GlobalIds. Storeys, rooms, and elements can link to tasks, issues, milestones, documents, reports, field submissions, and media assets, and their project-data endpoints return those connected records.

IfcOpenShell tessellates renderable products, buildings, storeys, and spaces in an isolated child process with a hard timeout. The cached `BIMGEO1` artifact stores local-origin float32 positions, triangle indices, and an ExpressID for every vertex. The authenticated mapping endpoint resolves each ExpressID to a model revision, IFC GlobalId, database element/spatial ID, class, building, storey, space, discipline, category, and system. This avoids browser-side IFC re-parsing and keeps source IFC files private.

The viewer supports orbit, pan, zoom, fit/reset, picking, selection highlighting, focus, isolation, hiding/showing, transparency, and storey/category/discipline/system filters. Hierarchy, element-table, and AI deep links focus the same stable database IDs. Direct `IfcSpace` geometry is included when present; otherwise room focus isolates contained elements and explicitly explains the fallback. Selection loads properties, quantities, and linked project activity. Geometry, missing-asset, unsupported-model, timeout, corrupt-asset, and WebGL initialization failures have distinct states.

When geometry generation is disabled or fails, no model facts are lost: the UI presents the hierarchy/property fallback. The mobile client intentionally remains a read-only status/summary surface suitable for field use; large-model inspection, upload, comparison, and review are web workflows.

## Comparison, impact, and coordination

Comparison first matches exact GlobalIds. Added/removed IDs are definitive at identifier level. Shared IDs are marked modified or moved only when normalized property JSON, type/material/name, placement fingerprints, spatial containers, or representation fingerprints differ. Every summary contains stored change-record IDs as evidence. Representation-fingerprint changes are not advertised as measured geometric displacement.

Impact analysis prioritizes explicit links at confidence 1.0. When no explicit link exists, it may propose a discipline-level task review at confidence 0.65 and states that limitation in the explanation. Impact proposals are reviewable and do not mutate the affected record.

Coordination checks identify deterministic data-quality conflicts such as duplicated non-empty element tags. Findings retain element IDs and evidence, can be acknowledged/ignored/marked false-positive, or explicitly converted into an issue by an authorized user.

### Structural/service interference

The geometry worker now records each element's real world-coordinate extent while it tessellates, so the bounding-box evidence that geometric analysis was waiting on exists. `app/services/ifc_interference.py` uses it to detect services running through structure.

What it pairs, and why only that: `discipline` comes from the parser's evidence-backed classification, where `STRUCTURAL` is exactly the load-bearing set — beams, columns, footings, piles, members, plates. Walls and slabs classify as `ARCHITECTURAL`. That distinction is the rule's signal-to-noise control: services pass through walls and slabs by design, through sleeves and openings, so pairing against those would bury the case that actually needs an engineer — a duct through a beam — under routine penetrations.

What it refuses to claim: an axis-aligned bounding box is the smallest upright box containing an element, not the element. Two boxes can overlap while the solids inside them never touch. Every finding therefore states `claim: "potential-interference"`, carries the verification step in its evidence, and is titled "Potential interference between…". Confidence is a property of the method rather than of how bad the overlap looks: it starts at 0.55, rises to 0.70 for overlaps of 50 mm or more, and is capped there. Nothing this rule produces approaches certainty, because nothing about a box overlap justifies it. Promoting a candidate to a fact needs solid-geometry intersection, which is not implemented.

Thresholds are real distances, so the model's `LENGTHUNIT` is read and applied: a millimetre model uses millimetre thresholds. A model that does not state its unit is **not analysed at all** — the report returns `skippedReason: "UNKNOWN_LENGTH_UNIT"` rather than assuming metres, because that assumption would turn a 10 mm noise floor into 10 km. "No findings" and "could not look" are distinguishable in the report for the same reason.

Overlap below 10 mm is treated as contact or modelling noise. Elements that merely touch — a tray resting on a beam's top face — overlap by zero and are not reported. Severity follows penetration depth: 100 mm or more is `HIGH`, 30 mm `MEDIUM`, below that `LOW`. A uniform-grid broad phase keeps large models off the O(n²) path, and the queue is capped at 500 pairs so a badly coordinated federated model stays reviewable.

Re-running is safe and is how the rule gets corrected. Pending findings for the revision are rebuilt; any pair a person has already ruled on keeps their decision, including `FALSE_POSITIVE`, so a pair dismissed once is never re-raised. Analysis runs after tessellation — in `process_version` and again whenever geometry is regenerated — because the boxes do not exist at `QUALITY_CHECKS` time, when the metadata rules run.

Findings are stored as `IFCCoordinationFinding` rows with both `element_a_id` and `element_b_id` populated, plus first-class `confidence`, `storey` and `space` columns. The findings API aggregates model-quality findings per rule as before, but keeps each interference pair separately reviewable — merging them would leave a reviewer unable to accept one and dismiss another.

## Suggestions, notifications, and audit

Element-class task suggestions include element counts, GlobalIds, discipline, evidence requirements, duplicate risk, reasoning, and confidence. Structural storeys can also produce milestone proposals, but a Project Manager must supply/edit the planned date because model existence never proves construction completion. Users may reject proposals; only the assigned Project Manager can accept creation. Edited payloads pass backend validation and are applied in the same transaction as the review status and audit records. Bulk review locks every selected proposal and fails atomically.

Upload, processing success/failure, comparison, project linking, review decisions, and finding-to-issue actions are audited. The uploader and Project Manager receive processing results; the Project Manager receives comparison summaries. Notifications contain project/entity references and never target users inferred from free text.

## Configuration

All settings are in `backend/.env.example`:

- `IFC_FEATURE_ENABLED`
- `IFC_MAX_FILE_MB`
- `IFC_PARSE_TIMEOUT_SECONDS`
- `IFC_MAX_ENTITY_COUNT`
- `IFC_BACKGROUND_PROCESSING_ENABLED`
- `IFC_ENGINEER_UPLOAD_ENABLED`
- `IFC_COMPARISON_ENABLED`
- `IFC_COORDINATION_CHECKS_ENABLED`
- `IFC_GEOMETRY_ENABLED`
- `IFC_AI_ANALYSIS_ENABLED`

`IFC_ENGINEER_UPLOAD_ENABLED=false` is the conservative default. Project Managers and admins manage versions; active main-contractor engineers can upload only when this setting is enabled. Consultant engineers can view, compare, and review findings within assigned projects. Owners and workers have read-only summary access. Private source files are never exposed by the static `/uploads` mount.

## API examples

Create a model group:

```http
POST /api/v1/projects/{projectId}/ifc/models
Authorization: Bearer …
Content-Type: application/json

{"name":"Architectural model","discipline":"ARCHITECTURAL"}
```

Upload a version:

```http
POST /api/v1/projects/{projectId}/ifc/models/{modelId}/versions
Authorization: Bearer …
Content-Type: multipart/form-data

file=@building.ifc; title=Issued for construction; revision_code=P03
```

Compare versions:

```http
POST /api/v1/projects/{projectId}/ifc/comparisons
Authorization: Bearer …
Content-Type: application/json

{"baseVersionId":"…","targetVersionId":"…"}
```

The OpenAPI document exposes 55 IFC operations covering upload constraints, models, versions, hierarchy/search, comparisons/impacts, findings, suggestions, links, and processing jobs.

## Deployment

1. Build the backend image so `ifcopenshell==0.8.5` is installed.
2. Persist `/app/private_uploads`; the compose configuration deliberately keeps the existing `voice_audio_data` volume name so upgrades retain prior private voice data while adding IFC sources.
3. Run `alembic upgrade head`. Revision `c30f4a6b8e71` adds IFC version type and processing duration after the original IFC schema revision.
4. Build and deploy the React application.
5. Monitor processing jobs, private-volume capacity, parsing duration, and failure support IDs.

IFC files can be large and are untrusted input. Keep the entity/file limits enabled, avoid making the private upload directory public, and place dedicated workers behind OS/container resource limits for production.

## Geometry and AI boundaries

Geometry generation is enabled by default and can be disabled with `IFC_GEOMETRY_ENABLED=false`. The selected architecture is server-side IfcOpenShell 0.8.5 tessellation plus a cached, versioned `BIMGEO1` binary rendered by maintained Three.js 0.185. This is a better fit than sending the private, potentially very large IFC source to every browser: it needs no browser WASM or Web Worker deployment, keeps authentication on normal API requests, provides stable ExpressID mapping, and caches conversion across users. The geometry worker is process-isolated, timeout-limited, vertex-limited, shifts georeferenced coordinates to a local WebGL origin, records partial/skipped statistics, and atomically replaces artifacts in persistent private storage.

The viewer itself makes no geometric claim, and revision analysis continues to use stable identifiers, properties, placements and representation fingerprints rather than measured displacement. Interference detection is separate from both: it reads the per-element bounding boxes the tessellator records, and reports candidates for review rather than confirmed clashes (see *Structural/service interference*).

The AI Intelligence Center is a persistent rule-driven review system, not a chatbot. It calculates a transparent weighted alignment score; detects missing discipline/task scope, low evidence coverage, completed linked tasks without verified evidence, uncovered modeled categories, revision impact on active/completed work, existing task/model match candidates, and existing IFC quality findings; and produces grouped task suggestions by revision, discipline, and storey. Fingerprints prevent duplicates. Findings carry evidence, confidence, impact, recommended action, and human review state. Authorized users can deliberately create an issue or review/edit/create a task, which also creates explicit IFC links. No task, issue, assignment, deadline, progress value, message, model geometry, or engineering decision is changed automatically.

## Tests

`backend/tests/fixtures/interference_ifc4.ifc` carries genuine extruded solids — a beam, a duct crossing it, a duct well clear of it, and a tray resting exactly on its top face — placed so the expected answer is arithmetic a reader can check by hand. `tests/test_ifc_interference.py` covers the pure rule (units, thresholds, pairing, ordering, refusals) and `tests/test_ifc_interference_pipeline.py` runs the whole chain against a real database, asserting the stored evidence can be recomputed from what was stored.

`backend/tests/fixtures/minimal_ifc4.ifc` is a small IFC4 STEP fixture with a complete project/site/building/storey/space hierarchy, one wall, containment, and a property set. Parser tests use the real IfcOpenShell package. Geometry tests programmatically build a renderable IFC wall and verify real tessellation, exact mesh counts, binary offsets, and stable ExpressIDs; they also verify the metadata-only failure path. AI tests verify score weights/caps and deterministic fingerprints. Workflow tests cover the processing state machine and file-signature rejection. The React TypeScript check and production build validate the workspace integration.

### The representative corpus

`minimal_ifc4.ifc` proves one wall in one schema. Five further checked-in fixtures, all produced by IfcOpenShell and exercised by `tests/test_ifc_corpus.py`, cover what real projects send:

| Fixture | What it exercises |
| --- | --- |
| `multi_discipline_ifc4.ifc` | Two storeys, eight spaces, all seven disciplines, `IfcProjectedCRS` + `IfcMapConversion` georeferencing, office-type inference |
| `multi_discipline_ifc2x3.ifc` | The same building in the schema most authoring tools still export; MEP classes that IFC2X3 does not define are absent by design |
| `infrastructure_ifc4x3.ifc` | Site/civil elements with no building or storey at all |
| `arabic_ifc4.ifc` | Arabic project, storey, space, element and property values end to end |
| `no_storey_ifc4.ifc` | A flat export with unnamed elements — warnings, not failure |
| `duplicate_tags_ifc4.ifc` | Distinct GlobalIds sharing one tag, the input for the duplicate-tag quality finding |

`tests/test_ifc_worker_failure.py` covers the crashed/killed/hung worker classification and asserts that every code the pipeline can emit has user-facing title, description and suggested action. Its end-to-end case spawns a real worker against a truncated fixture and is opt-in behind `IFC_NATIVE_CRASH_TEST=1`, because it deliberately crashes a child process.

`tests/test_ifc_secondary_product_failure.py` runs the real `process_version` against a real database and asserts that a failing geometry or intelligence pass leaves the model `READY`, while a genuine parse failure is still recorded as `FAILED`.

`frontend/src/features/ifc/components/IFCUpload.test.ts` covers pre-upload rejection and asserts both catalogues explain every backend failure code. Those headings are looked up by code at runtime, so the static `t("literal")` coverage check cannot see them.

## Acceptance scenarios

- First upload: an authorized user creates a group, uploads a signature-valid file, sees progress, then sees its hierarchy and extracted wall/property set.
- Room/floor selection: the hierarchy identifies spaces and storeys; project-data endpoints return only links from the same project.
- New version: the original remains immutable, the next number is assigned under a row lock, and baseline/active designation is explicit.
- Structural movement: a shared column GlobalId with changed placement/representation is a high-severity moved record; linked work receives an impact proposal, not an automatic status change.
- Task suggestion: the proposal is visible with evidence and duplicate risk; rejection creates nothing, while Project Manager acceptance creates a Backlog task transactionally.
- Photo/document evidence: an authorized explicit link connects a media/document record to an IFC element or spatial node without exposing the private IFC source.
- Arabic metadata: parser strings and JSON storage are Unicode-safe; no ASCII normalization is applied.
- Geometry failure: hierarchy and property intelligence stays available and the UI clearly reports geometry as disabled/failed.

## Known limitations

- Section planes, measurement tools, solid-geometry clash confirmation, progressive chunk streaming, and multi-model federation are not implemented. Large artifacts are cached and vertex-limited but are currently downloaded as one binary response.
- Metric/imperial source unit labels and measurement provenance are retained, but the end-user Metric/Imperial display toggle and safe geometry-derived quantity fallback are not yet implemented.
- The model chat and computer-vision interfaces remain future work. No model fact, site progress, or geometric deviation is invented.
- Intelligence runs automatically after IFC processing and on explicit user refresh. Automatic queued re-analysis hooks for every task, issue, evidence, design-change, and mapping mutation are not yet wired.
- Explicit IFC link APIs support tasks, issues, milestones, documents, reports, submissions, and media, and AI-created work items use them. Dedicated BIM location/object pickers are not yet embedded in every existing task, issue, evidence, and site-report edit screen.
- Parsing jobs use the existing durable in-process background runner; horizontal/high-volume deployments should connect the same service functions to a dedicated queue. Geometry conversion itself is isolated in a timeout-limited child process.
- Fuzzy matching is not used to silently pair changed identifiers. Unmatched IDs remain added/removed to avoid false certainty.
- Mobile is read-only for IFC and does not download large source files.
- Full visual acceptance and large-model performance testing still require the project's real architectural, structural, MEP and IFC4X3 model library. The checked-in corpus is representative in structure and schema coverage, but every fixture is small; nothing here measures behaviour at hundreds of megabytes or millions of entities.
- The `IFC_PARSER_OUT_OF_MEMORY` classification is inferred from a `SIGKILL` exit code. That is the usual cause on a container host under memory pressure, but the OS does not report a reason, so an operator killing the worker by hand is reported the same way.
