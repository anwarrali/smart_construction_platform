import { useCallback, useEffect, useState } from "react";
import { formatDateTime } from "../../../../utils/dates";
import { useVocabulary } from "../../../../utils/vocabulary";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../../utils/errorMessage";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  CircleDashed,
  ClipboardList,
  Clock3,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import api from "../../../../services/api";
import { Button } from "../../../../components/ui/Button";
import { Card } from "../../../../components/ui/Card";
import { Badge } from "../../../../components/ui/Badge";
import { useProjectWorkspace } from "../../../projects/context/ProjectWorkspaceContext";

interface EngineerTaskSummary {
  id: string;
  taskCode: string;
  name: string;
  projectName: string;
  discipline?: string;
  status: string;
  priority: string;
  progressPercentage: number;
  plannedEndDate?: string;
  daysRemaining?: number;
  daysOverdue: number;
  isCriticalPath: boolean;
  reviewComment?: string;
  rejectionReason?: string;
  reviewedAt?: string;
  reviewerName?: string;
}

interface EngineerDashboardData {
  project: {
    id: string;
    name: string;
    status: string;
    specialization?: string;
    organizationSide: string;
    assignmentTitle?: string;
    isSiteEngineer: boolean;
  };
  stats: {
    totalTasks: number;
    tasksToday: number;
    inProgress: number;
    overdue: number;
    underReview: number;
    reworkRequired: number;
    completed: number;
    blocked: number;
    openIssues: number;
  };
  tasksToday: EngineerTaskSummary[];
  upcomingDeadlines: EngineerTaskSummary[];
  overdueTasks: EngineerTaskSummary[];
  pendingReview: EngineerTaskSummary[];
  reworkRequired: EngineerTaskSummary[];
  recentActivity: Array<{
    id: string;
    action: string;
    actorName: string;
    timestamp: string;
  }>;
  notifications: Array<{
    id: string;
    title: string;
    message: string;
    isRead: boolean;
    createdAt: string;
  }>;
}

const priorityVariant = (priority: string): "danger" | "warning" | "neutral" => priority === "critical" || priority === "high" ? "danger" : priority === "medium" ? "warning" : "neutral";

const TaskList = ({
  tasks,
  empty,
  onOpen,
  mode = "normal",
}: {
  tasks: EngineerTaskSummary[];
  empty: string;
  onOpen: (task: EngineerTaskSummary) => void;
  mode?: "normal" | "overdue" | "rework";
}) => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  return (
  <div className="divide-y">
    {tasks.map((task) => (
      <button key={task.id} type="button" onClick={() => onOpen(task)} className="flex w-full items-start justify-between gap-4 px-4 py-3 text-left transition hover:bg-muted/40">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs font-semibold text-primary">{task.taskCode}</span>
            <Badge size="sm" variant={priorityVariant(task.priority)}>{vocabulary.priority(task.priority)}</Badge>
            {task.isCriticalPath && <Badge size="sm" variant="danger">{t("engineerDash.critical")}</Badge>}
          </div>
          <p className="mt-1 truncate text-sm font-medium">{task.name}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {task.discipline || "General"} · {task.status.replaceAll("_", " ")}
            {mode === "overdue" && task.daysOverdue > 0 ? ` · ${task.daysOverdue} days overdue` : ""}
          </p>
          {mode === "rework" && <p className="mt-2 line-clamp-2 text-xs text-state-overdue">{task.rejectionReason || task.reviewComment || "Review feedback is available in the task."}</p>}
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-semibold">{task.progressPercentage}%</p>
          <p className="text-xs text-muted-foreground">{task.plannedEndDate || "No due date"}</p>
        </div>
      </button>
    ))}
    {!tasks.length && <p className="px-4 py-8 text-center text-sm text-muted-foreground">{empty}</p>}
  </div>
);
}

