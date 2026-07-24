export type IssueStatus = "open" | "in_progress" | "resolved" | "closed";
export type IssueSeverity = "low" | "medium" | "high" | "critical";

export interface Issue {
  id: string;
  projectId: string;
  taskId?: string;
  title: string;
  description?: string;
  severity: IssueSeverity;
  status: IssueStatus;
  raisedById: string;
  assignedToId?: string;
  resolutionNotes?: string;
  createdAt: string;
  updatedAt: string;
  attachmentCount: number;
}
