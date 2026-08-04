export interface AIInsight {
  id:string;projectId:string;modelRevisionId?:string;insightType:string;category:string;severity:string;confidence:number;
  title:string;description:string;reason:string;recommendedAction:string;potentialImpact?:string;
  evidenceJson:Record<string,unknown>;affectedJson:{elements?:string[];storeys?:string[];spaces?:string[];buildings?:string[];disciplines?:string[];categories?:string[]};
  relatedTaskIdsJson:string[];relatedIssueIdsJson:string[];relatedEvidenceIdsJson:string[];sourceEngine:string;status:string;
  reviewNote?:string;reviewedById?:string;reviewedAt?:string;resolvedAt?:string;appliedEntityType?:string;appliedEntityId?:string;createdAt:string;updatedAt:string;
}
export interface AIInsightSource {
  id:string;insightId:string;projectId:string;sourceType:string;sourceId:string;sourceLabel?:string;
  sourceState:string;sourceVersion?:string;snapshotHash:string;isValid:boolean;invalidatedAt?:string;invalidationReason?:string;
  createdAt:string;updatedAt:string;
}
export interface AIIntelligenceOverview {
  openInsights:number;severityCounts:Record<string,number>;categoryCounts:Record<string,number>;statusCounts:Record<string,number>;
  alignment?:{overall:number;components:Record<string,number>;weights:Record<string,number>;ifcDisciplines:Record<string,number>;taskDisciplines:Record<string,number>;taskCount:number;issueCount:number;linkedTaskCount:number;linkedIssueCount:number;linkedEvidenceCount:number};
  latestRevision?:{id:string;revisionCode?:string;title:string};engineeringReviewNotice:string;
}
