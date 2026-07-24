export type DesignChangeStatus =
  | "proposed"
  | "under_review"
  | "approved"
  | "rejected"
  | "implemented";

export interface DesignChange {
  id: string;
  projectId: string;
  taskId?: string;
  title: string;
  description?: string;
  sourceDiscipline: string;
  proposedById: string;
  approvedById?: string;
  status: DesignChangeStatus;
  affectedDisciplines: DesignChangeAffectedDiscipline[];
  createdAt: string;
  updatedAt: string;
  attachmentCount: number;
}

export interface DesignChangeAffectedDiscipline {
  id: string;
  designChangeId: string;
  discipline: string;
  acknowledgedById?: string;
  acknowledged: boolean;
}
