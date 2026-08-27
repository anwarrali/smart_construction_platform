export type IFCDataSource = "IFC_SOURCE" | "CALCULATED" | "AI_INFERRED" | "USER_ENTERED" | "MISSING";

export interface IFCModelGroup {
  id: string; projectId: string; name: string; discipline?: string; description?: string;
  activeVersionId?: string; baselineVersionId?: string; archivedAt?: string;
}

export interface IFCMetric { count: number; total: number; percentage: number }
export interface IFCGeoreferencing {
  status?: string; impact?: string; coordinateReferenceSystem?: string; epsgCode?: string;
  latitude?: number; longitude?: number; easting?: number; northing?: number; elevation?: number;
  orthogonalHeight?: number; mapConversion?: Record<string, unknown>; source?: IFCDataSource;
}
export interface IFCSummary {
  schema?: string; sites?: number; buildings?: number; storeys?: number; spaces?: number; zones?: number; elements?: number;
  projectOverview?: Record<string, unknown> & { sources?: Record<string, IFCDataSource> };
  mainStatistics?: Record<string, number>; modelCompleteness?: Record<string, IFCMetric>;
  disciplineBreakdown?: Record<string, number>; majorElementCategories?: Record<string, number>;
  hierarchyCounts?: Record<string, number>; georeferencing?: IFCGeoreferencing; units?: Record<string, string>;
  warnings?: string[]; revision?: string; versionType?: string; modelGroup?: string;
  processingStages?: Array<{ key: string; label: string; percentage: number }>;
  assetType?: { value?: string; confidence?: number; evidence?: string[] };
  spaceCategories?: Record<string, number>;
  intelligenceSummary?: { text?: string; strengths?: string[]; missingInformation?: string[]; coordinationRisks?: string[]; recommendedNextSteps?: string[]; source?: string; reviewNotice?: string };
}

/** The server's upload rules, fetched so the client can check a file before sending it. */
export interface IFCUploadConstraints {
  maxFileBytes: number; maxFileMb: number; acceptedExtensions: string[];
  maxEntityCount: number; supportedSchemas: string[]; geometryEnabled: boolean;
}

export interface IFCVersion {
  id: string; modelGroupId: string; projectId: string; versionNumber: number;
  revisionCode?: string; versionType: string; title: string; description?: string; discipline?: string;
  originalFilename: string; fileHash: string; fileSize: number; ifcSchema?: string;
  authoringApplication?: string; processingStatus: string; processingProgress: number;
  processingDurationMs?: number; parsingErrorCode?: string; parsingErrorMessage?: string; supportLogId?: string;
  entityCount: number; geometryStatus: string;
  geometryError?: string; geometryStatsJson?: Record<string, unknown>; geometryGeneratedAt?: string;
  analysisStatus: string; modelSummaryJson: IFCSummary; isActive: boolean; createdAt: string;
  isBaseline: boolean; assetTypeSuggestion?: string; assetTypeConfidence?: number;
}

export interface IFCSpatialNode {
  id: string; versionId: string; globalId: string; entityType: string; name: string; description?: string;
  parentId?: string; nodeType: string; elevation?: number; area?: number; volume?: number; metadataJson?: Record<string, unknown>;
}

export interface IFCSpatialDetails {
  node: IFCSpatialNode; childCounts: Record<string, number>; elementCount: number;
  elementCategories: Record<string, number>; disciplines: Record<string, number>; relatedElementIds: string[];
  projectActivity: Record<string, number>; measurements: Record<string, { value: number; unit?: string; sourceType: string; sourceProperty?: string; confidence: number } | null>;
  spaceClassification?: { category: string; label: string; confidence: number; source: string; evidence?: string; method: string };
  availabilityNotice: string;
}

export interface IFCClassification { system?: string; code?: string; name?: string; source?: IFCDataSource }
export interface IFCElementMetadata {
  stepId?: number; originalName?: string; sourceGlobalId?: string; classifications?: IFCClassification[];
  disciplineSource?: IFCDataSource; disciplineConfidence?: number; disciplineReason?: string;
  disciplineSourceAttributes?: string[]; missingData?: string[]; completenessStatus?: "COMPLETE" | "PARTIAL" | "INCOMPLETE";
  materialStatus?: "DEFINED" | "VIRTUAL_REFERENCE" | "MISSING_FROM_SOURCE"; units?: Record<string, string>;
}
export interface IFCElement {
  id: string; versionId: string; globalId: string; entityType: string; name: string;
  description?: string; objectType?: string; predefinedType?: string; tag?: string; storeyNodeId?: string;
  spaceNodeId?: string; zoneNodeId?: string; buildingNodeId?: string; discipline?: string; systemName?: string; typeName?: string;
  materialSummary?: string; propertiesJson: Record<string, unknown>; quantitiesJson: Record<string, unknown>;
  boundingBoxJson?: Record<string, unknown>; geometryReference?: string; geometryHash?: string; placementHash?: string;
  metadataJson: IFCElementMetadata;
}

export interface IFCComparison {
  id: string; baseVersionId: string; targetVersionId: string; status: string;
  summaryJson: { total?: number; counts?: Record<string, number>; disciplineBreakdown?: Record<string, number>; comparisonConfidence?: string; unstableIdentifierCount?: number; confidenceMessage?: string };
  createdAt: string; error?: string;
}

/** One element as an interference finding describes it. */
export interface IFCInterferenceParty {
  elementId: string; globalId: string; name: string; entityType: string;
  discipline?: string; storey?: string; system?: string;
  boundingBox?: { min: number[]; max: number[] };
}

export interface IFCFinding {
  id: string; versionId: string; findingType: string; severity: string; title: string; description: string;
  discipline: string; disciplines: string[]; status: string; ifcRule: string; whyItMatters: string;
  recommendedAction: string; affectedElementIds: string[]; affectedElementCount: number; createdAt: string;
  /** How far the detection method can be trusted. Metadata-quality rules are 1. */
  confidence?: number;
  storey?: string; space?: string;
  /** Present on geometry-derived findings: what is being claimed, and how to check it. */
  claim?: string; verification?: string;
  /** Present on interference findings: the two elements and the measured overlap. */
  elementPair?: {
    structural?: IFCInterferenceParty; service?: IFCInterferenceParty;
    penetrationMetres?: number; overlapBox?: { min: number[]; max: number[] };
  };
}

export interface IFCSuggestion {
  id: string; versionId: string; suggestionType: string; payloadJson: Record<string, unknown>;
  title: string; discipline: string; priority: string; reason: string; affectedElementCount: number;
  expectedBenefit: string; recommendedAction: string; sourceFinding: string;
  confidence: number; status: string; aiInferred: boolean; createdAt: string;
}
