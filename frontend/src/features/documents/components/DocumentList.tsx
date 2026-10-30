import { useTranslation } from "react-i18next";
import {
  ClipboardList,
  File,
  FileCheck2,
  FileSignature,
  FileSpreadsheet,
  FileText,
  Inbox,
  PencilRuler,
  Receipt,
  type LucideIcon,
} from "lucide-react";
import { Button } from "../../../components/ui/Button";
import { formatDate } from "../../../utils/date";
import { formatFileSize } from "../../../utils/helpers";
import type { Document } from "../../../types/document";
import { CommunicationActions } from "../../../components/shared/CommunicationActions";
import { DocumentPartySharing } from "./DocumentPartySharing";

interface DocumentListProps {
  documents: Document[];
  isLoading: boolean;
  onDownload?: (doc: Document) => void;
  onDelete?: (doc: Document) => void;
  /** Opens the question-answering modal. Omitted where RAG is not offered. */
  onAskAI?: (doc: Document) => void;
}

/** Only PDFs can be indexed, so the action is only offered on PDFs.
 *  Showing it on a .docx would offer something guaranteed to fail.
 *
 *  This used to sniff the extension out of the public `fileUrl`, which no
 *  longer exists — documents are reached through an authenticated route that
 *  carries no filename. `detectedFormat` is a better answer anyway: it is what
 *  the server found in the bytes, not what the name claimed. */
const isPdf = (doc: Document) =>
  doc.mimeType === "application/pdf" ||
  doc.detectedFormat === "PDF" ||
  /\.pdf$/i.test(doc.title || "");

/* One glyph per document class, from the same icon family as the rest of the
   product, so the register scans by type without emoji. */
const typeIcons: Record<string, LucideIcon> = {
  drawing: PencilRuler,
  report: FileText,
  contract: FileSignature,
  permit: FileCheck2,
  specification: ClipboardList,
  invoice: Receipt,
  boq: FileSpreadsheet,
  other: File,
};

const humanize = (value: string) => value.replaceAll("_", " ");

/**
 * The document register: one ruled row per document, with type, revision,
 * size and date in aligned columns — the way a drawing register is kept —
 * instead of a stack of cards.
 */
export const DocumentList = ({
  documents,
  isLoading,
  onDownload,
  onDelete,
  onAskAI,
}: DocumentListProps) => {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <div className="divide-rule border" role="status" aria-busy="true" aria-label={t("common.loading")}>
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="flex items-center gap-4 px-3 py-3">
            <div className="skeleton h-4 w-4" />
            <div className="skeleton h-4 flex-1" />
            <div className="skeleton h-4 w-24" />
          </div>
        ))}
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="empty-state">
        <Inbox size={22} strokeWidth={1.5} className="empty-state-icon" aria-hidden />
        <p className="empty-state-title">{t("documentList.no_documents_found")}</p>
      </div>
    );
  }

  return (
    <div className="table-container">
      <div className="table-responsive">
        <table className="schedule-table">
          <thead>
            <tr>
              <th scope="col">{t("documentList.column_document")}</th>
              <th scope="col" className="hidden md:table-cell">{t("documentList.column_type")}</th>
              <th scope="col" data-measured>{t("documentList.column_revision")}</th>
              <th scope="col" data-measured className="hidden sm:table-cell">{t("documentList.column_size")}</th>
              <th scope="col" data-measured className="hidden lg:table-cell">{t("documentList.column_date")}</th>
              <th scope="col" className="text-end"><span className="sr-only">{t("documentList.column_actions")}</span></th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => {
              const Icon = typeIcons[doc.documentType] || File;
              return (
                <tr key={doc.id}>
                  <td className="max-w-0 w-full">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <Icon size={16} strokeWidth={1.6} className="shrink-0 text-muted-foreground" aria-hidden />
                      <span className="truncate font-medium" title={doc.title}>{doc.title}</span>
                    </div>
                  </td>
                  <td className="hidden whitespace-nowrap capitalize text-muted-foreground md:table-cell">
                    {t(`document.type.${doc.documentType}`, { defaultValue: humanize(doc.documentType) })}
                  </td>
                  <td data-measured className="whitespace-nowrap">v{doc.version}</td>
                  <td data-measured className="hidden whitespace-nowrap text-muted-foreground sm:table-cell">
                    {doc.fileSizeBytes ? formatFileSize(doc.fileSizeBytes) : "—"}
                  </td>
                  <td data-measured className="hidden whitespace-nowrap text-muted-foreground lg:table-cell">
                    {formatDate(doc.createdAt)}
                  </td>
                  <td className="whitespace-nowrap">
                    <div className="flex items-center justify-end gap-1">
                      {/* Share only. The backend refuses a share whose recipient
                          cannot access the document, so this never widens access. */}
                      <CommunicationActions
                        entityType="DOCUMENT"
                        entityId={doc.id}
                        projectId={doc.projectId}
                        intents={["forward"]}
                      />
                      {/* Opening it to an outside party: `document.share_external`. */}
                      <DocumentPartySharing doc={doc} />
                      {onAskAI && isPdf(doc) && (
                        <Button variant="ghost" size="sm" onClick={() => onAskAI(doc)}>
                          {t("documentList.ask_ai")}
                        </Button>
                      )}
                      {onDownload && (
                        <Button variant="ghost" size="sm" onClick={() => onDownload(doc)}>
                          {t("documentList.download")}
                        </Button>
                      )}
                      {onDelete && (
                        <Button variant="ghost" size="sm" className="text-destructive" onClick={() => onDelete(doc)}>
                          {t("documentList.delete")}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
