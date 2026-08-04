export interface AIActionVersion {
  id: string;
  projectId: string;
  actorUserId: string;
  voiceAnalysisId?: string;
  parentActionId?: string;
  revertedActionId?: string;
  source: string;
  intent: string;
  originalInput?: string;
  aiInterpretation: Record<string, unknown>;
  finalCommand: Record<string, unknown>;
  entityType: string;
  entityId: string;
  beforeState?: Record<string, unknown>;
  afterState?: Record<string, unknown>;
  approvalInfo: Record<string, unknown>;
  result: string;
  requestId: string;
  correlationId: string;
  undoPolicy: string;
  undoAvailable: boolean;
  undoReason?: string;
  createdAt: string;
}

export interface AIActionPage {
  items: AIActionVersion[];
  page: number;
  pageSize: number;
  total: number;
}
