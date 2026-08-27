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
  │ store        vectors     ──► JSONB + cosine, behind VectorStore │
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
only module that knows a vector is stored as JSONB** — see §9.

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

## 4. Retrieval flow

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
| `document_id` | UUID | FK → `documents.id` ON DELETE CASCADE |
| `project_id` | UUID | FK → `projects.id`. Denormalised on purpose — see below |
| `page_number` | int | 1-based. **NOT NULL** |
| `chunk_index` | int | order within the document |
| `content` | text | |
| `token_count` | int | |
| `embedding` | JSONB | float array. **Never returned by the API** |
| `embedding_model` | varchar(100) | so a model change is detected |
| `embedding_dim` | int | vectors of another length are skipped, not compared |
| `created_at` | timestamptz | |

Indexes: `(document_id, chunk_index)`, `(document_id, page_number)`,
`project_id`, `document_id`.

*`project_id` is denormalised* so every retrieval query filters on the project
column directly. A join that must be remembered is a join that will eventually
be forgotten, and forgetting this one leaks another project's document text.

*`page_number` is NOT NULL* because a chunk that cannot name its page cannot be
cited, and an uncitable chunk has no place here. Chunking therefore never spans
a page boundary.

**`documents`** gains `index_status`, `indexed_at`, `index_error`,
`page_count`.

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

## 9. Limitations of JSONB vector storage

This MVP stores vectors as JSONB and computes cosine similarity in Python with
numpy. That is a deliberate trade, and these are its real costs:

- **Retrieval is a linear scan.** Every candidate chunk is loaded and scored on
  every question. For one document (tens to hundreds of chunks) this is
  sub-millisecond. At tens of thousands of chunks it becomes the slowest part
  of the request.
- **Storage is inefficient.** A 1536-float vector is roughly 30 KB as JSON
  text, versus about 6 KB as a native `vector`. A 500-chunk document costs
  ~15 MB.
- **Every candidate is transferred** from PostgreSQL to the application on
  every query, rather than the ranking happening in the database.
- **No approximate-nearest-neighbour index** is possible, so there is no way to
  trade a little accuracy for a lot of speed.

What it buys: the stock `postgres:15` image with no extension, no change to
your database infrastructure, and no operational risk today.

## 10. Migrating to pgvector later

The migration is contained because **nothing outside `store.py` knows vectors
are in JSONB**. Nothing else reads `embedding`, computes a similarity, or names
JSONB.

1. Change the database image to `pgvector/pgvector:pg15` (same PostgreSQL major
   version, so the existing volume works unchanged).
2. `CREATE EXTENSION vector;` in a migration; add a `vector(1536)` column,
   backfill from the JSONB, drop the old column, and create an HNSW or IVFFlat
   index.
3. Write `PgVectorStore` implementing the same three methods, with the ordering
   done in SQL (`ORDER BY embedding <=> :query LIMIT :k`).
4. Change the one line in `store.py` that builds `_default_store`.

No service, API, schema, or test outside the store needs to change. Chunks
would need re-embedding only if the embedding *model* changes, not the storage.

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

## 12. Testing

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

## 13. Known limitations of this MVP

- **PDF only.** No ZIP or design-package ingestion.
- **No OCR.** A scanned PDF with no text layer is refused with a message
  saying so.
- **No drawing or image understanding.** Text only.
- **No conversational memory.** Each question is independent; there is no
  follow-up context.
- **Indexing is synchronous.** A large PDF holds the request open for the
  duration. A background job would be the next step.
- **A process that dies mid-index** leaves the document in `INDEXING`. The
  status endpoint shows it; `?force=true` re-claims it. There is no reaper.
- **No re-index on document replacement.** Uploading a new version does not
  re-index automatically — indexing is explicit by design.
- **Retention of stale vectors.** If `OPENAI_EMBEDDING_MODEL` changes, existing
  chunks are skipped at query time (their dimension no longer matches) rather
  than silently compared across incompatible spaces. Re-index to restore them.
