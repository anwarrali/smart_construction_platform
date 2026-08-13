export type ProjectStatus =
  | "planning"
  | "active"
  | "on_hold"
  | "delayed"
  | "completed"
  | "cancelled";
export type Priority = "low" | "medium" | "high" | "critical";

export interface Project {
  id: string;
  name: string;
  description?: string;
  location?: string;
  projectType?: string;
  status: ProjectStatus;
  startDate?: string;
  plannedEndDate?: string;
  actualEndDate?: string;
  budgetTotal?: number;
  budgetSpent?: number;
  completionPercentage: number;
  openIssueCount: number;
  ownerId: string;
  projectManagerId?: string;
  consultantApprovalMode: ApprovalMode;
  projectManager?: {
    id: string;
    fullName: string;
    email: string;
    role: string;
  };
  coverImageUrl?: string;
  members: ProjectMember[];
  createdAt: string;
  updatedAt: string;
}

export interface ProjectMember {
  id: string;
  projectId: string;
  userId: string;
  roleOnProject: string;
  isActive: boolean;
  assignmentTitle?: string;
  projectDiscipline?: string;
  projectNotes?: string;
  isSiteEngineer: boolean;
  assignedById?: string;
  createdAt?: string;
  updatedAt?: string;
  user: {
    id: string;
    fullName: string;
    email: string;
    role: string;
    organization?: string;
    engineerAffiliation?: "internal_engineer" | "main_contractor" | "external_consultant";
    status: string;
    engineerProfile?: { discipline: string };
  };
}

export type ApprovalMode = "CENTRALIZED_REVIEW" | "DISCIPLINE_BASED_REVIEW";

export interface ProjectApprovalConfig {
  projectId: string;
  mode: ApprovalMode;
  centralizedReviewerId?: string;
  disciplineReviewers: Record<string, string[]>;
  reviewers: Array<{
    id: string;
    userId: string;
    discipline?: string;
    user: ProjectMember["user"];
  }>;
}

export interface ProjectApprovalConfigUpdate {
  mode: ApprovalMode;
  centralizedReviewerId?: string;
  disciplineReviewers: Record<string, string[]>;
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
  location?: string;
  projectType?: string;
  startDate?: string;
  plannedEndDate?: string;
  budgetTotal?: number;
  status?: ProjectStatus;
  ownerId?: string;
  projectManagerId?: string;
}

export interface UpdateProjectRequest {
  name?: string;
  description?: string;
  status?: ProjectStatus;
  location?: string;
  startDate?: string;
  plannedEndDate?: string;
  budgetTotal?: number;
  ownerId?: string;
  projectManagerId?: string;
}

export interface ProjectFilters {
  status?: ProjectStatus;
  search?: string;
  ownerId?: string;
  projectManagerId?: string;
  page?: number;
  limit?: number;
}

export interface ProjectsResponse {
  items: Project[];
  data: Project[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export interface ProjectSummary {
  totalProjects: number;
  activeProjects: number;
  completedProjects: number;
  delayedProjects: number;
  averageCompletion: number;
  totalBudget: number;
  totalSpent: number;
}

export interface OwnerDashboardData {
  projectSummary: {
    name: string;
    status: string;
    completionPercentage: number;
    currentPhase: string;
    startDate: string;
    plannedEndDate: string;
    daysRemaining: number;
    isDelayed: boolean;
  };
  costSummary: CostSummary;
  milestones: {
    id: string;
    name: string;
    plannedDate: string;
    actualDate?: string;
    status: "pending" | "completed" | "delayed";
  }[];
  recentActivities: {
    id: string;
    type: string;
    description: string;
    timestamp: string;
    user: string;
  }[];
  recentPhotos: {
    id: string;
    url: string;
    caption: string;
    taskName: string;
    uploadedAt: string;
  }[];
  projectHealth: "on_track" | "at_risk" | "delayed";
  delayedTasks: Array<{
    id: string;
    name: string;
    taskCode: string;
    daysDelayed: number;
    isCriticalPath: boolean;
  }>;
  openIssues: Array<{
    id: string;
    title: string;
    severity: "low" | "medium" | "high" | "critical";
    status: string;
    summary?: string;
  }>;
  attentionRequired: Array<{
    id: string;
    type: string;
    severity: string;
    title: string;
    summary: string;
    entityType: string;
    entityId: string;
  }>;
  projectBreakdown: Array<{
    name: string;
    taskCount: number;
    completionPercentage: number;
  }>;
  designChanges: Array<{
    id: string;
    title: string;
    summary?: string;
    reason?: string;
    status: string;
    costImpact: number;
    scheduleImpactDays: number;
  }>;
  consultantApprovals: { approved: number; pending: number; rejected: number };
  latestExecutiveUpdates: Array<{
    id: string;
    action: string;
    entityType: string;
    timestamp: string;
  }>;
  pendingOwnerRequests: Array<{ id: string; title: string; status: string; priority: string; discipline?: string; needsOwnerInput: boolean }>;
  upcomingSiteVisits: Array<{ id: string; title: string; scheduledStart: string; visitType: string; status: string; location?: string }>;
  recentVerifiedSiteReports: Array<{ id: string; reportDate: string; summary?: string; reviewStatus: string }>;
  sinceLastVisit: { periodDays: number; since?: string; basis?: "YOUR_PREVIOUS_VISIT" | "FIRST_RECORDED_VISIT"; previousVisitAt?: string | null; verifiedTasks: number; approvedDesignChanges: number; verifiedSiteReports: number; requestsAwaitingClarification: number; nextEngineerVisit?: string; officialInformationOnly: boolean };
}

export interface CostSummary {
  projectId: string;
  budgetTotal: number;
  budgetSpent: number;
  committedCost: number;
  pendingCost: number;
  variance: number;
  variancePercentage: number;
  updatedAt: string;
}
