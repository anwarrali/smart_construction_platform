/**
 * The unified file ingestion pipeline, as the client sees it.
 *
 * Mirrors `backend/app/schemas/ingestion.py`. Two absences are deliberate and
 * must stay: there is no `storageKey` field, because the server never sends
 * one, and no raw `errorMessage`, because the internal detail stays on the
 * server. `error` is the publishable failure and is the only thing to show.
 */

/** Where a file is in its lifecycle. Mirrors `services/ingestion/state.py`. */
export type IngestionStatus =
  | "UPLOADED"
  | "VALIDATING"
  | "CLASSIFIED"
  | "QUEUED"
  | "PROCESSING"
  | "READY"
  /** Processed to completion, but less was extracted than the format allows. */
  | "PARTIAL"
  | "FAILED";

/** The normalized kind the pipeline dispatched on. */
export type FileCategory =
  | "IFC"
  | "PDF"
  | "DOC"
  | "DOCX"
  | "XLS"
  | "XLSX"
  | "DRAWING"
  | "IMAGE"
  | "TEXT"
  | "ZIP_PACKAGE"
  | "OTHER";

/** A failure a person can act on. Composed by the server; never a stack trace. */
export interface IngestionError {
  code: string;
  title: string;
  description: string;
  retryable: boolean;
  suggestedAction: string;
}

export interface IngestedFile {
  id: string;
  projectId: string;
  uploadedById: string;
  /** The package this file came out of, when it did not arrive on its own. */
  parentFileId?: string | null;

  originalFilename: string;
  contentType?: string | null;
  detectedFormat?: string | null;
  fileCategory: FileCategory;
  /** Advisory: BOQ, SCHEDULE, DRAWING… Never overrides a person's own choice. */
  documentKind?: string | null;
  fileSizeBytes: number;

  status: IngestionStatus;
  progress: number;
  processorName?: string | null;
  error?: IngestionError | null;

  classificationJson: Record<string, unknown>;
  metadataJson: Record<string, unknown>;

  checksumSha256?: string | null;
  /** An earlier file in this project with identical bytes, if there is one. */
  duplicateOfId?: string | null;
  sourceEntityType?: string | null;
  sourceEntityId?: string | null;

  processingStartedAt?: string | null;
  processingCompletedAt?: string | null;

  /**
   * RAG indexing, separate from `status` (processing): a file can be READY and
   * not yet indexed. Optional so an older server's response still parses.
   */
  indexStatus?: IndexStatus;
  indexedAt?: string | null;
  /** The server's readable reason for a failed index. */
  indexError?: string | null;
  createdAt: string;
  updatedAt: string;
}

/** Whether a file's text is searchable. Mirrors `services/rag/ingestion.py`. */
export type IndexStatus = "NOT_INDEXED" | "INDEXING" | "READY" | "FAILED";

/**
 * After a file with text settles, the server queues its indexing; the job is
 * claimed a moment later. Polling keeps going for this long so the panel sees
 * indexing start instead of stopping one poll too early.
 */
export const INDEX_PICKUP_GRACE_MS = 2 * 60 * 1000;

/**
 * Whether the list should keep refreshing for this file's indexing.
 *
 * True while it is INDEXING, and for a short window after a file with
 * extracted text settles but before its index job has been picked up. Not for
 * a file with no text (a drawing, an image, a model): nothing will index it.
 * `now` is passed in, never read here, so a render stays pure.
 */
export const awaitsIndexing = (file: IngestedFile, now: number): boolean => {
  if (file.indexStatus === "INDEXING") return true;
  if (file.indexStatus && file.indexStatus !== "NOT_INDEXED") return false;
  if (!["READY", "PARTIAL"].includes(file.status) || file.duplicateOfId) return false;
  if (file.metadataJson?.extraction !== "TEXT" || !file.processingCompletedAt) return false;
  return now - Date.parse(file.processingCompletedAt) < INDEX_PICKUP_GRACE_MS;
};

export interface IngestedFilePage {
  items: IngestedFile[];
  total: number;
  limit: number;
  offset: number;
}

export interface IngestionUploadConstraints {
  maxFileBytes: number;
  maxFileMb: number;
  acceptedExtensions: string[];
  maxPackageEntries: number;
  maxPackageTotalBytes: number;
  maxPackageDepth: number;
  categories: FileCategory[];
}

export interface IngestionRetryResult {
  file: IngestedFile;
  queued: boolean;
}

export interface IngestedFileFilters {
  category?: FileCategory;
  status?: IngestionStatus;
  parentId?: string;
  rootOnly?: boolean;
  limit?: number;
  offset?: number;
}

/** Statuses in which the pipeline is still working and the client should poll. */
export const IN_FLIGHT_STATUSES: readonly IngestionStatus[] = [
  "UPLOADED",
  "VALIDATING",
  "CLASSIFIED",
  "QUEUED",
  "PROCESSING",
];

export const isInFlight = (status: IngestionStatus): boolean =>
  IN_FLIGHT_STATUSES.includes(status);
