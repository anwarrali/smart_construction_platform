import type { PhotoCategory } from "./photoArchive";

export type FieldSubmissionStatus = "SUBMITTED" | "VERIFIED" | "REJECTED";
export type EvidencePhotoDirection =
  | "FRONT" | "BACK" | "LEFT" | "RIGHT" | "TOP" | "DETAIL" | "OTHER";

export interface FieldSubmission {
  id: string;
  projectId: string;
  taskId: string;
  workerId: string;
  description?: string;
  voiceMetadata?: string;
  status: FieldSubmissionStatus;
  reviewedAt?: string;
  reviewedById?: string;
  reviewComment?: string;
  resubmissionOfId?: string;
  worker: { id: string; fullName: string; email: string };
  reviewedBy?: { id: string; fullName: string };
  photos: Array<{
    id: string;
    direction?: EvidencePhotoDirection;
    categories: PhotoCategory[];
    attachment: {
      id: string;
      originalFilename: string;
      fileUrl: string;
      mimeType: string;
      createdAt: string;
    };
  }>;
  createdAt: string;
  updatedAt: string;
}
