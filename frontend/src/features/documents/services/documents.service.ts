import api from "../../../services/api";
import type {
  Document,
  DocumentsResponse,
  DocumentFilters,
  UploadDocumentRequest,
} from "../../../types/document";

export const documentsService = {
  list: async (filters?: DocumentFilters): Promise<DocumentsResponse> => {
    const result = await api.documents.list(filters);
    const data = Array.isArray(result) ? result : result.data || [];
    return { data, items: data, total: data.length, page: 1, limit: data.length, totalPages: data.length ? 1 : 0 };
  },

  getById: async (id: string): Promise<Document> => {
    return api.documents.getById(id);
  },

  upload: async (data: UploadDocumentRequest): Promise<Document> => {
    return api.documents.upload(data);
  },

  delete: async (id: string): Promise<void> => {
    return api.documents.delete(id);
  },

  getDownloadUrl: async (id: string): Promise<string> => {
    const { url } = await api.documents.downloadUrl(id);
    return url;
  },

  getByProject: async (
    projectId: string,
    filters?: DocumentFilters,
  ): Promise<DocumentsResponse> => {
    const result = await api.documents.getByProject(projectId, filters);
    const data = Array.isArray(result) ? result : result.data || [];
    return { data, items: data, total: data.length, page: 1, limit: data.length, totalPages: data.length ? 1 : 0 };
  },
};
