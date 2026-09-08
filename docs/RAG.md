# RAG — asking questions about project documents

Upload a PDF, index it, ask a question, get an answer that cites the document
and page it came from — or an explicit "not found" when the documents do not
contain the answer.

---

## 1. What RAG is, and why it is built this way

**Retrieval-Augmented Generation**: instead of asking a language model what it
knows, you *retrieve* the passages of your own documents that are most relevant
to the question, and ask the model to answer using only those. The model
supplies language; your documents supply facts.

On a construction project this distinction is the whole point. A model asked
"what is the retention percentage?" without context will answer confidently
from industry norms — commonly 5% or 10% — and it will be wrong for *this*
contract often enough to matter. Someone will act on it. So the system is built
so that **every factual answer is traceable to a page you can open and check**,
and an answer that cannot be traced is not given at all.

## 2. Architecture

```
                          POST /rag/documents/{id}/index
                                        │
                                        ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │ pdf_text     PDF on disk ──► text, one page at a time           │
  │ chunking     page text   ──► token-bounded, page-tagged chunks  │
  │ embeddings   text        ──► vectors (OpenAI, client injectable)│
  │ store        vectors     ──► pgvector + cosine, behind VectorStore│
  │ ingestion    orchestrates the above, owns the state machine     │
  └─────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                             document_chunks table
                                        ▲
                          POST /rag/query
                                        │
  ┌─────────────────────────────────────────────────────────────────┐
  │ document_access  which documents may this user read?            │
  │ retrieval        question ──► top-K chunks in that allowed set  │
  │ answering        chunks   ──► grounded answer + citations       │
  └─────────────────────────────────────────────────────────────────┘
```

Each layer is replaceable without disturbing the others. **`store.py` is the
only module that knows how a vector is stored** — which is what made the move
from JSONB to pgvector one new class and one factory line. See §9.

## 2b. Routing — deciding whether to retrieve at all

Retrieval used to be unconditional. `POST /rag/query` embedded every question
and searched the document vectors, because searching was the only thing it
could do. Ask it "what is the project progress?" and it searched contract PDFs,
returned whichever passage happened to be nearest, and left the answering layer
to notice the mismatch.

That is the wrong shape for a platform that already holds the answer to most
project questions as structured data. Progress is a number in `tasks`. The
latest site report is a row. What conflicts with a beam is a coordination
finding carrying measured evidence. None of those improve by being turned into
a similarity search over PDFs, and injecting unrelated passages into the prompt
makes a grounded answer *less* likely, not more.

`services/knowledge_router.py` decides first, and does so **deterministically**
— the platform's rule that AI decides intent while the backend decides
execution applies here, because choosing a data source is closer to execution
than to intent. Every decision carries the phrase that produced it, so it can
be explained rather than guessed at.

### Sources

| Source | Answered by | Example |
| --- | --- | --- |
| `PROJECT_STRUCTURED` | `voice_query_service.answer_query` | "What is the project progress?" |
| `SITE_REPORTS` | `voice_query_service.answer_query` | "What did the latest site report say?" |
| `IFC_MODEL` | `services/ifc_knowledge.py` | "What conflicts with this beam?" |
| `DOCUMENTS` | `rag.retrieve` + `AnswerService` | "What does the specification say about grout?" |

The topic taxonomy is **not** reinvented. `VoiceQueryTopic` already enumerates
the questions the backend can answer from project data, and `answer_query`
already answers them, so routing maps a typed question onto that taxonomy. A
typed question and a spoken one now reach the same facts through the same
function and cannot drift into disagreeing about the project.

### Two rules that matter more than accuracy

**When unsure, documents.** A question the router cannot place goes to document
retrieval — exactly where it went before routing existed. Routing may only take
work *away* from the vector store on a confident match, never on a guess. This
is why the pre-existing RAG behaviour is preserved for every unrouted question.

**A source is never invented.** Availability is checked per project *and* per
caller before a source is chosen: routing a model question to IFC on a project
with no model, or for someone who may not open it, would be worse than not
routing. Rejected sources are recorded in `unavailable` rather than dropped.

### Where it applies

`POST /rag/query` now routes before retrieving, and returns `route`,
`routeReason` and `routeMatched` alongside its existing fields — additive, so a
client ignoring them behaves as before. When the question belongs elsewhere it
returns `found: false` with the reason instead of searching anyway. Naming a
`documentId` explicitly skips routing entirely: that is an instruction, not a
question about where to look.

