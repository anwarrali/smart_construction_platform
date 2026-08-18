import { Card } from "../../../components/ui/Card";
import { useTranslation } from "react-i18next";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Loader } from "../../../components/ui/Loader";
import { formatDate } from "../../../utils/date";
import { formatFileSize } from "../../../utils/helpers";
import type { Document } from "../../../types/document";
import { CommunicationActions } from "../../../components/shared/CommunicationActions";

interface DocumentListProps {
  documents: Document[];
  isLoading: boolean;
  onDownload?: (doc: Document) => void;
  onDelete?: (doc: Document) => void;
}

const typeIcons: Record<string, string> = {
  drawing: "📐",
  report: "📝",
  contract: "📋",
  permit: "📄",
  specification: "📏",
  invoice: "🧾",
  other: "📎",
};

export const DocumentList = ({
  documents,
  isLoading,
  onDownload,
  onDelete,
}: DocumentListProps) => {
  const { t } = useTranslation();
  if (isLoading) return <Loader text="Loading documents..." />;

  if (documents.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">📄</div>
        <p className="empty-state-title">{t("documentList.no_documents_found")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {documents.map((doc) => (
        <Card key={doc.id} className="flex items-center justify-between p-4">
          <div className="flex items-center gap-4">
            <span className="text-2xl">
              {typeIcons[doc.documentType] || "📎"}
            </span>
            <div>
              <p className="font-medium text-sm">{doc.title}</p>
              <div className="flex items-center gap-2 mt-1">
                <Badge size="sm">{doc.documentType}</Badge>
                {doc.fileSizeBytes && (
                  <span className="text-xs text-muted-foreground">
                    {formatFileSize(doc.fileSizeBytes)}
                  </span>
                )}
                <span className="text-xs text-muted-foreground">
                  v{doc.version}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatDate(doc.createdAt)}
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Share only. The backend refuses a share whose recipient cannot
                access the document, so this never widens document access. */}
            <CommunicationActions
              entityType="DOCUMENT"
              entityId={doc.id}
              projectId={doc.projectId}
              intents={["forward"]}
            />
            {onDownload && (
              <Button variant="ghost" size="sm" onClick={() => onDownload(doc)}>
                {t("documentList.download")}
              </Button>
            )}
            {onDelete && (
              <Button variant="ghost" size="sm" onClick={() => onDelete(doc)}>
                {t("documentList.delete")}
              </Button>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
};
