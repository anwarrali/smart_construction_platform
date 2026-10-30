import { Badge } from "../../../components/ui/Badge";
import { useTranslation } from "react-i18next";
import type { IndexStatus } from "../../../types/ingestion";

/**
 * Whether a file's text is searchable, beside where its processing is.
 *
 * Shows only what the server reports. `NOT_INDEXED` renders nothing: most of
 * those files will never be indexed — a drawing, an image, a model has no text
 * — and a "not indexed" label on every one of them would read as a problem.
 * The failure carries the server's reason as its tooltip, the same way the
 * processing badge does.
 */

const VARIANTS: Record<Exclude<IndexStatus, "NOT_INDEXED">, "success" | "danger" | "info"> = {
  INDEXING: "info",
  READY: "success",
  FAILED: "danger",
};

const LABEL_KEYS: Record<Exclude<IndexStatus, "NOT_INDEXED">, string> = {
  INDEXING: "ingestion.index.indexing",
  READY: "ingestion.index.ready",
  FAILED: "ingestion.index.failed",
};

interface IndexStatusBadgeProps {
  status?: IndexStatus;
  error?: string | null;
}

export const IndexStatusBadge = ({ status, error }: IndexStatusBadgeProps) => {
  const { t } = useTranslation();
  if (!status || status === "NOT_INDEXED" || !(status in LABEL_KEYS)) return null;
  return (
    <span
      data-testid="index-status"
      data-status={status}
      title={status === "FAILED" && error ? error : undefined}
    >
      <Badge variant={VARIANTS[status]}>{t(LABEL_KEYS[status])}</Badge>
    </span>
  );
};