`POST /projects/{projectId}/knowledge/query` is the routed entry point that can
answer from any source, with citations carrying `sourceType` so a project
record, an IFC finding and a document page are distinguishable. It is mostly
not new code — routing was the missing part, not the answering.

### IFC knowledge is not vectorised

Element names and GlobalIds are identifiers, not prose. Similarity search over
them retrieves near-spellings rather than facts, so `ifc_knowledge.py` does
database lookups and returns exact answers with evidence attached. A fact
lifted out of a coordination finding carries that finding's own hedge —
"potential interference, verify the solid geometry" — because a caveat dropped
in transit is a caveat lost exactly where it matters.

Naming a subject that does not exist is answered as such. "What conflicts with
ZZZ999?" reports that no element matched, rather than returning every finding
in the project, which would be answering a question nobody asked.

## 3. Ingestion flow

1. A PDF is uploaded through the **existing** `POST /documents/upload`.
   Nothing is indexed automatically.
2. `POST /rag/documents/{id}/index` is called explicitly.
3. Permission check — project access **plus** the owner/consultant document
   scopes (§7).
4. The document is claimed with an atomic `UPDATE … WHERE index_status <>
   'INDEXING'`. The row count *is* the lock: two concurrent requests race, one
   wins, the loser gets **409**.
5. `file_url` is resolved to a path under `UPLOAD_DIR` with a traversal guard,
   and the file's first bytes are checked for `%PDF-`. The declared
   `mime_type` is not trusted — it is client-supplied at upload.
6. Size and page-count limits are enforced.
7. pypdf extracts text **per page**. Blank pages are dropped. A PDF with no
   text layer at all fails with a message that says it is probably a scan and
   that OCR is not supported.
8. Each page is chunked independently, token-aware, with overlap.
9. Chunks are embedded in batches; the call is recorded in the existing
   `ai_provider_calls` governance table.
10. `VectorStore.add_chunks` **replaces** any previous chunks, then the
    document becomes `READY` with `indexed_at` and `page_count`.

## 3b. Indexing a file from the unified ingestion pipeline

The same state machine, a different way of getting the text, and one extra
gate at the front.

```
IngestedFile
     │
     ├─ metadata_json.extraction == "TEXT"?  ──no──►  NotIndexable
     │                                                (status unchanged,
     │                                                 no error recorded)
     ▼
  claim (INDEXING)  ──►  read text  ──►  chunk  ──►  embed  ──►  store
                                                                   │
                                              DocumentChunk(ingested_file_id=…)
                                                                   │
                                                                 READY
```

1. A file is uploaded through `POST /projects/{id}/files`, which classifies it
   and records what it extracted. Nothing is indexed automatically.
2. `POST /rag/files/{id}/index` is called explicitly. It returns **202**: the
   work is queued, not done.
3. Permission — project access, then `document.view`, the same codes the
   unified file endpoints enforce. A file outside every project the caller can
   reach is a **404**, because confirming an id exists is itself information.
4. **The gate is the pipeline's own verdict.** `metadata_json.extraction` was
   written when the file was processed, so a scan, a drawing or a spreadsheet
   is refused *without the file being opened*. That refusal happens before the
   row is claimed, so an unindexable file keeps `NOT_INDEXED` and gets no
   error — a permanent property must not look like a retryable failure.
5. The work runs on `services/processing_pool.py`, the **same bounded pool**
   IFC parsing and file processing already share. `IFC_MAX_CONCURRENT_PROCESSING`
   therefore remains one ceiling over all heavy work rather than one of several.
6. Text is read back through `services/rag/text_source.py`, which **delegates
   to the ingestion processors** rather than reimplementing extraction. A PDF
   yields real pages; a Word or text file yields a single page 1, which is
   truthful — that is where a reader opening it would find the passage.
7. From there it is identical to the document path: chunk, embed, replace,
   `READY`.

Why the text is read again at all, when the pipeline already extracted it: the
pipeline stores a ~4 KB *sample*, because `metadata_json` is a metadata column
and not a text store. The *decision* is free and is never re-derived; the
*content* is not.

## 4. Retrieval flow

> **Both sources are retrievable.** A passage may come from a library
> `Document` or from an `IngestedFile`, and `VectorStore.search` takes a
> separate, mandatory readable-id set for each. An empty set means *zero
> readable sources of that type*; it never means "all". See §12.

