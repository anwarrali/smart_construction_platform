import { useCallback, useEffect, useState } from "react";
import { formatDateTime } from "../../../../utils/dates";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../../utils/errorMessage";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, GitBranch, Paperclip } from "lucide-react";
import api from "../../../../services/api";
import { Badge } from "../../../../components/ui/Badge";
import { Button } from "../../../../components/ui/Button";
import { Card } from "../../../../components/ui/Card";
import { Input } from "../../../../components/ui/Input";
import { Select } from "../../../../components/ui/Select";
import { useProjectWorkspace } from "../../../projects/context/ProjectWorkspaceContext";
import type { ConsultantReviewSummary } from "../../../../types/consultant";

const title = (value?: string) => (value || "—").replaceAll("_", " ").replace(/\b\w/g, (x) => x.toUpperCase());

export const ConsultantReviewsPage = ({ history = false }: { history?: boolean }) => {
  const { t } = useTranslation();
  const workspace = useProjectWorkspace();
  const navigate = useNavigate();
  const [items, setItems] = useState<ConsultantReviewSummary[]>([]);
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("");
  const [status, setStatus] = useState("");
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [resubmissionsOnly, setResubmissionsOnly] = useState(false);
  const [blockingOnly, setBlockingOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    if (!workspace.projectId) return;
    setLoading(true); setError("");
    try {
      const filters = { search: search || undefined, priority: priority || undefined, status: status || undefined,
        criticalOnly: criticalOnly || undefined, overdueOnly: overdueOnly || undefined,
        resubmissionsOnly: resubmissionsOnly || undefined, blockingOnly: blockingOnly || undefined };
      setItems(history ? await api.consultant.history(workspace.projectId, filters) : await api.consultant.reviews(workspace.projectId, filters));
    } catch (err: any) { setError(errorMessage(err, "Unable to load reviews.")); }
    finally { setLoading(false); }
  }, [blockingOnly, criticalOnly, history, overdueOnly, priority, resubmissionsOnly, search, status, workspace.projectId]);
  useEffect(() => { const timer = window.setTimeout(load, 250); return () => window.clearTimeout(timer); }, [load]);
  return <div className="page-container space-y-6">
    <div><h1 className="text-2xl font-bold">{history ? "Review History" : "Pending Reviews"}</h1><p className="text-muted-foreground">{workspace.project?.name || "Selected project"} · only submissions matching your specialization</p></div>
    <Card className="space-y-4"><div className="grid gap-3 md:grid-cols-[1fr_180px_190px]"><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("consultantReviewsPage.search_task_id_description_or_contractor")} />
      <Select value={priority} onChange={(event) => setPriority(event.target.value)} options={[{value:"",label:"All priorities"},{value:"low",label:"Low"},{value:"medium",label:"Medium"},{value:"high",label:"High"},{value:"critical",label:"Critical"}]}/>
      <Select value={status} onChange={(event) => setStatus(event.target.value)} options={history ? [{value:"",label:"All decisions"},{value:"approved",label:"Approved"},{value:"rejected",label:"Rejected"}] : [{value:"",label:"All active states"},{value:"pending",label:"Pending"},{value:"in_review",label:"In Review"},{value:"clarification_requested",label:"Clarification Requested"}]}/></div>
      {!history && <div className="flex flex-wrap gap-4 text-sm">{[["Critical only",criticalOnly,setCriticalOnly],["Overdue only",overdueOnly,setOverdueOnly],["Resubmissions",resubmissionsOnly,setResubmissionsOnly],["Blocking dependencies",blockingOnly,setBlockingOnly]].map(([label,value,setValue]) => <label key={String(label)} className="flex items-center gap-2"><input type="checkbox" checked={value as boolean} onChange={(event) => (setValue as (value:boolean)=>void)(event.target.checked)}/>{label as string}</label>)}</div>}
    </Card>
    {error && <Card><p className="text-destructive">{error}</p><Button className="mt-3" onClick={load}>{t("consultantReviewsPage.try_again")}</Button></Card>}
    <Card className="p-0 overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left text-sm"><thead><tr className="border-b text-muted-foreground"><th className="p-4">{t("consultantReviewsPage.task")}</th><th className="p-4">{t("consultantReviewsPage.submitted")}</th><th className="p-4">{t("consultantReviewsPage.review")}</th><th className="p-4">{t("consultantReviewsPage.impact")}</th><th className="p-4">{t("consultantReviewsPage.evidence")}</th><th className="p-4"></th></tr></thead><tbody>
      {items.map((item) => <tr key={item.id} className="border-b align-top last:border-0"><td className="p-4"><div className="flex flex-wrap gap-2"><p className="font-medium">{item.taskCode} · {item.taskTitle}</p>{item.isCritical && <Badge variant="danger">{t("consultantReviewsPage.critical")}</Badge>}</div><p className="mt-1 text-xs text-muted-foreground">{title(item.discipline)} · {title(item.priority)}</p>{item.description && <p className="mt-1 max-w-sm truncate text-xs text-muted-foreground">{item.description}</p>}</td>
        <td className="p-4"><p>{item.submittedBy?.fullName || "Contractor Engineer"}</p><p className="text-xs text-muted-foreground">{formatDateTime(item.submittedAt)}</p>{item.isResubmission && <Badge className="mt-1" variant="warning">Attempt {item.submissionNumber}</Badge>}</td>
        <td className="p-4"><Badge variant={item.reviewStatus === "approved" ? "success" : item.reviewStatus === "rejected" ? "danger" : item.reviewStatus === "clarification_requested" ? "warning" : "info"}>{title(item.reviewStatus)}</Badge>{item.reviewDueDate && <p className={`mt-2 text-xs ${item.isOverdue ? "text-state-overdue" : "text-muted-foreground"}`}>{item.isOverdue ? "Overdue · " : "Due · "}{item.reviewDueDate}</p>}</td>
        <td className="p-4">{item.blocksDependentWork ? <p className="flex items-center gap-1 text-state-review"><GitBranch size={14}/> {item.dependentTasksBlocked} blocked</p> : <span className="text-muted-foreground">{t("consultantReviewsPage.no_downstream_block")}</span>}{item.previousRejectionCount > 0 && <p className="mt-1 flex items-center gap-1 text-xs text-state-overdue"><AlertTriangle size={12}/>{item.previousRejectionCount} prior rejection(s)</p>}</td>
        <td className="p-4"><span className="flex items-center gap-1"><Paperclip size={14}/>{item.evidenceCount}</span></td>
        <td className="p-4 text-right"><Button size="sm" onClick={() => navigate(`${workspace.path("reviews")}/${item.id}`)}>{history ? "View Record" : "Open Review"}</Button></td></tr>)}
      {!loading && !items.length && <tr><td colSpan={6} className="p-10 text-center text-muted-foreground">{history ? "No review history matches these filters." : "No work is currently waiting for review."}</td></tr>}
      {loading && <tr><td colSpan={6} className="p-10 text-center text-muted-foreground">{t("consultantReviewsPage.loading_review_submissions")}</td></tr>}
    </tbody></table></div></Card>
  </div>;
};
