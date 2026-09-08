import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";

import api from "../../../services/api";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { errorMessage } from "../../../utils/errorMessage";
import { useRole } from "../../../hooks/useRole";
import { IngestionStatusBadge } from "./IngestionStatusBadge";
import {
  isInFlight,
  type IngestedFile,
  type IngestionUploadConstraints,
} from "../../../types/ingestion";

/**
 * The minimum UI that makes the ingestion foundation usable and testable.
 *
 * Deliberately **not** a Documents redesign. The Documents page keeps its own
 * list, its own types and its own upload, because a document there is a
 * library entry somebody titled and classified. This panel shows the *files*:
 * what arrived, what the pipeline made of it, and what to do when it could
 * not. That includes the members of a design package, which have no library
 * entry at all and are otherwise invisible.
 *
 * Two behaviours worth naming:
 *
 * **It polls only while something is moving.** A list where every file has
 * settled stops refreshing, so an idle Files tab costs nothing.
 *
 * **Retry is offered only where it can help.** The server says whether a
 * failure is retryable; a scanned PDF and an unparsed DWG are finished, and
 * offering a button that cannot change the outcome is worse than offering none.
 */

/** How often the list refreshes while any file is still being processed. */
const POLL_INTERVAL_MS = 4000;

const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

interface ProjectFilesPanelProps {
  projectId: string;
}

export const ProjectFilesPanel = ({ projectId }: ProjectFilesPanelProps) => {
  const { t } = useTranslation();
  const { permissionsReady, hasCapability } = useRole();
  const canUpload = !permissionsReady || hasCapability("document.upload");

  /**
   * `null` means "not fetched yet", which is the loading state.
   *
   * A separate `isLoading` boolean would need a `setIsLoading(true)` in the
   * effect below — a synchronous setState that cascades a render — and it
   * would also have to be suppressed on every four-second poll, or a settled
   * list would flicker. One nullable value says both things and needs neither.
   */
  const [files, setFiles] = useState<IngestedFile[] | null>(null);
  const [constraints, setConstraints] =
    useState<IngestionUploadConstraints | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchFiles = useCallback(async () => {
    try {
      const page = await api.ingestion.list(projectId, { limit: 100 });
      setFiles(page.items);
    } catch (error) {
      toast.error(errorMessage(error, t("ingestion.loadFailed")));
      setFiles([]);
    }
  }, [projectId, t]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      await fetchFiles();
      try {
        const limits = await api.ingestion.constraints(projectId);
        if (!cancelled) setConstraints(limits);
      } catch {
        // Constraints are a convenience — they let the file picker filter and
        // the size be checked before a long upload. The panel works without
        // them, so a failure here is not worth a toast.
        if (!cancelled) setConstraints(null);
      }
    };
    void load();
    // Guards against a project switch landing the previous project's limits on
    // the new project's panel.
    return () => {
      cancelled = true;
    };
  }, [fetchFiles, projectId]);

  const hasWorkInFlight = (files ?? []).some((file) => isInFlight(file.status));

  useEffect(() => {
    if (!hasWorkInFlight) return;
    const timer = setInterval(fetchFiles, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hasWorkInFlight, fetchFiles]);

  const handleUpload = async (file: File) => {
    if (constraints && file.size > constraints.maxFileBytes) {
      // Checked here as well as on the server, which remains the authority:
      // the point is not to trust the client, it is to avoid making somebody
      // on a site connection upload 200 MB to be told no.
      toast.error(
        t("ingestion.tooLarge", { limit: constraints.maxFileMb }),
      );
      return;
    }
    setIsUploading(true);
    try {
      await api.ingestion.upload(projectId, file);
      toast.success(t("ingestion.uploadAccepted"));
      await fetchFiles();
    } catch (error) {
      toast.error(errorMessage(error, t("ingestion.uploadFailed")));
    } finally {
      setIsUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const handleRetry = async (file: IngestedFile) => {
    try {
      await api.ingestion.retry(projectId, file.id);
      toast.success(t("ingestion.retryQueued"));
      await fetchFiles();
    } catch (error) {
      toast.error(errorMessage(error, t("ingestion.retryFailed")));
    }
  };

  return (
    <Card padding="sm" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold">{t("ingestion.title")}</h3>
          <p className="text-xs text-muted-foreground">
            {t("ingestion.subtitle")}
          </p>
        </div>
        {canUpload && (
          <>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              aria-label={t("ingestion.chooseFile")}
              accept={constraints?.acceptedExtensions.join(",")}
              onChange={(event) => {
                const chosen = event.target.files?.[0];
                if (chosen) handleUpload(chosen);
              }}
            />
            <Button
              variant="primary"
              isLoading={isUploading}
              onClick={() => inputRef.current?.click()}
            >
              {t("ingestion.upload")}
            </Button>
          </>
        )}
      </div>

      {files === null ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : files.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("ingestion.empty")}</p>
      ) : (
        <ul className="divide-y divide-border">
          {files.map((file) => (
            <li
              key={file.id}
              className="py-2 flex items-center justify-between gap-3"
              data-testid="ingested-file"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {file.originalFilename}
                </p>
                <p className="text-xs text-muted-foreground">
                  {file.fileCategory}
                  {" · "}
                  {formatSize(file.fileSizeBytes)}
                  {file.parentFileId && ` · ${t("ingestion.fromPackage")}`}
                  {file.duplicateOfId && ` · ${t("ingestion.duplicate")}`}
                </p>
                {file.error && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {file.error.description}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <IngestionStatusBadge status={file.status} error={file.error} />
                {canUpload && file.error?.retryable && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleRetry(file)}
                  >
                    {t("ingestion.retry")}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
};