1. `POST /rag/query` with a `projectId`, a `query`, and optionally a
   `documentId`.
2. Project access is checked. Then the set of documents this user may read is
   resolved, and narrowed to those that are `READY`.
3. The question is embedded with the same model used for the chunks.
4. `VectorStore.search` scores every candidate chunk by cosine similarity and
   returns the top K.
5. The retrieved passages are numbered and given to the model with a prompt
   that forbids outside knowledge.
6. Citations are constructed **from the retrieved chunk records** — never
   parsed out of the model's prose.

## 5. Grounding — the three mechanisms

Grounding does not rely on the model choosing to behave. Three independent
mechanisms push toward it:

1. **The prompt forbids outside knowledge.** It requires the model to emit the
   sentinel `INSUFFICIENT_CONTEXT` when the passages do not support an answer,
   rather than being trusted to phrase a refusal consistently — "I could not
   find that", "the document does not specify", and a plausible fabrication
   are hard to tell apart downstream. A sentinel is unambiguous.
2. **Citations cannot be invented.** They are built from the retrieved chunk
   records, so a citation can only ever point at a page that was actually
   retrieved. A model that writes "…as stated on page 99 [7]" still produces
   citations pointing only at the real retrieved pages — there is no channel
   through which a hallucinated page can become a citation.
3. **`found` is computed, not claimed.** With nothing retrieved, the not-found
   answer is returned and **the model is never called at all** — an empty
   context is an invitation to improvise.

## 6. Database schema

**`document_chunks`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `document_id` | UUID **nullable** | FK → `documents.id` ON DELETE CASCADE |
| `ingested_file_id` | UUID **nullable** | FK → `ingested_files.id` ON DELETE CASCADE |
| `project_id` | UUID | FK → `projects.id`. Denormalised on purpose — see below |
| `page_number` | int | 1-based. **NOT NULL** |
| `chunk_index` | int | order within the document |
| `content` | text | |
| `token_count` | int | |
| `embedding` | `vector(1536)` | pgvector. **Never returned by the API** |
| `embedding_model` | varchar(100) | so a model change is detected |
| `embedding_dim` | int | vectors of another length are skipped, not compared |
| `created_at` | timestamptz | |

Indexes: `(document_id, chunk_index)`, `(document_id, page_number)`,
`(ingested_file_id, chunk_index)`, `project_id`, `document_id`,
`ingested_file_id`.

Constraint `ck_document_chunks_exactly_one_source`:
`num_nonnulls(document_id, ingested_file_id) = 1`.

Vector index `ix_document_chunks_embedding_hnsw`:
`USING hnsw (embedding vector_cosine_ops)`. The operator class matters — an
index built for the default L2 distance would never be chosen by the `<=>`
(cosine) queries the store issues, and the only symptom would be a slow
search returning correct answers.

*The dimension is part of the schema.* `vector(1536)` rejects a vector of any
other width, so changing the embedding model to one of a different width is a
migration, not a configuration change. That turns a silent degradation —
vectors from two incompatible spaces compared against each other — into a
write that fails immediately. See `RAG_EMBEDDING_DIMENSIONS`.

*A chunk has exactly one source.* Its text came either from a library
`Document` or from an `IngestedFile` produced by the unified ingestion pipeline
(see [FILE_INGESTION.md](FILE_INGESTION.md)). Both columns are nullable and the
CHECK requires precisely one, so "a chunk with no source" and "a chunk claiming
two" are unrepresentable rather than merely discouraged. A polymorphic
`source_type`/`source_id` pair was rejected: it carries no foreign key, so
nothing would stop a chunk pointing at a deleted parent, and the cascade that
keeps indexed text from outliving its source would have to be reimplemented in
application code.

`document_id` is **not** deprecated. Every pre-existing chunk uses it, retrieval
still resolves citations through it, and the Document path is untouched. This is
a compatibility phase, not a migration.

*`project_id` is denormalised* so every retrieval query filters on the project
column directly. A join that must be remembered is a join that will eventually
be forgotten, and forgetting this one leaks another project's document text.

*`page_number` is NOT NULL* because a chunk that cannot name its page cannot be
cited, and an uncitable chunk has no place here. Chunking therefore never spans
a page boundary.

