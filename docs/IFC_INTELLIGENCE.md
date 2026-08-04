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
- Deterministic coordination data-quality findings. A geometric clash is never claimed unless geometry evidence exists.
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

## Upload and version workflow

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

Coordination checks currently identify deterministic data-quality conflicts such as duplicated non-empty element tags. Findings retain element IDs and evidence, can be acknowledged/ignored/marked false-positive, or explicitly converted into an issue by an authorized user. Geometric clash claims are disabled until an isolated geometry worker supplies bounding-box/mesh evidence.

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

The OpenAPI document exposes 48 IFC operations covering models, versions, hierarchy/search, comparisons/impacts, findings, suggestions, links, and processing jobs.

## Deployment

1. Build the backend image so `ifcopenshell==0.8.5` is installed.
2. Persist `/app/private_uploads`; the compose configuration deliberately keeps the existing `voice_audio_data` volume name so upgrades retain prior private voice data while adding IFC sources.
3. Run `alembic upgrade head`. Revision `c30f4a6b8e71` adds IFC version type and processing duration after the original IFC schema revision.
4. Build and deploy the React application.
5. Monitor processing jobs, private-volume capacity, parsing duration, and failure support IDs.

IFC files can be large and are untrusted input. Keep the entity/file limits enabled, avoid making the private upload directory public, and place dedicated workers behind OS/container resource limits for production.

## Geometry and AI boundaries

Geometry generation is enabled by default and can be disabled with `IFC_GEOMETRY_ENABLED=false`. The selected architecture is server-side IfcOpenShell 0.8.5 tessellation plus a cached, versioned `BIMGEO1` binary rendered by maintained Three.js 0.185. This is a better fit than sending the private, potentially very large IFC source to every browser: it needs no browser WASM or Web Worker deployment, keeps authentication on normal API requests, provides stable ExpressID mapping, and caches conversion across users. The geometry worker is process-isolated, timeout-limited, vertex-limited, shifts georeferenced coordinates to a local WebGL origin, records partial/skipped statistics, and atomically replaces artifacts in persistent private storage.

This viewer does not claim geometric clashes or measured revision displacement. Revision analysis continues to use stable identifiers, properties, placements, and representation fingerprints unless a future validated clash pipeline is added.

The AI Intelligence Center is a persistent rule-driven review system, not a chatbot. It calculates a transparent weighted alignment score; detects missing discipline/task scope, low evidence coverage, completed linked tasks without verified evidence, uncovered modeled categories, revision impact on active/completed work, existing task/model match candidates, and existing IFC quality findings; and produces grouped task suggestions by revision, discipline, and storey. Fingerprints prevent duplicates. Findings carry evidence, confidence, impact, recommended action, and human review state. Authorized users can deliberately create an issue or review/edit/create a task, which also creates explicit IFC links. No task, issue, assignment, deadline, progress value, message, model geometry, or engineering decision is changed automatically.

## Tests

`backend/tests/fixtures/minimal_ifc4.ifc` is a small IFC4 STEP fixture with a complete project/site/building/storey/space hierarchy, one wall, containment, and a property set. Parser tests use the real IfcOpenShell package. Geometry tests programmatically build a renderable IFC wall and verify real tessellation, exact mesh counts, binary offsets, and stable ExpressIDs; they also verify the metadata-only failure path. AI tests verify score weights/caps and deterministic fingerprints. Workflow tests cover the processing state machine and file-signature rejection. The React TypeScript check and production build validate the workspace integration.

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

- Section planes, measurement tools, geometric clash detection, progressive chunk streaming, and multi-model federation are not implemented. Large artifacts are cached and vertex-limited but are currently downloaded as one binary response.
- Metric/imperial source unit labels and measurement provenance are retained, but the end-user Metric/Imperial display toggle and safe geometry-derived quantity fallback are not yet implemented.
- The model chat and computer-vision interfaces remain future work. No model fact, site progress, or geometric deviation is invented.
- Intelligence runs automatically after IFC processing and on explicit user refresh. Automatic queued re-analysis hooks for every task, issue, evidence, design-change, and mapping mutation are not yet wired.
- Explicit IFC link APIs support tasks, issues, milestones, documents, reports, submissions, and media, and AI-created work items use them. Dedicated BIM location/object pickers are not yet embedded in every existing task, issue, evidence, and site-report edit screen.
- Parsing jobs use the existing durable in-process background runner; horizontal/high-volume deployments should connect the same service functions to a dedicated queue. Geometry conversion itself is isolated in a timeout-limited child process.
- Fuzzy matching is not used to silently pair changed identifiers. Unmatched IDs remain added/removed to avoid false certainty.
- Mobile is read-only for IFC and does not download large source files.
- Full visual acceptance and large-model performance testing still require the project's real architectural, structural, MEP and IFC4X3 model library. The repository contains only the small IFC4 metadata fixture plus the programmatically generated geometry test model.
