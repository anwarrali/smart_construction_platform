import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2, LoaderCircle, RefreshCw } from "lucide-react";

import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import type { IFCDataSource } from "../../../types/ifc";

export const labelize = (value?: string) => value ? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Not available";
export const formatFileSize = (bytes = 0) => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
export const formatDuration = (milliseconds?: number) => milliseconds == null ? "Not available" : milliseconds < 1000 ? `${milliseconds} ms` : `${(milliseconds / 1000).toFixed(1)} s`;
export const displayValue = (value: unknown) => value == null || value === "" ? "Not defined in source IFC" : typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);

export const SourceBadge = ({ source }: { source?: IFCDataSource | string }) => {
  const values: Record<string, { label: string; variant: "success" | "info" | "warning" | "neutral" }> = {
    IFC_SOURCE: { label: "IFC source", variant: "success" }, CALCULATED: { label: "Calculated", variant: "info" },
    AI_INFERRED: { label: "AI inferred", variant: "warning" }, USER_ENTERED: { label: "User entered", variant: "primary" as "info" },
    MISSING: { label: "Missing", variant: "neutral" },
  };
  const item = values[source || "MISSING"] || values.MISSING;
  return <Badge variant={item.variant} size="sm">{item.label}</Badge>;
};

export const EmptyState = ({ title, description, action }: { title: string; description: string; action?: ReactNode }) => <Card className="border-dashed">
  <div className="py-10 text-center"><CheckCircle2 className="mx-auto mb-3 text-muted-foreground"/><h3 className="font-semibold">{title}</h3><p className="mx-auto mt-1 max-w-xl text-sm text-muted-foreground">{description}</p>{action && <div className="mt-4">{action}</div>}</div>
</Card>;

export const LoadingState = ({ label = "Loading model intelligence…" }: { label?: string }) => <Card><div className="flex min-h-44 items-center justify-center gap-3 text-sm text-muted-foreground"><LoaderCircle className="animate-spin"/> {label}</div></Card>;

export const ErrorState = ({ message, onRetry }: { message: string; onRetry?: () => void }) => {
  const { t } = useTranslation();
  return <Card className="border-red-200"><div className="py-8 text-center"><AlertTriangle className="mx-auto mb-3 text-red-500"/><h3 className="font-semibold">{t("iFCShared.this_view_could_not_be_loaded")}</h3><p className="mx-auto mt-1 max-w-xl text-sm text-muted-foreground">{message}</p>{onRetry && <Button className="mt-4" variant="outline" onClick={onRetry}><RefreshCw size={15}/> Retry</Button>}</div></Card>; }

/**
 * Why the server would refuse this file, decided before a byte is transmitted.
 *
 * Only checks the browser can make with certainty are made here — extension,
 * emptiness, and size against the limit the server itself reported. Anything
 * needing the file's contents, the STEP signature above all, stays server-side.
 * Returns a translation key and its values, or null when nothing is wrong.
 */
export const rejectUpload = (
  file: File,
  constraints?: { acceptedExtensions: string[]; maxFileBytes: number; maxFileMb: number },
): { key: string; values?: Record<string, string | number> } | null => {
  const extensions = constraints?.acceptedExtensions?.length ? constraints.acceptedExtensions : [".ifc"];
  if (!extensions.some((extension) => file.name.toLowerCase().endsWith(extension.toLowerCase()))) {
    return { key: "ifcWorkspace.file_must_be_ifc", values: { extensions: extensions.join(", ") } };
  }
  if (!file.size) return { key: "ifcWorkspace.file_is_empty" };
  // Without constraints the limit is unknown, and guessing one would block
  // uploads the server would have accepted. The server still enforces it.
  if (constraints && file.size > constraints.maxFileBytes) {
    return { key: "ifcWorkspace.file_exceeds_limit", values: { size: (file.size / 1024 / 1024).toFixed(1), limit: constraints.maxFileMb } };
  }
  return null;
};

/**
 * Everything the server knows about a failed model, in the order a person acts on it.
 *
 * The failure card used to print `parsingErrorMessage` alone — the middle
 * sentence of a structured error whose title and suggested action were dropped,
 * and whose support log ID, the one thing support actually asks for, was never
 * shown at all. The reason is localized from the stored error code so an Arabic
 * reader gets the explanation too; the English sentence the backend stored is
 * the fallback for rows written before a code existed.
 */
export const ProcessingFailure = ({ code, message, supportLogId, onRetry }: {
  code?: string; message?: string; supportLogId?: string; onRetry?: () => void;
}) => {
  const { t } = useTranslation();
  const known = code ? t(`ifcWorkspace.error_${code}_title`, { defaultValue: "" }) : "";
  const action = code ? t(`ifcWorkspace.error_${code}_action`, { defaultValue: "" }) : "";
  return <Card className="border-red-200">
    <div className="flex gap-3">
      <AlertTriangle className="mt-0.5 shrink-0 text-red-500"/>
      <div className="min-w-0 flex-1">
        <h3 className="font-semibold">{known || t("ifcWorkspace.ifc_model_could_not_be_parsed")}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{message || t("ifcWorkspace.parsing_or_extraction_failed")}</p>
        {action && <p className="mt-2 text-sm"><span className="font-medium">{t("ifcWorkspace.what_to_do_next")}</span> {action}</p>}
        <p className="mt-2 text-xs text-muted-foreground">{t("ifcWorkspace.original_file_is_kept")}</p>
        {supportLogId && <p className="mt-2 font-mono text-xs text-muted-foreground">{t("ifcWorkspace.support_log_id")}: {supportLogId}</p>}
        {onRetry && <Button className="mt-4" variant="outline" size="sm" onClick={onRetry}><RefreshCw size={15}/> {t("common.retry")}</Button>}
      </div>
    </div>
  </Card>;
};

interface BoundaryProps { name: string; children: ReactNode; onRetry?: () => void }
interface BoundaryState { error?: Error }
export class IFCTabErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = {};
  static getDerivedStateFromError(error: Error): BoundaryState { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error(`[IFC Intelligence:${this.props.name}] tab failure`, error, info.componentStack); }
  componentDidUpdate(previous: BoundaryProps) { if (previous.name !== this.props.name && this.state.error) this.setState({ error: undefined }); }
  private retry = () => { this.setState({ error: undefined }); this.props.onRetry?.(); };
  render() { return this.state.error ? <ErrorState message="This tab encountered an unexpected error. Other model analysis remains available." onRetry={this.retry}/> : this.props.children; }
}