**`documents`** gains `index_status`, `indexed_at`, `index_error`,
`page_count`.

**`ingested_files`** gains `index_status`, `indexed_at`, `index_error` — the
same three columns holding the same four values, driven by the same state
machine. Deliberately not a second vocabulary: the point of putting indexing on
that record is that there is eventually *one* answer to "is this file
queryable", and two enums is how that becomes two answers. It has no
`page_count` column because the ingestion pipeline already records the page
count in `metadata_json`.

**Indexing state machine**

```
NOT_INDEXED ─┐
FAILED ──────┼──► INDEXING ──► READY
READY ───────┘         │
                       └────► FAILED (+ index_error, chunks removed)
```

On any failure the chunks are deleted and the status becomes `FAILED` with a
readable reason, committed as one unit. **Retrieval refuses anything that is
not `READY`**, so a half-written index is unreachable by construction rather
than by remembering to check.

## 7. Security

RAG answers questions *out of* document text, which makes it a read of that
text. So it enforces the **same** rules as the documents API, from the same
code — `app/services/document_access.py`:

1. **Project access** — `user_has_project_access`.
2. **Owner scope** — an Owner sees contracts and permits with no task, plus
   documents on tasks that are `DONE` and `approved`. Not drafts in progress.
3. **Consultant scope** — a consultant engineer sees documents in their own
   discipline, plus project-level documents.

Those two scope helpers were moved out of `api/documents.py` and are now shared
rather than duplicated. Had RAG checked only project access, an Owner could
have asked about a draft they are forbidden to download and received its
contents with page citations — unlogged, and looking like a feature. Tests
`test_an_owner_cannot_index_a_document_they_may_not_download` and
`test_a_consultant_cannot_index_a_document_outside_their_discipline` exist to
keep that door shut.

Also enforced:

- `VectorStore.search` **requires** `project_id` and an explicit list of
  document ids. An unscoped query cannot be expressed, let alone run.
- An empty readable set retrieves nothing — it never falls through to "all".
- A `documentId` from another project is refused rather than trusted, so
  naming a document directly cannot bypass the project filter.
- **Embeddings are never exposed.** No response schema has such a field.

## 8. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `RAG_ENABLED` | `false` | Master switch. With it off, RAG routes return **503** and the rest of the application is unaffected |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | 1536 dimensions |
| `RAG_EMBEDDING_DIMENSIONS` | `1536` | The width of the `embedding` column. **A schema change, not a setting** — a migration must move with it |
| `RAG_HNSW_ITERATIVE_SCAN` | `strict_order` | Keeps HNSW scanning until it has `k` rows that pass the filter. Empty disables it, for pgvector < 0.8 |
| `RAG_INDEX_STALE_MINUTES` | `30` | How long a row may sit in `INDEXING` before the reaper takes it back |
| `RAG_REAPER_ENABLED` | `true` | The periodic stale-run sweep. Off degrades to recovery-by-`force` only |
| `RAG_REAPER_INTERVAL_MINUTES` | `10` | How often that sweep runs |
| `RAG_REINDEX_MAX_ATTEMPTS` | `3` | Bounded retry for a project run |
| `RAG_REINDEX_MAX_SOURCES` | `500` | Ceiling on one run's size |
| `OPENAI_RAG_MODEL` | `gpt-4.1-mini` | The answering model |
| `RAG_CHUNK_TOKENS` | `500` | Target chunk size |
| `RAG_CHUNK_OVERLAP` | `75` | Tokens carried between neighbouring chunks |
| `RAG_TOP_K` | `5` | Passages retrieved per question |
| `RAG_MAX_FILE_MB` | `25` | Refused above this |
| `RAG_MAX_PAGES` | `300` | Refused above this |

The backend **refuses to boot** on `RAG_ENABLED=true` with no `OPENAI_API_KEY`,
and rejects an overlap greater than or equal to the chunk size (which would
make chunking non-terminating). It logs its status at startup:

```
INFO:     RAG enabled (OpenAI key configured: True, embedding model: …, answering model: …)
INFO:     RAG disabled; document question answering endpoints return 503
```

`OPENAI_API_KEY` is read from the environment only — never passed as a
parameter, never logged, never sent to a client.

## 9. Vector storage

Embeddings live in a pgvector `vector(1536)` column. Cosine distance is
computed by PostgreSQL, the ordering and the `LIMIT` happen in SQL, and an
HNSW index serves the ordering.

