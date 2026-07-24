import { useState, useCallback } from "react";
import api from "../services/api";
import type {
  Document,
  UploadDocumentRequest,
  DocumentFilters,
} from "../types/document";

interface UseDocumentsReturn {
  documents: Document[];
  total: number;
  page: number;
  totalPages: number;
  isLoading: boolean;
  selectedDocument: Document | null;
  fetchDocuments: (filters?: DocumentFilters) => Promise<void>;
  uploadDocument: (data: UploadDocumentRequest) => Promise<Document>;
  deleteDocument: (id: string) => Promise<void>;
  getDownloadUrl: (id: string) => Promise<string>;
  setSelectedDocument: (doc: Document | null) => void;
}

export const useDocuments = (): UseDocumentsReturn => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(
    null,
  );

  const fetchDocuments = useCallback(async (filters?: DocumentFilters) => {
    setIsLoading(true);
    const response = await api.documents.list(filters);
    setDocuments(response.data);
    setTotal(response.total);
    setPage(response.page);
    setTotalPages(response.totalPages);
    setIsLoading(false);
  }, []);

  const uploadDocument = useCallback(async (data: UploadDocumentRequest) => {
    const document = await api.documents.upload(data);
    return document;
  }, []);

  const deleteDocument = useCallback(async (id: string) => {
    await api.documents.delete(id);
    setDocuments((prev) => prev.filter((d) => d.id !== id));
  }, []);

  const getDownloadUrl = useCallback(async (id: string) => {
    const { url } = await api.documents.downloadUrl(id);
    return url;
  }, []);

  return {
    documents,
    total,
    page,
    totalPages,
    isLoading,
    selectedDocument,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
    getDownloadUrl,
    setSelectedDocument,
  };
};
