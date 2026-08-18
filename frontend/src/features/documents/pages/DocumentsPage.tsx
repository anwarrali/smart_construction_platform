import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { DocumentList } from "../components/DocumentList";
import { DocumentUploader } from "../components/DocumentUploader";
import { documentsService } from "../services/documents.service";
import { useDebounce } from "../../../hooks/useDebounce";
import type {
  Document,
  DocumentFilters,
  UploadDocumentRequest,
  DocumentType,
} from "../../../types/document";
import api from "../../../services/api";
import toast from "react-hot-toast";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import { useRole } from "../../../hooks/useRole";
import { useSearchParams } from "react-router-dom";

export const DocumentsPage = () => {
  const { t } = useTranslation();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [projects, setProjects] = useState<Array<{id:string;name:string}>>([]);
  const debouncedSearch = useDebounce(search);
  const isFirstRender = useRef(true);
  const workspace = useProjectWorkspace();
  const activeProjectId = workspace.projectId;
  const { isProjectManager, isMainContractorEngineer } = useRole();
  const canUpload = isProjectManager || isMainContractorEngineer;
  const [searchParams, setSearchParams] = useSearchParams();
  const focusedDocumentId = searchParams.get("documentId");
  const visibleDocuments = focusedDocumentId ? documents.filter((document) => document.id === focusedDocumentId) : documents;

  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    try {
      const filters: DocumentFilters = { search: debouncedSearch || undefined,
        documentType: (typeFilter as DocumentType) || undefined };
      const response = activeProjectId
        ? await documentsService.getByProject(activeProjectId, filters)
        : await documentsService.list(filters);
      setDocuments(Array.isArray(response) ? response : response.data || response.items || []);
    } catch (err:any) {
      toast.error(errorMessage(err, "Failed to load documents."));
      setDocuments([]);
    } finally { setIsLoading(false); }
  }, [activeProjectId, debouncedSearch, typeFilter]);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      fetchDocuments();
      return;
    }
    const timer = setTimeout(() => fetchDocuments(), 0);
    return () => clearTimeout(timer);
  }, [fetchDocuments]);

  useEffect(() => {
    if (activeProjectId && workspace.project) { setProjects([{ id: activeProjectId, name: workspace.project.name }]); return; }
    api.projects.list({limit:100}).then(response => setProjects((response.data||[]).map(project=>({id:project.id,name:project.name})))).catch(()=>setProjects([]));
  }, [activeProjectId, workspace.project]);

  const handleUpload = async (data: UploadDocumentRequest) => {
    await documentsService.upload(data);
    await fetchDocuments();
    toast.success("Document uploaded successfully.");
  };

  const handleDownload = async (doc: Document) => {
    const url = await documentsService.getDownloadUrl(doc.id);
    window.open(url, "_blank");
  };

  const handleDelete = async (doc: Document) => {
    await documentsService.delete(doc.id);
    fetchDocuments();
  };

  return (
    <div className="page-container space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Documents{workspace.project ? ` · ${workspace.project.name}` : ""}</h1>
          <p className="text-muted-foreground">{t("documentsPage.project_documents_and_files")}</p>
        </div>
        {canUpload && <Button onClick={() => setIsUploadOpen(true)}>+ Upload Document</Button>}
      </div>
      {focusedDocumentId && <div className="flex items-center justify-between rounded-lg border bg-card p-3 text-sm"><span>{t("documentsPage.showing_the_document_opened_from_your")}</span><Button size="sm" variant="ghost" onClick={() => setSearchParams({})}>{t("documentsPage.show_all_documents")}</Button></div>}

      <Card>
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="flex-1">
            <Input
              placeholder={t("documentsPage.search_documents")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Select
            options={[
              { value: "", label: t("documentsPage.all_types") },
              { value: "drawing", label: t("docUploader.documentType.drawing") },
              { value: "report", label: t("docUploader.documentType.report") },
              { value: "contract", label: t("docUploader.documentType.contract") },
              { value: "permit", label: t("docUploader.documentType.permit") },
              { value: "specification", label: t("docUploader.documentType.specification") },
              { value: "invoice", label: t("docUploader.documentType.invoice") },
            ]}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="w-full sm:w-48"
          />
        </div>

        <DocumentList
          documents={visibleDocuments}
          isLoading={isLoading}
          onDownload={handleDownload}
          onDelete={canUpload ? handleDelete : undefined}
        />
      </Card>

      {canUpload && <DocumentUploader
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUpload={handleUpload}
        projectId={activeProjectId || ""}
        projects={projects}
      />}
    </div>
  );
};
