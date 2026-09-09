export type AttachmentEntityType = "TASK" | "TASK_REVIEW" | "ISSUE" | "SITE_REPORT" | "DESIGN_CHANGE";

export interface Attachment {
  id: string;
  originalFilename: string;
  /** Authenticated route that streams the bytes; see `useAuthedFile`. */
  downloadUrl: string;
  mimeType: string;
  fileSizeBytes: number;
  uploadedById: string;
  projectId: string;
  entityType: AttachmentEntityType;
  entityId: string;
  createdAt: string;
}
