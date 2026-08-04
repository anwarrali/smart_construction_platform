export interface VoiceActionDraft {
  id: string;
  clientActionId: string;
  actionType: string;
  targetEntityId?: string;
  extractedPayload: Record<string, unknown>;
  userEditedPayload?: Record<string, unknown>;
  targetSnapshot?: {
    status: string;
    progressPercentage: number;
    updatedAt: string;
  };
  confidence: number;
  missingFields: string[];
  warnings: string[];
  riskLevel: "INFORMATIONAL" | "LOW" | "MEDIUM" | "HIGH";
  requiredEvidence: string[];
  executionStatus: string;
}

export interface VoiceCommand {
  id: string;
  projectId: string;
  taskId?: string;
  fieldSubmissionId?: string;
  rawTranscript?: string;
  normalizedTranscript?: string;
  detectedLanguage?: string;
  status: string;
  rowVersion: number;
  structuredResult?: {
    summary?: string;
    suggestedActions?: Array<{
      type: string;
      payload: Record<string, unknown>;
      confidence: number;
    }>;
  };
  actionDrafts: VoiceActionDraft[];
  createdAt: string;
}