**This replaced JSONB.** The MVP stored each vector as a JSON array and scored
every candidate in numpy — no database extension needed, at the cost of a full
scan per query. `docs/RAG.md` §10 described the way out; migration
`c63fa2b5e819` is that migration, and the change reached exactly two files
outside the schema: `store.py` and the model.

### What the index does and does not do

Every query this store issues filters by project **and** by the source ids the
caller may read. Plain HNSW fetches its candidate set first and applies the
filter afterwards, so a selective filter can return fewer than the `k` rows
asked for — silently, and more often as the corpus grows.

`hnsw.iterative_scan` (pgvector ≥ 0.8) fixes that: the scan continues until it
has `k` matches. It is set per transaction with `SET LOCAL`, so it cannot leak
onto the next request sharing a pooled connection, and it is configurable —
`RAG_HNSW_ITERATIVE_SCAN=""` disables it for an older pgvector, where the only
consequence is possibly fewer results, never wrong or wider ones.

The default is `strict_order`, which guarantees results come back in true
distance order. That is what `ScoredChunk.score` implies to every caller, and
at `RAG_TOP_K=5` the cost over `relaxed_order` is not measurable.

### Remaining limits

* **Recall is approximate.** HNSW is an approximate index; a chunk that is
  genuinely in the top-k can be missed. `hnsw.ef_search` trades recall for
  latency and is left at pgvector's default.
* **One embedding model at a time.** The column holds one width, so a corpus
  cannot mix models. Changing models means a migration and a re-index of every
  document and file.
* **No hybrid search.** There is no lexical (BM25/`tsvector`) arm, so an exact
  term a passage uses verbatim ranks only as well as its embedding does.

## 10. The pgvector migration, as it was done

Kept as a record because the sequence is what makes it safe to repeat on
another environment.

1. **The database image.** `docker-compose.yml` moved from `postgres:15` to
   `pgvector/pgvector:pg15` — the same PostgreSQL major version with the
   extension compiled in, so the existing `postgres_data` volume is picked up
   unchanged. It is a binary swap, not a data migration.

   The pgvector image is built on a different Debian release, so PostgreSQL
   reports a **collation version mismatch** on first connect. The remedy is
   `REINDEX DATABASE` followed by
   `ALTER DATABASE … REFRESH COLLATION VERSION`; skipping it leaves text
   indexes built under collation rules the new library disagrees with.

2. **The dependency.** `pgvector==0.3.6` in `requirements.txt`, for the
   SQLAlchemy `Vector` type. It is a hard dependency, not an optional one like
   `pypdf`: `models/document_chunk.py` imports it, so the model must load
   whether or not RAG is enabled.

3. **The migration** (`c63fa2b5e819`): `CREATE EXTENSION vector`, add
   `embedding_vector vector(1536)`, backfill with `embedding::text::vector`,
   drop the JSONB column, rename into place, add the HNSW cosine index.

   Chunks whose JSONB array was not 1536 long are **deleted**, with the count
   raised as a notice. They had no representation in the new column, retrieval
   already refused them for having the wrong width, and they are regenerable
   by re-indexing. Admitting them as NULL would have cost the NOT NULL
   invariant permanently.

4. **The store.** `PgVectorStore` replaced `JsonbVectorStore` and
   `_default_store` changed. Nothing else did.

The downgrade rebuilds the JSONB column from the vectors and loses nothing:
`vector::text` is a JSON array of the same numbers, verified to round-trip
exactly with a real 1536-dimensional chunk.

## 11. Running and using it

### Enable it

In `backend/.env`:

```
RAG_ENABLED=true
OPENAI_API_KEY=sk-...
```

Then `docker compose up -d --build backend`.

### Index a document

```bash
curl -X POST "http://localhost:8000/api/v1/rag/documents/<DOCUMENT_ID>/index" -H "Authorization: Bearer <TOKEN>"
```

Returns `202` with `status: "READY"`, `pageCount` and `chunkCount`. Add
`?force=true` to re-claim a document stuck in `INDEXING` after an interrupted
run. Re-indexing replaces chunks; it never duplicates them.

### Check status

```bash
curl "http://localhost:8000/api/v1/rag/documents/<DOCUMENT_ID>/status" -H "Authorization: Bearer <TOKEN>"
```

### Ask a question

