import { Component, type ErrorInfo, type ReactNode } from "react";
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

export const ErrorState = ({ message, onRetry }: { message: string; onRetry?: () => void }) => <Card className="border-red-200"><div className="py-8 text-center"><AlertTriangle className="mx-auto mb-3 text-red-500"/><h3 className="font-semibold">This view could not be loaded</h3><p className="mx-auto mt-1 max-w-xl text-sm text-muted-foreground">{message}</p>{onRetry && <Button className="mt-4" variant="outline" onClick={onRetry}><RefreshCw size={15}/> Retry</Button>}</div></Card>;

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
