export type AttachmentEntityType = "TASK" | "TASK_REVIEW" | "ISSUE" | "SITE_REPORT" | "DESIGN_CHANGE";

export interface Attachment {
  id: string;
  originalFilename: string;
  storageKey: string;
  fileUrl: string;
  mimeType: string;
  fileSizeBytes: number;
  uploadedById: string;
  projectId: string;
  entityType: AttachmentEntityType;
  entityId: string;
  createdAt: string;
}
