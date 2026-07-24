import type { User } from "./auth";

export type TaskStatus =
  | "backlog"
  | "todo"
  | "in_progress"
  | "under_review"
  | "rework_required"
  | "blocked"
  | "done"
  | "cancelled";
export type TaskPriority = "low" | "medium" | "high" | "critical";
export type DependencyType =
  | "finish_to_start"
  | "start_to_start"
  | "finish_to_finish"
  | "start_to_finish";
export type RescheduleReason =
  | "dependency_delay"
  | "resource_delay"
  | "weather"
  | "material_delay"
  | "design_change"
  | "manual"
  | "other";

export interface Task {
  id: string;
  taskCode: string;
  projectId: string;
  milestoneId?: string;
  name: string;
  description?: string;
  discipline?: string;
  status: TaskStatus;
  priority: TaskPriority;
  assigneeIds: string[];
  assignees: User[];
  createdById: string;
  createdBy?: User;
  plannedStartDate?: string;
  plannedEndDate?: string;
  actualStartDate?: string;
  actualEndDate?: string;
  submittedForReviewAt?: string;
  reviewedAt?: string;
  reviewedById?: string;
  consultantComments?: string;
  rejectionReason?: string;
  reviewStatus?: string;
  reviewRequired: boolean;
  reviewDueDate?: string;
  durationDays?: number;
  progressPercentage: number;
  isCriticalPath: boolean;
  isMilestone: boolean;
  totalFloatDays?: number;
  dependencies: TaskDependency[];
  dependents: TaskDependency[];
  rescheduleLogs: TaskRescheduleLog[];
  createdAt: string;
  updatedAt: string;
}

export interface TaskDependency {
  id: string;
  taskId: string;
  dependsOnTaskId: string;
  dependencyType: DependencyType;
  lagDays: number;
  dependsOnTask?: Task;
  dependsOnTaskCode?: string;
  dependsOnTaskName?: string;
  dependsOnTaskStatus?: TaskStatus;
}

export interface TaskRescheduleLog {
  id: string;
  taskId: string;
  triggeredByTaskId?: string;
  triggeredByUserId?: string;
  reason: RescheduleReason;
  notes?: string;
  previousStartDate?: string;
  previousEndDate?: string;
  newStartDate?: string;
  newEndDate?: string;
  shiftDays: number;
  isAutomatic: boolean;
  createdAt: string;
}

export interface CreateTaskRequest {
  projectId: string;
  milestoneId?: string;
  name: string;
  description?: string;
  discipline?: string;
  status?: TaskStatus;
  assigneeIds?: string[];
  priority: TaskPriority;
  plannedStartDate?: string;
  plannedEndDate?: string;
  isMilestone?: boolean;
  dependencyIds?: string[];
  reviewRequired?: boolean;
  reviewDueDate?: string;
}

export interface UpdateTaskRequest {
  milestoneId?: string | null;
  name?: string;
  description?: string;
  discipline?: string;
  assigneeIds?: string[];
  status?: TaskStatus;
  priority?: TaskPriority;
  plannedStartDate?: string;
  plannedEndDate?: string;
  progressPercentage?: number;
  dependencyIds?: string[];
  reviewRequired?: boolean;
  reviewDueDate?: string | null;
}

export interface TaskFilters {
  status?: TaskStatus;
  priority?: TaskPriority;
  assigneeId?: string;
  search?: string;
  isCriticalPath?: boolean;
  projectId?: string;
  page?: number;
  limit?: number;
}

export interface TasksResponse {
  items?: Task[];
  data: Task[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export interface TaskAnalytics {
  totalTasks: number;
  doneTasks: number;
  overdueTasks: number;
  blockedTasks: number;
  reworkRequiredTasks: number;
  averageCompletionTime: number;
  tasksByStatus: Record<TaskStatus, number>;
  tasksByPriority: Record<TaskPriority, number>;
}
