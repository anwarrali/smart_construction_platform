export interface Milestone {
  id: string;
  projectId: string;
  milestoneCode: string;
  name: string;
  description?: string;
  plannedDate: string;
  actualDate?: string;
  status: "pending" | "completed" | "delayed";
  progressPercentage: number;
  taskCount: number;
  completedTaskCount: number;
  taskIds: string[];
  createdById?: string;
  createdAt: string;
  updatedAt: string;
}

export interface MilestoneInput {
  projectId: string;
  name: string;
  description?: string;
  plannedDate: string;
  actualDate?: string;
  taskIds: string[];
}
