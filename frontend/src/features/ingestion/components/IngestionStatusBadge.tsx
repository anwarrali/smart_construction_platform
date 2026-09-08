import { Badge } from "../../../components/ui/Badge";
import { useTranslation } from "react-i18next";
import type { IngestionError, IngestionStatus } from "../../../types/ingestion";

/**
 * Where a file is, in one word a person can act on.
 *
 * The distinction this component exists to make visible is **Partially
 * processed** versus **Failed**. They look similar and mean opposite things: a
 * failed file can be retried and may then work, while a partially processed
 * one is finished — a scanned PDF has no text layer and never will, and a DWG
 * is stored deliberately unparsed. Showing both as an error would send people
 * to retry something that cannot improve; showing both as success would hide
 * that their specification is not searchable.
 *
 * The variants encode that: `warning` for partial (attention, not alarm),
 * `danger` only for a real failure.
 */

const VARIANTS: Record<
  IngestionStatus,
  "success" | "warning" | "danger" | "info" | "neutral"
> = {
  UPLOADED: "neutral",
  VALIDATING: "info",
  CLASSIFIED: "info",
  QUEUED: "info",
  PROCESSING: "info",
  READY: "success",
  PARTIAL: "warning",
  FAILED: "danger",
};

/** Translation keys, so a status is never a raw enum name on screen. */
const LABEL_KEYS: Record<IngestionStatus, string> = {
  UPLOADED: "ingestion.status.uploading",
  VALIDATING: "ingestion.status.validating",
  CLASSIFIED: "ingestion.status.classified",
  QUEUED: "ingestion.status.queued",
  PROCESSING: "ingestion.status.processing",
  READY: "ingestion.status.ready",
  PARTIAL: "ingestion.status.partial",
  FAILED: "ingestion.status.failed",
};

interface IngestionStatusBadgeProps {
  status: IngestionStatus;
  /** Shown as the tooltip when the pipeline had something to say. */
  error?: IngestionError | null;
}

export const IngestionStatusBadge = ({
  status,
  error,
}: IngestionStatusBadgeProps) => {
  const { t } = useTranslation();
  const label = t(LABEL_KEYS[status] ?? "ingestion.status.unknown");
  return (
    // Wrapped rather than passing `title` to `Badge`: the shared Badge takes
    // only presentational props, and widening it for one caller would be a
    // change to every other use of it.
    //
    // The reason travels with the badge instead of needing a separate click:
    // "why is this only partly processed" is the first question anybody asks.
    <span
      data-testid="ingestion-status"
      data-status={status}
      title={error ? `${error.title} — ${error.suggestedAction}` : undefined}
    >
      <Badge variant={VARIANTS[status] ?? "neutral"}>{label}</Badge>
    </span>
  );
};
