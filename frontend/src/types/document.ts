export type DocumentType =
  | "drawing"
  | "report"
  | "contract"
  | "permit"
  | "specification"
  | "invoice"
  | "other";
export type MediaType = "image" | "video" | "audio" | "document";

export interface Document {
  id: string;
  projectId: string;
  taskId?: string;
  uploadedById: string;
  title: string;
  documentType: DocumentType;
  fileUrl: string;
  fileSizeBytes?: number;
  mimeType?: string;
  version: number;
  notes?: string;
  createdAt: string;
  updatedAt: string;
  uploadedBy?: {
    id: string;
    fullName: string;
  };
}

export interface MediaAsset {
  id: string;
  projectId: string;
  taskId?: string;
  siteReportId?: string;
  uploadedById: string;
  mediaType: MediaType;
  fileUrl: string;
  thumbnailUrl?: string;
  caption?: string;
  projectStage?: string;
  fileSizeBytes?: number;
  createdAt: string;
  updatedAt: string;
}

export interface UploadDocumentRequest {
  title: string;
  documentType: DocumentType;
  file: File;
  projectId: string;
  taskId?: string;
  notes?: string;
}

export interface DocumentFilters {
  documentType?: DocumentType;
  projectId?: string;
  taskId?: string;
  search?: string;
  page?: number;
  limit?: number;
}

export interface DocumentsResponse {
  items?: Document[];
  data: Document[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}
