import api from "../../../services/api";
import { downloadAuthedFile } from "../../../hooks/useAuthedFile";
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

  /**
   * Save a document to disk through the authenticated route.
   *
   * This used to ask the server for a URL and hand it to `window.open`. The
   * server answered with a public `/uploads/...` location, so the permission
   * check it had just performed protected only the *address* — anyone with the
   * URL could fetch the bytes. There is no URL to open any more: the file is
   * streamed over the credentialed client and saved from a blob.
   */
  download: async (doc: { id: string; title: string }): Promise<void> => {
    await downloadAuthedFile(`/documents/${doc.id}/download`, doc.title);
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
