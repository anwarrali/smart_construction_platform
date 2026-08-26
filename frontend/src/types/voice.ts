export interface VoiceActionDraft {
  id: string;
  clientActionId: string;
  sequence: number;
  actionType: string;
  targetEntityType?: string;
  targetEntityId?: string;
  extractedPayload: Record<string, unknown>;
  userEditedPayload?: Record<string, unknown>;
  targetSnapshot?: {
    taskId?: string;
    status: string;
    progressPercentage: number;
    updatedAt: string;
  };
  confidence: number;
  missingFields: string[];
  warnings: string[];
  riskLevel: "INFORMATIONAL" | "LOW" | "MEDIUM" | "HIGH";
  requiredEvidence: string[];
  selectedForExecution: boolean;
  executionStatus: string;
  executionError?: string;
}

/**
 * One option on a clarification question.
 *
 * The backend ranks these, so the order is meaningful and must not be re-sorted
 * in the UI: `score` and `reasons` explain *why* a task is being offered, which
 * is what lets an engineer dismiss a wrong candidate without reading all of
 * them.
 */
export interface VoiceClarificationOption {
  value: string;
  label: string;
  status?: string;
  progressPercentage?: number;
  discipline?: string;
  score?: number;
  reasons?: string[];
}

export interface VoiceClarification {
  id: string;
  voiceActionDraftId?: string;
  sequence: number;
  fieldPath: string;
  questionAr: string;
  questionEn: string;
  expectedAnswerType: "TASK_SELECTION" | "NUMBER" | "TEXT" | string;
  options: VoiceClarificationOption[];
  answerText?: string;
  answerSource?: string;
  answeredAt?: string;
}

export interface VoiceTaskCandidate {
  taskId: string;
  taskCode?: string;
  name: string;
  status: string;
  progressPercentage: number;
  discipline?: string;
  score: number;
  reasons: string[];
}

export interface VoiceTaskCandidates {
  resolvedTaskId?: string;
  confidence: number;
  candidates: VoiceTaskCandidate[];
}

/** Server-side stage timings, in milliseconds. Never contains speech content. */
export interface VoiceLatencyMs {
  transcription?: number;
  context?: number;
  analysis?: number;
  drafting?: number;
  total?: number;
}

/**
 * The assistant's own sentence, composed for the question that was asked and
 * in the language it was asked in.
 *
 * `text` is what to show. `textEn`/`textAr` are the deterministic templates the
 * backend falls back to when phrasing is unavailable, kept so a client can pick
 * a language itself if it needs to.
 */
export interface VoiceAnswer {
  topic: string;
  text: string;
  language: string;
  textEn: string;
  textAr: string;
  data?: Record<string, unknown>;
}

export interface VoiceCommand {
  id: string;
  projectId: string;
  userId: string;
  taskId?: string;
  fieldSubmissionId?: string;
  rawTranscript?: string;
  normalizedTranscript?: string;
  detectedLanguage?: string;
  status: string;
  rowVersion: number;
  overallConfidence?: number;
  errorCode?: string;
  errorDetail?: string;
  providerMetadata?: {
    latencyMs?: VoiceLatencyMs;
    /** ANSWER | ACTION | COMMUNICATION | CLARIFICATION. */
    route?: string;
    /** The language the backend replied in — the one that was spoken. */
    replyLanguage?: string;
  } & Record<string, unknown>;
  structuredResult?: {
    summary?: string;
    humanSummaryAr?: string;
    humanSummaryEn?: string;
    detectedIntents?: string[];
    suggestedActions?: Array<{
      type: string;
      payload: Record<string, unknown>;
      confidence: number;
    }>;
    /**
     * What the assistant said back: either the answer to a question or the one
     * thing it still needs to know. Present for reads and for half-finished
     * requests; absent when a complete proposal is waiting to be confirmed.
     */
    answer?: VoiceAnswer;
  };
  actionDrafts: VoiceActionDraft[];
  clarifications: VoiceClarification[];
  actionResults?: Array<{
    actionIndex?: number;
    type: string;
    success: boolean;
    status: string;
    /** The backend's own English wording. For logs and support, never shown. */
    message: string;
    /**
     * What happened, phrased for the person and in the language they spoke.
     * Present on both outcomes: what was done, or why it was not. Shown in
     * place of `message`, which names internal rules and fields.
     */
    userMessage?: string;
    /** Stable classification behind `userMessage`. Never displayed. */
    errorCode?: string;
    entityId?: string;
  }>;
  createdAt: string;
}

export interface VoiceReportUpdate {
  voiceCommandId: string;
  actionType: string;
  taskId?: string;
  taskCode?: string;
  taskName?: string;
  discipline?: string;
  beforeState?: Record<string, unknown>;
  afterState?: Record<string, unknown>;
  summary?: string;
  reportedById: string;
  reportedAt: string;
}

export interface VoiceReportReadiness {
  projectId: string;
  reportDate: string;
  ready: boolean;
  updateCount: number;
  taskCount: number;
  disciplines: string[];
  updates: VoiceReportUpdate[];
}

/** Client-measured stage timings, for the latency the engineer actually feels. */
export interface VoiceClientTiming {
  micStartMs?: number;
  recordingMs?: number;
  uploadAndProcessMs?: number;
  firstPartialTranscriptMs?: number;
  totalMs?: number;
}
