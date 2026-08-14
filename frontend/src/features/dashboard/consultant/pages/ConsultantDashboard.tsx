import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../../utils/errorMessage";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Clock3, GitBranch, RotateCcw, ShieldCheck, XCircle } from "lucide-react";
import api from "../../../../services/api";
import { Badge } from "../../../../components/ui/Badge";
import { Button } from "../../../../components/ui/Button";
import { Card } from "../../../../components/ui/Card";
import { useProjectWorkspace } from "../../../projects/context/ProjectWorkspaceContext";
import type { ConsultantDashboardData, ConsultantReviewSummary } from "../../../../types/consultant";

const label = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
type Translate = ReturnType<typeof useTranslation>["t"];
const reviewRow = (item: ConsultantReviewSummary, open: () => void, t: Translate) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4 last:border-0">
  <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="font-medium">{item.taskCode} · {item.taskTitle}</p>{item.isCritical && <Badge variant="danger">{t("consultantDash.critical")}</Badge>}{item.isResubmission && <Badge variant="warning">Resubmission #{item.submissionNumber}</Badge>}</div>
    <p className="mt-1 text-xs text-muted-foreground">{label(item.discipline)} · {item.submittedBy?.fullName || "Contractor Engineer"} · {new Date(item.submittedAt).toLocaleString()}</p>
    {item.dependentTasksBlocked > 0 && <p className="mt-1 text-xs text-state-review">Blocks {item.dependentTasksBlocked} dependent task{item.dependentTasksBlocked === 1 ? "" : "s"}</p>}
  </div><Button size="sm" onClick={open}>{t("consultantDash.review")}</Button>
</div>;

export const ConsultantDashboard = () => {
  const { t } = useTranslation();
  const workspace = useProjectWorkspace();
  const navigate = useNavigate();
  const [data, setData] = useState<ConsultantDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    if (!workspace.projectId) return;
    setLoading(true); setError("");
    try { setData(await api.consultant.dashboard(workspace.projectId)); }
    catch (err: any) { setError(errorMessage(err, "Unable to load the Consultant dashboard.")); }
    finally { setLoading(false); }
  }, [workspace.projectId]);
  useEffect(() => { load(); }, [load]);
  if (workspace.isLoading || loading) return <div className="p-8 text-center text-muted-foreground">{t("consultantDash.loading_supervision_workspace")}</div>;
  if (workspace.error || error) return <Card><p className="text-destructive">{workspace.error || error}</p><Button className="mt-4" onClick={load}>{t("consultantDash.try_again")}</Button></Card>;
  if (!data || !workspace.projectId) return <Card><p className="text-muted-foreground">{t("consultantDash.select_an_assigned_project_to_open_its")}</p></Card>;
  const cards = [
    ["Pending Reviews", data.stats.pendingReviews, Clock3, "text-state-progress"],
    ["Due Today", data.stats.reviewsDueToday, ShieldCheck, "text-state-blocked"],
    ["Overdue", data.stats.overdueReviews, AlertTriangle, "text-state-overdue"],
    ["Critical Reviews", data.stats.criticalReviews, GitBranch, "text-state-review"],
    ["Approval Gates", data.stats.approvalGatedTasks, GitBranch, "text-state-review"],
    ["Approved This Week", data.stats.approvedThisWeek, CheckCircle2, "text-state-verified"],
    ["Rejected This Week", data.stats.rejectedThisWeek, XCircle, "text-state-overdue"],
    ["Awaiting Resubmission", data.stats.reworkAwaitingResubmission, RotateCcw, "text-state-review"],
  ] as const;
  return <div className="page-container space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-2xl font-bold">{t("consultantDash.consultant_engineer_dashboard")}</h1><p className="text-muted-foreground">{data.project.name} · {label(data.specialization)} supervision · read-only project progress</p></div><Button variant="outline" onClick={() => navigate(workspace.path("reviews"))}>{t("consultantDash.open_pending_reviews")}</Button></div>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{cards.map(([title, value, Icon, color]) => <Card key={title}><Icon size={19} className={color}/><p className="mt-3 text-2xl font-bold">{value || 0}</p><p className="text-sm text-muted-foreground">{title}</p></Card>)}</div>
    <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
      <Card className="p-0 overflow-hidden"><div className="flex items-center justify-between border-b p-5"><h2 className="font-semibold">{t("consultantDash.pending_reviews")}</h2><button className="text-sm text-primary" onClick={() => navigate(workspace.path("reviews"))}>{t("consultantDash.view_all")}</button></div>{data.pendingReviews.map((item) => reviewRow(item, () => navigate(`${workspace.path("reviews")}/${item.id}`), t))}{!data.pendingReviews.length && <p className="p-6 text-sm text-muted-foreground">{t("consultantDash.no_work_is_currently_waiting_for_review")}</p>}</Card>
      <Card><h2 className="font-semibold">{t("consultantDash.project_progress_summary")}</h2><p className="mt-3 text-3xl font-bold">{data.project.completionPercentage.toFixed(1)}%</p><div className="mt-3 h-2 rounded bg-muted"><div className="h-2 rounded bg-primary" style={{ width: `${Math.min(100, data.project.completionPercentage)}%` }}/></div><div className="mt-5 grid grid-cols-2 gap-3 text-sm"><p><span className="block text-muted-foreground">{t("consultantDash.total_tasks")}</span>{data.projectSummary.totalTasks}</p><p><span className="block text-muted-foreground">{t("consultantDash.delayed")}</span>{data.projectSummary.delayedTasks}</p><p><span className="block text-muted-foreground">{t("consultantDash.critical")}</span>{data.projectSummary.criticalTasks}</p><p><span className="block text-muted-foreground">{t("consultantDash.under_review")}</span>{data.projectSummary.taskCounts.under_review || 0}</p></div></Card>
    </div>
    <div className="grid gap-6 lg:grid-cols-2"><Card><h2 className="mb-3 font-semibold">{t("consultantDash.rework_awaiting_contractor_resubmission")}</h2>{data.reworkAwaitingResubmission.map((item) => <div key={item.taskId} className="border-b py-3 last:border-0"><p className="font-medium">{item.taskCode} · {item.taskTitle}</p><p className="text-sm text-muted-foreground">{item.requiredCorrections || item.rejectionReason || "Corrections requested"}</p></div>)}{!data.reworkAwaitingResubmission.length && <p className="text-sm text-muted-foreground">{t("consultantDash.no_rejected_work_is_awaiting")}</p>}</Card>
      <Card><h2 className="mb-3 font-semibold">{t("consultantDash.recent_review_activity")}</h2>{data.recentActivity.map((item) => <div key={item.id} className="border-b py-3 text-sm last:border-0"><p className="font-medium">{label(item.action)}</p><p className="text-xs text-muted-foreground">{item.actor?.fullName || "System"} · {new Date(item.timestamp).toLocaleString()}</p></div>)}{!data.recentActivity.length && <p className="text-sm text-muted-foreground">{t("consultantDash.no_recent_review_activity")}</p>}</Card></div>
  </div>;
};
