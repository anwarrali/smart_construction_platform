import type { Attachment } from "./attachment";
import type {
  EvidencePhotoDirection,
  FieldSubmissionStatus,
} from "./fieldSubmission";

export interface PhotoCategory {
  id: string;
  name: string;
  code: string;
  projectId?: string;
  isSystem: boolean;
  active: boolean;
  createdById?: string;
  createdAt: string;
}

export interface EvidencePhotoArchiveItem {
  id: string;
  fieldSubmissionId: string;
  projectId: string;
  taskId: string;
  taskCode: string;
  taskTitle: string;
  discipline?: string;
  workerId: string;
  workerName: string;
  uploaderId: string;
  uploaderName: string;
  submissionStatus: FieldSubmissionStatus;
  submissionCreatedAt: string;
  reviewedAt?: string;
  reviewedById?: string;
  reviewerName?: string;
  direction?: EvidencePhotoDirection;
  categories: PhotoCategory[];
  attachment: Attachment;
}

export interface EvidencePhotoArchivePage {
  items: EvidencePhotoArchiveItem[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface EvidencePhotoFilters {
  category?: string;
  discipline?: string;
  taskId?: string;
  uploaderId?: string;
  workerId?: string;
  engineerId?: string;
  status?: FieldSubmissionStatus | "";
  dateFrom?: string;
  dateTo?: string;
  direction?: EvidencePhotoDirection | "";
  search?: string;
  page?: number;
  pageSize?: number;
}
