/** Document question answering. Mirrors `backend/app/schemas/rag.py`. */

/** NOT_INDEXED — never indexed. INDEXING — a run is in flight.
 *  READY — queryable. FAILED — the last run failed; `error` says why. */
export type IndexStatus = "NOT_INDEXED" | "INDEXING" | "READY" | "FAILED";

export interface DocumentIndexStatus {
  documentId: string;
  status: IndexStatus;
  pageCount: number | null;
  chunkCount: number;
  indexedAt: string | null;
  error: string | null;
}

/** Where a cited passage came from. A citation always names exactly one. */
export type RagSourceType = "DOCUMENT" | "INGESTED_FILE";

/** A passage the answer was built from. Always points at a real retrieved
 *  chunk — the server constructs these from its own records rather than
 *  parsing them out of the model's prose, so a page here can be opened and
 *  checked.
 *
 *  `documentId` is populated exactly as before for a library document, and is
 *  null for a passage retrieved from an ingested file. Branch on `sourceType`
 *  rather than null-checking two ids. */
export interface RagCitation {
  sourceType: RagSourceType;
  /** Set when `sourceType` is "DOCUMENT". */
  documentId: string | null;
  /** Set when `sourceType` is "INGESTED_FILE". */
  ingestedFileId: string | null;
  /** A document's title, or a file's original filename. Never a storage key. */
  title: string;
  page: number;
  snippet: string;
}

export interface RagQueryResponse {
  answer: string;
  /** False when the indexed text did not support an answer. Rendered
   *  differently rather than pattern-matching the wording. */
  found: boolean;
  citations: RagCitation[];
  chunksUsed: number;
}
