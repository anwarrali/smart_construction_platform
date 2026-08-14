import { useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { Button } from "../../../components/ui/Button";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import { formatFileSize } from "../../../utils/helpers";
import type {
  DocumentType,
  UploadDocumentRequest,
} from "../../../types/document";

interface DocumentUploaderProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (data: UploadDocumentRequest) => Promise<void>;
  projectId: string;
  taskId?: string;
  projects: Array<{ id: string; name: string }>;
}

const DOCUMENT_TYPE_OPTIONS = [
  { value: "drawing", label: "Drawing" },
  { value: "report", label: "Report" },
  { value: "contract", label: "Contract" },
  { value: "permit", label: "Permit" },
  { value: "specification", label: "Specification" },
  { value: "invoice", label: "Invoice" },
  { value: "other", label: "Other" },
];

export const DocumentUploader = ({
  isOpen,
  onClose,
  onUpload,
  projectId,
  taskId,
  projects,
}: DocumentUploaderProps) => {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [documentType, setDocumentType] = useState<string>("other");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState(projectId || "");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      if (!title) setTitle(selected.name);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!file) {
      setError("Please select a file");
      return;
    }
    if (!selectedProjectId) {
      setError("Please select a project");
      return;
    }

    setIsLoading(true);
    try {
      await onUpload({
        title: title || file.name,
        documentType: documentType as DocumentType,
        file,
        projectId: selectedProjectId,
        taskId,
        notes: notes || undefined,
      });
      setFile(null); setTitle(""); setNotes(""); setDocumentType("other");
      onClose();
    } catch (err: any) {
      const detail = errorMessage(err);
      setError(Array.isArray(detail) ? detail.map((item:any)=>item.msg).join(", ") : detail || "Document upload failed. Check the selected project and file.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t("docUploader.upload_document")} size="md">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="bg-red-50 text-red-600 text-sm rounded-md px-4 py-3">
            {error}
          </div>
        )}

        <div
          className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:bg-muted/30 transition-colors"
          onClick={() => fileInputRef.current?.click()}
        >
          {file ? (
            <div>
              <p className="font-medium">{file.name}</p>
              <p className="text-sm text-muted-foreground">
                {formatFileSize(file.size)}
              </p>
            </div>
          ) : (
            <div>
              <p className="text-2xl mb-2">📁</p>
              <p className="text-sm text-muted-foreground">
                {t("docUploader.click_to_select_a_file")}
              </p>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".jpg,.jpeg,.png,.pdf,.doc,.docx,.xls,.xlsx,.txt,.dwg"
            onChange={handleFileChange}
          />
        </div>

        <Input
          label={t("docUploader.title")}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t("docUploader.document_title")}
        />
        <Select
          label={t("docUploader.project")}
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          options={[{value:"",label:"Select project"}, ...projects.map(project=>({value:project.id,label:project.name}))]}
          required
        />
        <Select
          label={t("docUploader.document_type")}
          options={DOCUMENT_TYPE_OPTIONS}
          value={documentType}
          onChange={(e) => setDocumentType(e.target.value)}
        />
        <Input
          label={t("docUploader.notes")}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={t("docUploader.optional_notes")}
        />

        <ModalActions>
          <Button variant="outline" onClick={onClose} type="button">
            {t("docUploader.cancel")}
          </Button>
          <Button type="submit" isLoading={isLoading}>
            {t("docUploader.upload")}
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
};