export const EngineerDashboard = () => {
  const { t } = useTranslation();
  const workspace = useProjectWorkspace();
  const navigate = useNavigate();
  const [data, setData] = useState<EngineerDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!workspace.projectId) {
      setIsLoading(false);
      setError("Select an assigned project to open the Engineer dashboard.");
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      setData(await api.dashboard.getEngineerProjectStats(workspace.projectId));
    } catch (err: any) {
      setData(null);
      setError(errorMessage(err, "Unable to load the Engineer dashboard."));
    } finally {
      setIsLoading(false);
    }
  }, [workspace.projectId]);

  useEffect(() => { load(); }, [load]);

  if (isLoading) return <div className="grid animate-pulse gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 8 }, (_, index) => <div key={index} className="h-28 rounded-xl border bg-card" />)}</div>;
  if (error || !data) return <Card className="mx-auto max-w-xl p-8 text-center"><AlertCircle className="mx-auto mb-3 text-destructive" /><p className="font-medium">{error || "Dashboard unavailable"}</p><Button className="mt-4" onClick={load}><RefreshCw size={15} /> Retry</Button></Card>;

  const openTask = (task: EngineerTaskSummary) => navigate(workspace.path(`tasks/${task.id}`));
  const cards = [
    ["My Total Tasks", data.stats.totalTasks, ClipboardList, "text-state-progress bg-wash-progress"],
    ["My Tasks Today", data.stats.tasksToday, CalendarClock, "text-state-progress bg-wash-progress"],
    ["In Progress", data.stats.inProgress, CircleDashed, "text-state-review bg-wash-review"],
    ["Overdue", data.stats.overdue, Clock3, "text-state-overdue bg-wash-overdue"],
    ["Under Review", data.stats.underReview, Clock3, "text-state-blocked bg-wash-blocked"],
    ["Rework Required", data.stats.reworkRequired, RotateCcw, "text-state-review bg-wash-review"],
    ["Completed", data.stats.completed, CheckCircle2, "text-state-verified bg-wash-verified"],
    ["Open Issues", data.stats.openIssues, AlertCircle, "text-state-overdue bg-wash-overdue"],
  ] as const;

  return <div className="page-container space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="text-sm font-semibold text-primary">Main Contractor · {data.project.specialization?.replaceAll("_", " ") || "Engineer"}</p>
        <h1 className="text-2xl font-bold">{data.project.name} · Execution Dashboard</h1>
        <p className="text-sm text-muted-foreground">{data.project.assignmentTitle || "Project Engineer"}{data.project.isSiteEngineer ? " · Site Engineer" : ""}</p>
      </div>
      <Button variant="outline" onClick={load}><RefreshCw size={15} /> Refresh</Button>
    </div>

    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map(([label, value, Icon, color]) => <Card key={label} className="p-4"><div className="flex items-center justify-between"><div><p className="text-xs font-medium text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-bold">{value}</p></div><span className={`rounded-lg p-2 ${color}`}><Icon size={18} /></span></div></Card>)}
    </div>

    <div className="grid gap-6 xl:grid-cols-2">
      <Card className="overflow-hidden p-0"><h2 className="border-b px-4 py-3 font-semibold">{t("engineerDash.my_tasks_today")}</h2><TaskList tasks={data.tasksToday} empty="No assigned tasks scheduled for today." onOpen={openTask} /></Card>
      <Card className="overflow-hidden p-0"><h2 className="border-b px-4 py-3 font-semibold">{t("engineerDash.upcoming_deadlines_7_days")}</h2><TaskList tasks={data.upcomingDeadlines} empty="No deadlines in the next seven days." onOpen={openTask} /></Card>
      <Card className="overflow-hidden p-0"><h2 className="border-b px-4 py-3 font-semibold text-state-overdue">{t("engineerDash.overdue_tasks")}</h2><TaskList tasks={data.overdueTasks} empty="No overdue assigned tasks." onOpen={openTask} mode="overdue" /></Card>
      <Card className="overflow-hidden p-0"><h2 className="border-b px-4 py-3 font-semibold text-state-review">{t("engineerDash.rework_required")}</h2><TaskList tasks={data.reworkRequired} empty="No work has been returned for correction." onOpen={openTask} mode="rework" /></Card>
      <Card className="overflow-hidden p-0"><h2 className="border-b px-4 py-3 font-semibold">{t("engineerDash.pending_review")}</h2><TaskList tasks={data.pendingReview} empty="No submitted work is waiting for review." onOpen={openTask} /></Card>
      <Card className="overflow-hidden p-0"><h2 className="border-b px-4 py-3 font-semibold">{t("engineerDash.recent_activity")}</h2><div className="divide-y">{data.recentActivity.map((item) => <div key={item.id} className="px-4 py-3"><p className="text-sm font-medium">{item.action.replaceAll("_", " ")}</p><p className="text-xs text-muted-foreground">{item.actorName} · {formatDateTime(item.timestamp)}</p></div>)}{!data.recentActivity.length && <p className="px-4 py-8 text-center text-sm text-muted-foreground">{t("engineerDash.no_recent_engineer_activity")}</p>}</div></Card>
    </div>

    <Card className="overflow-hidden p-0"><div className="flex items-center justify-between border-b px-4 py-3"><h2 className="font-semibold">{t("engineerDash.notifications")}</h2><Button size="sm" variant="ghost" onClick={() => navigate(workspace.path("notifications"))}>{t("engineerDash.view_all")}</Button></div><div className="divide-y">{data.notifications.map((item) => <div key={item.id} className={`px-4 py-3 ${item.isRead ? "" : "bg-primary/5"}`}><p className="text-sm font-medium">{item.title}</p><p className="text-xs text-muted-foreground">{item.message} · {formatDateTime(item.createdAt)}</p></div>)}{!data.notifications.length && <p className="px-4 py-8 text-center text-sm text-muted-foreground">{t("engineerDash.no_project_notifications")}</p>}</div></Card>
  </div>;
};
