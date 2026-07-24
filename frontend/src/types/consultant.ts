export interface ConsultantPerson { id: string; fullName: string; role: string; specialization?: string; organizationSide?: string }
export interface ConsultantReviewSummary {
  id: string; taskId: string; taskCode: string; taskTitle: string; description?: string;
  projectId: string; projectName: string; discipline: string; priority: string; taskStatus: string;
  reviewStatus: string; submissionNumber: number; isResubmission: boolean; submittedBy?: ConsultantPerson;
  submittedAt: string; reviewDueDate?: string; isOverdue: boolean; isCritical: boolean;
  dependentTasksBlocked: number; blocksDependentWork: boolean; evidenceCount: number;
  previousRejectionCount: number; completionNote?: string; clarificationQuestion?: string;
  clarificationResponse?: string; reviewer?: ConsultantPerson; reviewedAt?: string; comments?: string;
  rejectionReason?: string; requiredCorrections?: string;
}
export interface ConsultantDashboardData {
  project: { id: string; name: string; status: string; completionPercentage: number };
  specialization: string; stats: Record<string, number>; pendingReviews: ConsultantReviewSummary[];
  criticalReviews: ConsultantReviewSummary[];
  reworkAwaitingResubmission: Array<{ taskId: string; taskCode: string; taskTitle: string; rejectionReason?: string; requiredCorrections?: string }>;
  recentActivity: Array<{ id: string; action: string; entityType: string; entityId?: string; actor?: ConsultantPerson; timestamp: string }>;
  projectSummary: { taskCounts: Record<string, number>; totalTasks: number; delayedTasks: number; criticalTasks: number; upcomingMilestones: Array<{ id: string; name: string; plannedDate: string; completed: boolean }> };
}
export interface ConsultantReviewDetail {
  review: ConsultantReviewSummary; task: Record<string, any>; submissionEvidence: Array<Record<string, any>>;
  currentTaskEvidence: Array<Record<string, any>>; dependencies: Array<Record<string, any>>;
  dependents: Array<Record<string, any>>; history: ConsultantReviewSummary[];
  comments: Array<Record<string, any>>; documents: Array<Record<string, any>>;
  siteReports: Array<Record<string, any>>; issues: Array<Record<string, any>>;
}
