import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Loader } from "../../../components/ui/Loader";
import { Modal } from "../../../components/ui/Modal";
import api from "../../../services/api";
import { errorMessage } from "../../../utils/errorMessage";
import type { Document } from "../../../types/document";
import type { DocumentIndexStatus, RagQueryResponse } from "../../../types/rag";
import { openAuthedFile } from "../../../hooks/useAuthedFile";

interface DocumentAssistantProps {
  document: Document | null;
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Ask a question about one PDF, and see where the answer came from.
 *
 * The whole flow lives in this one modal — index status, indexing, the
 * question, the answer, the citations — because it is one task from the
 * user's side and splitting it across screens would only add navigation.
 *
 * Two things it deliberately does *not* do:
 *
 *   * It keeps no history. Each question is independent; there is no
 *     conversation, by design for the MVP.
 *   * It makes no authorization decision. Whether this document may be read
 *     at all is settled by the server, which applies the same rules as the
 *     download endpoint. A second opinion here would drift from it.
 *
 * Answers are shown with the server's `found` flag rather than by reading the
 * answer text, so "the documents do not contain this" is presented as a
 * distinct outcome instead of looking like a confident reply.
 */
export const DocumentAssistant = ({ document, isOpen, onClose }: DocumentAssistantProps) => {
  const { t } = useTranslation();
  const [status, setStatus] = useState<DocumentIndexStatus | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(false);
  const [isIndexing, setIsIndexing] = useState(false);
  const [question, setQuestion] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const [result, setResult] = useState<RagQueryResponse | null>(null);
  const [error, setError] = useState("");

  const documentId = document?.id;

  const loadStatus = useCallback(async () => {
    if (!documentId) return;
    setIsLoadingStatus(true);
    setError("");
    try {
      setStatus(await api.rag.getStatus(documentId));
    } catch (err) {
      // Surfaces the server's own words — including "not enabled on this
      // server" when RAG is switched off, which is far more useful than a
      // generic failure.
      setError(errorMessage(err, t("documentAssistant.status_failed")));
      setStatus(null);
    } finally {
      setIsLoadingStatus(false);
    }
  }, [documentId, t]);

  // Reset per document: leaving one document's answer on screen while another
  // is open would attribute it to the wrong file.
  useEffect(() => {
    if (!isOpen) return;
    setQuestion("");
    setResult(null);
    setError("");
    void loadStatus();
  }, [isOpen, documentId, loadStatus]);

  const handleIndex = async () => {
    if (!documentId) return;
    setIsIndexing(true);
    setError("");
    try {
      const next = await api.rag.indexDocument(documentId);
      setStatus(next);
      toast.success(
        t("documentAssistant.indexed_toast", {
          pages: next.pageCount ?? 0,
          chunks: next.chunkCount,
        }),
      );
    } catch (err) {
      setError(errorMessage(err, t("documentAssistant.index_failed")));
      // The server records the reason against the document, so re-reading the
      // status shows the same explanation the API just returned.
      void loadStatus();
    } finally {
      setIsIndexing(false);
    }
  };

  const handleAsk = async () => {
    if (!documentId || !document || question.trim().length < 3) return;
    setIsAsking(true);
    setError("");
    setResult(null);
    try {
      setResult(
        await api.rag.query({
          projectId: document.projectId,
          query: question.trim(),
          documentId,
        }),
      );
    } catch (err) {
      setError(errorMessage(err, t("documentAssistant.ask_failed")));
    } finally {
      setIsAsking(false);
    }
  };

  /** Open the cited page in the PDF viewer. */
  const openCitation = async (page: number) => {
    if (!documentId) return;
    try {
      // Browsers honour #page=N for PDFs, which is what turns a citation from
      // a claim into something the reader can check in one click. The file now
      // arrives over the authenticated route as a blob, and the fragment works
      // on a blob URL just the same.
      await openAuthedFile(`/documents/${documentId}/download`, `#page=${page}`);
    } catch (err) {
      toast.error(errorMessage(err, t("documentAssistant.open_failed")));
    }
  };

  const isReady = status?.status === "READY";
  const canAsk = isReady && question.trim().length >= 3 && !isAsking;

  const statusBadge = () => {
    if (!status) return null;
    const variants = {
      READY: "success",
      INDEXING: "info",
      FAILED: "danger",
      NOT_INDEXED: "neutral",
    } as const;
    return (
      <Badge variant={variants[status.status] ?? "neutral"} size="sm">
        {t(`documentAssistant.status.${status.status}`)}
      </Badge>
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      title={t("documentAssistant.title")}
      description={document?.title}
    >
      <div className="space-y-4">
        {/* --- indexing state --- */}
        <div className="rounded-lg border bg-muted/30 p-3">
          {isLoadingStatus ? (
            <Loader size="sm" />
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-muted-foreground">
                  {t("documentAssistant.index_state")}
                </span>
                {statusBadge()}
                {isReady && (
                  <span className="text-xs text-muted-foreground">
                    {t("documentAssistant.indexed_summary", {
                      pages: status?.pageCount ?? 0,
                      chunks: status?.chunkCount ?? 0,
                    })}
                  </span>
                )}
              </div>
              <Button size="sm" variant={isReady ? "ghost" : "primary"}
                onClick={handleIndex} disabled={isIndexing}>
                {isIndexing
                  ? t("documentAssistant.indexing")
                  : isReady
                    ? t("documentAssistant.reindex")
                    : t("documentAssistant.index_for_ai")}
              </Button>
            </div>
          )}

          {status?.status === "FAILED" && status.error && (
            <p className="mt-2 text-xs text-destructive">{status.error}</p>
          )}
          {status?.status === "NOT_INDEXED" && (
            <p className="mt-2 text-xs text-muted-foreground">
              {t("documentAssistant.index_hint")}
            </p>
          )}
        </div>

        {/* --- question --- */}
        <div className="space-y-2">
          <label htmlFor="rag-question" className="text-sm font-medium">
            {t("documentAssistant.question_label")}
          </label>
          <textarea
            id="rag-question"
            rows={3}
            className="w-full rounded-md border bg-background p-2 text-sm disabled:opacity-50"
            placeholder={t("documentAssistant.question_placeholder")}
            value={question}
            disabled={!isReady || isAsking}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends; Shift+Enter is a newline. A question is usually
              // one line, so requiring a mouse trip to the button is friction.
              if (event.key === "Enter" && !event.shiftKey && canAsk) {
                event.preventDefault();
                void handleAsk();
              }
            }}
          />
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              {isReady
                ? t("documentAssistant.answers_from_this_document")
                : t("documentAssistant.index_before_asking")}
            </p>
            <Button size="sm" onClick={handleAsk} disabled={!canAsk}>
              {isAsking ? t("documentAssistant.asking") : t("documentAssistant.ask")}
            </Button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {isAsking && <Loader size="sm" text={t("documentAssistant.searching")} />}

        {/* --- answer --- */}
        {result && !isAsking && (
          <div className="space-y-3">
            <div
              className={`rounded-lg border p-3 text-sm ${
                result.found ? "bg-card" : "bg-muted/40 text-muted-foreground"
              }`}
            >
              <p className="whitespace-pre-wrap">{result.answer}</p>
              {!result.found && (
                <p className="mt-2 text-xs">
                  {t("documentAssistant.not_found_hint")}
                </p>
              )}
            </div>

            {result.citations.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {t("documentAssistant.sources", { count: result.citations.length })}
                </p>
                {result.citations.map((citation, index) => (
                  <button
                    key={`${citation.documentId ?? citation.ingestedFileId}-${citation.page}-${index}`}
                    type="button"
                    onClick={() => openCitation(citation.page)}
                    className="block w-full rounded-lg border p-2 text-start text-xs hover:bg-muted/50"
                  >
                    <span className="font-medium">
                      [{index + 1}] {citation.title}
                    </span>
                    <Badge variant="info" size="sm" className="mx-2">
                      {t("documentAssistant.page", { page: citation.page })}
                    </Badge>
                    <span className="mt-1 block text-muted-foreground">
                      {citation.snippet}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
};