```bash
curl -X POST "http://localhost:8000/api/v1/rag/query" -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"projectId":"<PROJECT_ID>","query":"What is the retention percentage?"}'
```

```json
{
  "answer": "Retention is five per cent of each interim payment certificate [1].",
  "found": true,
  "citations": [
    { "documentId": "…", "title": "Main Contract", "page": 2,
      "snippet": "Retention is five per cent of each interim payment certificate." }
  ],
  "chunksUsed": 3
}
```

Omit `documentId` to search every readable, indexed document in the project;
include it to restrict the search to one.

## 12. Unified retrieval across both sources

A chunk's text comes from a `Document` or an `IngestedFile`, and one query
searches both.

```
question
   ↓
readable_document_ids(db, user, project)        ── documents' four-layer rule
readable_ingested_file_ids(db, user, project)   ── the same rule, derived
   ↓
VectorStore.search(project_id, documents, files, …)
   ↓
ScoredChunk(source=ChunkSource(…))
   ↓
Citation → RagCitation(sourceType, documentId | ingestedFileId, title, page)
```

**The invariant.** Both id sets are mandatory keyword arguments with no
defaults. Passing `[]` means zero readable sources of that type, and with both
empty the store returns before building a query — so no code path scans a
project without an explicit, caller-resolved list of what may be read. The
document parameter was *renamed* from `document_ids` to `readable_document_ids`
so a caller that predates this fails with a `TypeError` rather than silently
searching one source type.

**Ingested-file authorization is derived from the document rule, layer by
layer, and is never weaker.** A file has no share table and no task, so the
party and discipline scopes cannot be applied mechanically: the party scope
reduces to *own uploads only* (the shared set is empty — deny-by-default), and
the discipline scope grants all files (a file has no task, i.e. is
project-level, which that predicate already grants for documents). A naive
"project access plus `document.view`" would have been strictly weaker: an
external contractor reads only shared documents but would have read every file
on the project. See `services/document_access.py`.

**Titles.** A document cites by `title`, a file by `original_filename`. The
title query selects those two columns specifically — a `select(IngestedFile)`
would pull `storage_key` into memory one refactor from being serialised.

**Compatibility.** `RagCitation.documentId` is populated exactly as before for
a document citation; `sourceType` and `ingestedFileId` are additive.

## 13. Re-embedding and index maintenance

Two problems that only appear once a corpus has existed for a while: the
embedding model changes, and a worker dies mid-index.

### Detecting what needs re-embedding

A chunk records `embedding_model` and `embedding_dim`. A source is stale when
any of its chunks disagrees with the configured model — **derived, never
stored**. A flag would be wrong the moment configuration changed without it
being updated, which is exactly the moment it matters.

`GET /rag/projects/{id}/reindex` reports this without starting anything:

```json
{"embeddingSummary": {"configuredModel": "text-embedding-3-small",
                      "totalChunks": 412, "staleChunks": 88,
                      "needsReembedding": true,
                      "models": [{"model": "text-embedding-ada-002",
                                  "chunks": 88, "current": false}]}}
```

Configuration changing never re-embeds anything on its own. It makes the fact
*visible*; spending the credits stays a decision somebody makes.

### Re-indexing a project

```
POST /rag/projects/{id}/reindex   {"scope": "STALE"}   → 202
```

```
project
   ↓  eligible_sources(project_id, scope)   ← the data boundary
sources (Document | IngestedFile)
   ↓  reindex_source → ingestion.index_document / index_ingested_file
chunks  (add_chunks replaces, so re-running cannot duplicate)
   ↓
vector(1536)
```

Three scopes: `STALE` (default — only outdated vectors, the cheapest),
`FAILED` (retry what failed), `ALL` (every indexed-or-attempted source). A
`NOT_INDEXED` source is in none of them: re-indexing means indexing *again*,
and doing it implicitly would spend credits on every file that ever landed.

The endpoint returns as soon as the job row exists. The work runs on
`services/processing_pool.py` — the *same* bounded pool IFC parsing, file
processing and single-file indexing use, so `IFC_MAX_CONCURRENT_PROCESSING`
remains one ceiling over all heavy work.

**No transaction spans the run.** Each source is committed as it finishes, so
a crash at source 73 leaves 1–72 genuinely indexed. The job's counters are
committed alongside, so its progress is real rather than a guess made at the
end. A run with both successes and failures settles as `PARTIAL`.

