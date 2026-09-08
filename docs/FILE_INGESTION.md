# Unified File Ingestion Pipeline — foundation

What is in the repository today. Nothing below is aspirational; where something
is deliberately not built, it is stated under **Not implemented**.

Companion documents: [FILE_INTELLIGENCE.md](FILE_INTELLIGENCE.md),
[IFC_INTELLIGENCE.md](IFC_INTELLIGENCE.md), [RAG.md](RAG.md),
[RBAC.md](RBAC.md), [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. The problem this solves

Before this, a file could enter the platform three ways, and each way owned a
different model with a different vocabulary:

| Path | Model | Storage | Lifecycle | Classification |
|---|---|---|---|---|
| `POST /documents/upload` | `Document` | public `/uploads/...` URL | RAG `index_status` only | advisory, on upload |
| `POST /attachments` | `Attachment` | public URL + storage key | none | none |
| `POST /projects/{id}/ifc/models/{m}/versions` | `IFCModelVersion` | private storage key | 8-state machine | schema/app from a full parse |

Three consequences followed:

1. **No project-wide file identity.** "Show me every file on this project" had
   no query behind it.
2. **No home for a design package.** A ZIP holding forty drawings and a
   specification had nowhere to record that its members came from it — none of
   the three models has a parent.
3. **Format knowledge was re-derived per path.** `file_intelligence` answered
   *what format is this* well, but the answer had no shared category to feed,
   so every caller re-read an extension.

## 2. What was built

A layer that sits **beside** those three, not above them. Existing endpoints
are unchanged and remain authoritative for their own domain meaning.

```
POST /projects/{id}/files
        │
        ▼
   ┌─────────────────────────── in the request ───────────────────────────┐
   │ UPLOAD ─► VALIDATE ─► CLASSIFY ─► REGISTER ─► STORE ─► QUEUE         │
   │   │          │            │           │         │        │           │
   │   │   file_storage   file_intelligence │  private_storage │           │
   │   │   (allowlist +   + categories.py   │  (key, not path) │           │
   │   │    magic bytes)                    │                  │           │
   └───┼────────────────────────────────────┼──────────────────┼──────────┘
       │                                    │                  │
       │  refused → 415/413/400,       ingested_files     ingestion_jobs
       │  nothing stored                    row               row
       │                                                       │
   ┌───────────────────── on the shared bounded pool ──────────▼──────────┐
   │  ProcessorRegistry.select(file)                                      │
   │        │                                                             │
   │        ├─ validate()  ─ may this processor touch it?                 │
   │        ├─ extract()   ─ raw, format-shaped facts                     │
   │        ├─ normalize() ─ the platform's vocabulary                    │
   │        └─ process()   ─ READY | PARTIAL | FAILED                     │
   └──────────────────────────────────────────────────────────────────────┘
```

### Modules

| Module | Responsibility |
|---|---|
| `services/ingestion/categories.py` | `FileCategory` + `classify_file()` — the normalized kind, with evidence |
| `services/ingestion/validation.py` | the gate, reusing `file_storage`'s allowlist and signature check |
| `services/ingestion/archives.py` | ZIP defences: traversal, bombs, entry count, symlinks |
| `services/ingestion/state.py` | the lifecycle as a transition table |
| `services/ingestion/errors.py` | failure codes, and the internal/public split |
| `services/ingestion/contracts.py` | `FileProcessor`, `ProcessorContext`, `ProcessorOutcome` |
| `services/ingestion/registry.py` | one processor per category, ambiguity refused at import |
| `services/ingestion/processors/` | pdf, office, ifc, zip_package, misc |
| `services/ingestion/pipeline.py` | orchestration, transactions, background dispatch |
| `services/ingestion/ifc_bridge.py` | IFC revisions made visible without being owned |
| `services/processing_pool.py` | the bounded pool, **moved out of `api/ifc.py` and shared** |
| `api/downloads.py` | streaming + RFC 6266 headers, **moved out of `api/ifc.py` and shared** |

## 3. The record

`ingested_files` is one row per file, and it is deliberately *not* an extension
of `documents`: `Document.file_url` is a public URL and the model carries RAG
state, `Attachment` is bound to a domain entity, and `IFCModelVersion` is a
revision in a comparison graph. None can hold package parentage and a shared
lifecycle without becoming worse at its own job.

`source_entity_type` / `source_entity_id` point back at whichever subsystem
owns the file's meaning (`IFC_MODEL_VERSION` today), and that subsystem stays
the authority.

`ingestion_jobs` mirrors `ifc_processing_jobs` down to the idempotency key,
because that shape already worked.

### Duplicates

`checksum_sha256` is indexed, **not unique**. A duplicate is *recorded* in
`duplicate_of_id` rather than refused, because the two subsystems need opposite
policies: a duplicate IFC revision is meaningless and the IFC endpoint returns
409, while a design package legitimately ships the same title block in six
drawings. Surfacing the fact lets each consumer decide.

## 4. Lifecycle

```
UPLOADED ─► VALIDATING ─► CLASSIFIED ─► QUEUED ─► PROCESSING ─┬─► READY
                                          ▲                   ├─► PARTIAL
                                          └───── retry ───────┴─► FAILED
```

**PARTIAL is a success.** The processor ran to completion and delivered less
than the format allows: a scanned PDF with no text layer, a DWG stored
unparsed, a workbook whose sheet names were read but not its cells. Calling
that FAILED would push people to retry something that can never succeed.
`QUEUED → READY/PARTIAL` directly is legal so that inline processing (tests,
and `INGESTION_BACKGROUND_PROCESSING_ENABLED=false`) is not a different machine.

## 5. Processors

| Processor | Categories | Extraction | Typical outcome |
|---|---|---|---|
| `pdf` | PDF | page count, text layer, sample (pypdf, already a dependency) | READY, or PARTIAL `NO_TEXT_LAYER` for a scan |
| `docx` | DOCX | body text from `word/document.xml`, stdlib only | READY |
| `xlsx` | XLSX | sheet names from `xl/workbook.xml`, stdlib only | PARTIAL `FORMAT_NOT_PARSED` — cells not read |
| `legacy-office` | DOC, XLS | none (OLE2 has no stdlib reader) | PARTIAL `FORMAT_NOT_PARSED` |
| `ifc` | IFC | STEP header, or the engine's own facts when linked | READY when the linked revision is; else PARTIAL |
| `drawing` | DRAWING | none | PARTIAL `FORMAT_NOT_PARSED` |
| `image` | IMAGE | none, and that is complete | READY |
| `text` | TEXT | sample | READY |
| `zip-package` | ZIP_PACKAGE | members registered individually | READY, or PARTIAL when entries were skipped |
| `passthrough` | OTHER + fallback | none | PARTIAL `NO_PROCESSOR` |

The IFC processor is an **adapter and never a parser**. `ifc_processing_service`
— 670 lines with an isolated child process, its own timeout and its own memory
ceiling — is untouched. A file linked to an `IFCModelVersion` has its status
*derived* from that version at process time, so there is no second copy to
drift. A bare IFC uploaded here reads its header and says so.

## 6. Design packages

`inspect()` judges every entry before a byte is read, and separates two things:

* **Refuse the archive** — traversal, symlink, declared expansion or ratio over
  the ceiling, too many entries. Not accidents.
* **Skip an entry, and record it** — directories, `__MACOSX/`, `.DS_Store`,
  empty entries, and members that fail the upload allowlist on their own terms.

Entry names are used only as **labels**. Every member is stored under a key the
platform generates, so no attacker-controlled string reaches the filesystem
even if the name checks were removed. A nested archive is stored and not
opened (`INGESTION_ZIP_MAX_DEPTH`, default 1).

## 7. API

All under `/api/v1/projects/{project_id}/files` — project-scoped in the prefix,
so isolation is structural rather than remembered.

| Route | Permission | Notes |
|---|---|---|
| `GET /upload-constraints` | `document.view` | limits, accepted extensions, categories |
| `POST /` | `document.upload` (+ `ifc.upload` if classified IFC) | 202; the stored object is deleted if the IFC gate refuses |
| `GET /` | `document.view` | paginated; `category`, `status`, `parentId`, `rootOnly` |
| `GET /{id}` | `document.view` | normalized metadata and the publishable error |
| `GET /{id}/download` | `document.view` (+ `ifc.download` if IFC) | streamed, always `application/octet-stream` |
| `POST /{id}/retry` | `document.upload` | 409 while still processing |

No new permission codes. The existing `document.upload` / `document.view` are
what the endpoints check, so an administrator configures one vocabulary.

## 8. Security

| Threat | Control |
|---|---|
| Path traversal (filename) | `sanitize_filename` takes `Path(...).name` first, then filters |
| Path traversal (archive) | `safe_entry_name` refuses `..`, absolute and drive-qualified names; members stored under generated keys regardless |
| Symlink entries | refused on the `external_attr` mode bits |
| Zip bombs | three independent ceilings — total, per-entry, ratio — checked on the declared sizes *and* enforced again on the actual read |
| Entry-count exhaustion | `INGESTION_ZIP_MAX_ENTRIES`, checked before any entry is read |
| Unbounded recursion | `INGESTION_ZIP_MAX_DEPTH` |
| MIME spoofing | `file_storage._matches_signature`, unchanged; extension only breaks container ties |
| Oversized files | `INGESTION_MAX_FILE_MB`, enforced while streaming and again on package members |
| Dangerous types | allowlist per upload category; `.exe` and anything unlisted refused |
| Unauthorized project access | `user_has_project_access` first on every route, then the permission, then a `project_id` filter on the row |
| Unauthorized IFC access | `can_ifc` additionally gates IFC upload and download here |
| Storage key exposure | no schema field carries it; downloads stream |
| Header injection | `attachment_headers` strips `\r`, `\n`, `"` and `\` |
| Stored XSS via download | downloads always `application/octet-stream`, never the file's own type |
| Error information leakage | internal detail on the row; the API publishes only a code and a sentence |
| Orphaned objects | the stored object is deleted if registration fails; `storage_key` is unique |

## 9. Configuration

```
INGESTION_ENABLED=true
INGESTION_MAX_FILE_MB=200
INGESTION_BACKGROUND_PROCESSING_ENABLED=true
INGESTION_ZIP_MAX_ENTRIES=500
INGESTION_ZIP_MAX_TOTAL_MB=1000
INGESTION_ZIP_MAX_ENTRY_MB=200
INGESTION_ZIP_MAX_RATIO=100
INGESTION_ZIP_MAX_DEPTH=1
```

There is deliberately **no** `INGESTION_MAX_CONCURRENT_PROCESSING`.
`IFC_MAX_CONCURRENT_PROCESSING` governs the one shared pool; a second ceiling
would silently double the memory bound the first exists to enforce.

## 10. Migration

`aa41c7d2e908`, revising `f59d2c8e4a13`. Two new tables, no existing table
altered, no data moved, nothing backfilled — inventing a classification for
files nobody looked at is indistinguishable from having looked.
`ifc_bridge.backfill_project(db, project_id)` registers historical IFC
revisions explicitly and repeatably.

`downgrade()` drops both tables; objects already written under the `ingest/`
prefix remain in private storage, because dropping a table must never delete a
customer's files.

## 10b. RAG indexing (added after the foundation)

An `IngestedFile` whose `metadata_json.extraction` is `TEXT` can be indexed for
retrieval: `POST /rag/files/{id}/index` queues the work on the same bounded
pool, and the chunks land in `document_chunks` with `ingested_file_id` set.
Files that extracted no text — a scan, a drawing, a spreadsheet — are refused
using that recorded verdict, without the file being opened. The gate is the
reason the extraction result is recorded at all. See
[RAG.md](RAG.md) §3b.

The three indexing columns live on `ingested_files`; the extraction verdict
stays in `metadata_json`, where the processor that produced it put it.

## 11. Not implemented

Deliberately out of scope for the foundation:

* **RAG retrieval over ingested files** — chunks are stored with full
  provenance but are not yet reachable by `POST /rag/query`; see RAG.md §12.
* **pgvector** — vectors are still JSONB behind the `VectorStore` interface.
* **MCP, agents, autonomous detection** — nothing here calls a model. All
  classification is deterministic.
* **Deep parsing** — DWG/DXF geometry, spreadsheet cell values, Word tables and
  headers, OCR for scanned PDFs. Each is declared as a limitation on its
  processor and in `file_intelligence.REGISTRY`.
* **Cross-document analysis** — no linking of a drawing to a specification, no
  revision comparison across packages.
* **Migrating `documents` or `attachments` onto this record.** They keep their
  own identities; this is not an older version of them.
* **A Documents UI redesign.** `ProjectFilesPanel` sits beside the existing
  library, showing files rather than library entries.

## 12. Next step for RAG 2.0

The ingestion record already provides what a retrieval layer needs: a stable
file id, project association, category, document kind, normalized metadata,
processing status and source relationships.

The recommended next task is to move indexing off `documents` and onto
`ingested_files`:

1. add `IngestedFile.index_status` / `indexed_at` / `index_error`, mirroring the
   three columns `Document` already carries, so both populations are indexable
   while the migration proceeds;
2. give `DocumentChunk` a nullable `ingested_file_id` beside its
   `document_id`, so a chunk can cite either;
3. teach `services/rag/ingestion.py` to accept an `IngestedFile` whose
   `metadata_json.extraction` is `TEXT` — which is already true for every PDF
   and DOCX the pipeline has processed;
4. only then consider pgvector, and only with a measured reason.

Step 3 is where the foundation pays off: the PDF and DOCX processors already
produce the extraction verdict, so RAG stops re-opening files to find out
whether they have readable text.