### Duplicate runs

`ix_rag_index_jobs_one_active_per_project` is a **partial unique index** over
`project_id` where the status is QUEUED or RUNNING. Two simultaneous requests
both insert; one violates the index and gets a 409. A check-then-insert would
be a race whose loser starts a second full re-embedding pass.

### Recovering a stranded run

A worker that dies mid-index leaves `index_status = INDEXING` forever — the
concurrency guard cannot tell a dead run from a live one, so every later
attempt is refused. Before this, the only way out was somebody noticing and
passing `force=true`.

```
INDEXING  ──(index_started_at older than RAG_INDEX_STALE_MINUTES)──►  FAILED
                                                                       │
                                                        explicit retry ┘
```

`index_started_at` exists because neither existing timestamp can answer the
question: `indexed_at` is written only on success, and `updated_at` moves for
any edit. A NULL start on an INDEXING row counts as stale — those are rows
claimed before the column existed.

Two things it deliberately does **not** do:

* **It does not delete chunks.** The run may have died after writing every
  chunk and before writing the status; deleting would turn a recoverable
  interruption into data loss. A retry replaces them wholesale anyway.
* **It does not retry automatically.** The row moves to FAILED with a readable
  reason, which makes it eligible for an explicit retry or a `FAILED`-scoped
  run. An automatic retry here would be an unbounded loop over a source that
  fails deterministically.

A stranded *project job* is re-queued rather than failed, bounded by
`attempt` — after `RAG_REINDEX_MAX_ATTEMPTS` it is given up on.

The sweep runs on the existing scheduler (`services/scheduler.py`), on the
same asyncio loop as the reminder sweep but under its **own** advisory lock,
so a slow reminder pass on one worker cannot stop the reaper on another.

### HNSW is not rebuilt

pgvector maintains the index on ordinary INSERT and DELETE. A `REINDEX` per
run would rebuild the whole structure to replace a handful of rows. If index
maintenance is ever genuinely needed it is a database operation on a schedule,
kept separate from anything the application does on a user's behalf.

## 14. Testing

```bash
docker compose exec backend python -m pytest tests/test_rag_pipeline.py tests/test_rag_api.py -q
```

**OpenAI is stubbed throughout** — no test makes a network call, and the suite
needs no API key and costs nothing. The stub produces deterministic embeddings
from word overlap, so retrieval tests are meaningful rather than tautological:
a question about retention genuinely scores highest against the passage that
mentions retention.

Test PDFs are built in pure Python (`tests/pdf_fixture.py`) rather than with
reportlab, so the suite gains no dependency for a fixture — and they are real
PDFs, so extraction is genuinely exercised.

## 15. Known limitations

- **Approximate recall.** HNSW is an approximate index; a chunk genuinely in
  the top-k can be missed. `hnsw.ef_search` trades recall for latency and is
  left at pgvector's default.
- **One embedding model at a time.** `vector(1536)` holds one width, so a
  corpus cannot mix models. Changing model means a migration and a re-index.
- **No hybrid search.** No lexical (BM25/`tsvector`) arm, so a term a passage
  uses verbatim ranks only as well as its embedding does.
- **No OCR.** A scanned PDF with no text layer is refused with a message
  saying so.
- **No drawing or image understanding.** DWG/DXF and images are stored and
  classified, never read. Spreadsheet cell values are not read either.
- **No conversational memory.** Each question is independent.
- **Document indexing is synchronous**; `POST /rag/documents/{id}/index` holds
  the request open for the duration. Ingested-file indexing is not — it runs on
  the shared bounded pool.
- **A process that dies mid-index** leaves the row in `INDEXING` until the
  reaper takes it back — within `RAG_INDEX_STALE_MINUTES`, or immediately with
  `?force=true`. See §13.
- **No re-index on replacement.** Uploading a new version does not re-index
  automatically; indexing is explicit by design, so nobody spends embedding
  credits on every file that lands in a project.
- **A re-index is per project.** There is no cross-project or platform-wide
  sweep, so a model change has to be actioned project by project.
- **A run is not resumable mid-source.** An interrupted run keeps every source
  it finished and re-does the one it was on; there is no chunk-level
  checkpoint, which for a single document is seconds of work.
- **No file-level sharing for external parties.** A contractor can only reach
  ingested files they uploaded themselves, because no share mechanism exists
  for them yet.
