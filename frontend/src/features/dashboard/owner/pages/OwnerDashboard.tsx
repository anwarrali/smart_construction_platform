import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Building2, CalendarDays, CheckCircle2, Clock, Flag, MessageSquareText, Wallet } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card } from "../../../../components/ui/Card";
import { Select } from "../../../../components/ui/Select";
import { Loader } from "../../../../components/ui/Loader";
import api from "../../../../services/api";
import type { OwnerDashboardData, Project } from "../../../../types/project";
import { projectEntityPath, projectModulePath } from "../../../../utils/projectRoutes";

const money = (value: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);

const healthLabels = {
  on_track: { label: "On Track", className: "bg-emerald-100 text-emerald-700" },
  at_risk: { label: "At Risk", className: "bg-amber-100 text-amber-700" },
  delayed: { label: "Delayed", className: "bg-rose-100 text-rose-700" },
};

export const OwnerDashboard = () => {
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [data, setData] = useState<OwnerDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.projects.list({ limit: 100 }).then((response) => {
      const assigned = response.data || [];
      setProjects(assigned);
      setProjectId((current) => current || assigned[0]?.id || "");
      if (!assigned.length) setIsLoading(false);
    }).catch((err) => {
      setError(err?.response?.data?.detail || "Unable to load assigned projects.");
      setIsLoading(false);
    });
  }, []);

  const loadDashboard = useCallback(async () => {
    if (!projectId) return;
    setIsLoading(true);
    setError("");
    try {
      setData(await api.projects.getOwnerDashboard(projectId));
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Unable to load the executive dashboard.");
      setData(null);
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  if (isLoading) return <Loader fullPage />;
  if (!projects.length) return <Card><div className="empty-state"><p className="empty-state-title">{t("owner.noAssignedProjects")}</p><p className="text-sm text-muted-foreground">{t("owner.noAssignedProjectsHint")}</p></div></Card>;
  if (!data) return <Card><p className="text-sm text-destructive">{error || t("errors.loadFailed")}</p></Card>;

  const summary = data.projectSummary;
  const cost = data.costSummary;
  const health = healthLabels[data.projectHealth];
  const remaining = Math.max(cost.budgetTotal - cost.budgetSpent, 0);
  const currentMilestone = data.milestones.find((item) => item.status === "pending" || item.status === "delayed");
  const upcomingMilestone = data.milestones.find((item) => item.status === "pending" && item.id !== currentMilestone?.id);

  return (
    <div className="page-container space-y-6">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <p className="text-sm font-medium text-primary">{t("owner.dashboard")}</p>
          <h1 className="text-3xl font-bold">{summary.name}</h1>
          <p className="mt-1 text-muted-foreground">{t("owner.intro")}</p>
        </div>
        <Select
          label={t("owner.selectedProject")}
          className="w-full lg:w-80"
          value={projectId}
          onChange={(event) => setProjectId(event.target.value)}
          options={projects.map((project) => ({ value: project.id, label: project.name }))}
        />
      </div>

      {error && <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}

      <Card className="border-primary/20 bg-primary/5 p-5">
        <div className="flex items-start gap-3"><CheckCircle2 className="mt-1 text-primary" /><div className="flex-1"><h2 className="font-semibold">{t("owner.sinceYourLastVisit")}</h2><p className="text-xs text-muted-foreground">{data.sinceLastVisit.basis === "YOUR_PREVIOUS_VISIT" && data.sinceLastVisit.previousVisitAt ? `Verified and approved project information recorded since you last opened this project on ${new Date(data.sinceLastVisit.previousVisitAt).toLocaleString()}.` : `First recorded visit — showing verified and approved project information from the last ${data.sinceLastVisit.periodDays} days.`}</p><div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div><p className="text-2xl font-bold">{data.sinceLastVisit.verifiedTasks}</p><p className="text-xs text-muted-foreground">{t("owner.tasksVerified")}</p></div>
          <div><p className="text-2xl font-bold">{data.sinceLastVisit.verifiedSiteReports}</p><p className="text-xs text-muted-foreground">{t("owner.verifiedSiteReports")}</p></div>
          <div><p className="text-2xl font-bold">{data.sinceLastVisit.approvedDesignChanges}</p><p className="text-xs text-muted-foreground">{t("owner.designChangesApproved")}</p></div>
          <div><p className="text-2xl font-bold">{data.sinceLastVisit.requestsAwaitingClarification}</p><p className="text-xs text-muted-foreground">{t("owner.requestsNeedClarification")}</p></div>
          <div><p className="text-sm font-bold">{data.sinceLastVisit.nextEngineerVisit ? new Date(data.sinceLastVisit.nextEngineerVisit).toLocaleString() : t("common.notScheduled")}</p><p className="text-xs text-muted-foreground">{t("owner.nextEngineerVisit")}</p></div>
        </div></div></div>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-5"><div className="flex justify-between"><div><p className="text-sm text-muted-foreground">{t("owner.projectProgress")}</p><p className="mt-2 text-3xl font-bold">{summary.completionPercentage}%</p><p className="text-xs text-muted-foreground">{summary.currentPhase}</p></div><Building2 className="text-primary" /></div><div className="mt-4 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${summary.completionPercentage}%` }} /></div></Card>
        <Card className="p-5"><div className="flex justify-between"><div><p className="text-sm text-muted-foreground">{t("owner.projectStatus")}</p><span className={`mt-3 inline-flex rounded-full px-3 py-1 text-sm font-semibold ${health.className}`}>{health.label}</span><p className="mt-2 text-xs text-muted-foreground">{summary.daysRemaining >= 0 ? t("project.daysRemaining", { count: summary.daysRemaining }) : t("project.daysOverdue", { count: Math.abs(summary.daysRemaining) })}</p></div><CheckCircle2 className="text-emerald-600" /></div></Card>
        <Card className="p-5"><div className="flex justify-between"><div><p className="text-sm text-muted-foreground">{t("owner.criticalDelayedTasks")}</p><p className="mt-2 text-3xl font-bold">{data.delayedTasks.length}</p><a href="#delays" className="text-xs font-medium text-primary">{t("owner.viewCriticalDelays")}</a></div><Clock className="text-rose-600" /></div></Card>
        <Card className="p-5"><div className="flex justify-between"><div><p className="text-sm text-muted-foreground">{t("project.openIssues")}</p><p className="mt-2 text-3xl font-bold">{data.openIssues.length}</p><p className="text-xs text-muted-foreground">{data.openIssues.filter((item) => item.severity === "critical").length} critical</p></div><AlertTriangle className="text-amber-600" /></div></Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2 p-5">
          <h2 className="font-semibold">{t("owner.attentionRequired")}</h2>
          <p className="text-sm text-muted-foreground">{t("owner.attentionHint")}</p>
          <div className="mt-4 space-y-3">
            {data.attentionRequired.map((item) => <div key={`${item.type}-${item.id}`} className="rounded-lg border p-3"><div className="flex items-start gap-3"><AlertTriangle size={17} className={item.severity === "critical" ? "text-rose-600" : "text-amber-600"} /><div><p className="text-sm font-semibold">{item.title}</p><p className="mt-1 text-sm text-muted-foreground">{item.summary}</p></div></div></div>)}
            {!data.attentionRequired.length && <div className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-700">{t("owner.noAttentionItems")}</div>}
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2"><Wallet size={18} /><h2 className="font-semibold">{t("owner.projectCost")}</h2></div>
          <div className="mt-5 space-y-4">
            <div><p className="text-xs text-muted-foreground">{t("owner.overallBudget")}</p><p className="text-2xl font-bold">{money(cost.budgetTotal)}</p></div>
            <div className="grid grid-cols-2 gap-3"><div><p className="text-xs text-muted-foreground">{t("project.spent")}</p><p className="font-semibold">{money(cost.budgetSpent)}</p></div><div><p className="text-xs text-muted-foreground">{t("project.remaining")}</p><p className="font-semibold">{money(remaining)}</p></div></div>
            <div><div className="mb-1 flex justify-between text-xs"><span>{t("owner.costProgress")}</span><span>{cost.budgetTotal ? Math.min(Math.round(cost.budgetSpent / cost.budgetTotal * 100), 100) : 0}%</span></div><div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-emerald-600" style={{ width: `${cost.budgetTotal ? Math.min(cost.budgetSpent / cost.budgetTotal * 100, 100) : 0}%` }} /></div></div>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5"><div className="flex items-center gap-2"><MessageSquareText size={18} /><h2 className="font-semibold">{t("owner.yourRequests")}</h2></div><div className="mt-4 space-y-3">{data.pendingOwnerRequests.map((item) => <Link key={item.id} to={projectEntityPath(projectId, "OWNER_REQUEST", item.id, "owner")} className="block rounded-lg border p-3 transition-colors hover:bg-muted/40"><div className="flex justify-between gap-3"><p className="text-sm font-semibold">{item.title}</p><span className="text-xs font-medium capitalize">{item.status.replaceAll("_", " ").toLowerCase()}</span></div>{item.needsOwnerInput && <p className="mt-1 text-xs font-semibold text-amber-700">{t("owner.clarificationRequired")}</p>}</Link>)}{!data.pendingOwnerRequests.length && <p className="text-sm text-muted-foreground">{t("empty.noRequestsHint")}</p>}</div><Link className="mt-3 inline-flex text-sm font-medium text-primary" to={projectModulePath(projectId, "requests", "owner")}>{t("owner.openRequests")}</Link></Card>
        <Card className="p-5"><div className="flex items-center gap-2"><CalendarDays size={18} /><h2 className="font-semibold">{t("owner.upcomingEngineerVisits")}</h2></div><div className="mt-4 space-y-3">{data.upcomingSiteVisits.map((visit) => <Link key={visit.id} to={projectEntityPath(projectId, "SITE_VISIT", visit.id, "owner")} className="block rounded-lg border p-3 transition-colors hover:bg-muted/40"><p className="text-sm font-semibold">{visit.title}</p><p className="text-xs text-muted-foreground">{new Date(visit.scheduledStart).toLocaleString()} · {visit.location || "Project site"}</p></Link>)}{!data.upcomingSiteVisits.length && <p className="text-sm text-muted-foreground">{t("owner.noVisitsScheduled")}</p>}</div><Link className="mt-3 inline-flex text-sm font-medium text-primary" to={projectModulePath(projectId, "site-visits", "owner")}>{t("owner.openSchedule")}</Link></Card>
        <Card className="p-5">
          <div className="flex items-center gap-2"><Flag size={18} /><h2 className="font-semibold">{t("owner.projectTimeline")}</h2></div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2"><div className="rounded-lg bg-muted/50 p-3"><p className="text-xs text-muted-foreground">{t("owner.currentMilestone")}</p><p className="font-semibold">{currentMilestone?.name || t("owner.noActiveMilestone")}</p></div><div className="rounded-lg bg-muted/50 p-3"><p className="text-xs text-muted-foreground">{t("owner.upcomingMilestone")}</p><p className="font-semibold">{upcomingMilestone?.name || t("owner.noUpcomingMilestone")}</p></div></div>
          <div className="mt-4 space-y-3">{data.milestones.map((milestone) => <div key={milestone.id} className="flex items-center justify-between border-b pb-3"><div><p className="text-sm font-medium">{milestone.name}</p><p className="text-xs text-muted-foreground">{milestone.plannedDate || t("common.notScheduled")}</p></div><span className="text-xs capitalize">{milestone.status}</span></div>)}{!data.milestones.length && <p className="text-sm text-muted-foreground">{t("owner.noMilestones")}</p>}</div>
        </Card>

        <Card className="p-5">
          <h2 className="font-semibold">{t("owner.projectBreakdown")}</h2>
          <p className="text-sm text-muted-foreground">High-level phases derived from the project’s existing work disciplines.</p>
          <div className="mt-4 space-y-4">{data.projectBreakdown.map((phase) => <div key={phase.name}><div className="mb-1 flex justify-between text-sm"><span>{phase.name}</span><span>{phase.completionPercentage}%</span></div><div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${phase.completionPercentage}%` }} /></div></div>)}{!data.projectBreakdown.length && <p className="text-sm text-muted-foreground">{t("owner.noPhases")}</p>}</div>
        </Card>
      </div>

      <div id="delays" className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5"><h2 className="font-semibold">{t("owner.criticalDelays")}</h2><div className="mt-4 space-y-3">{data.delayedTasks.map((task) => <div key={task.id} className="flex justify-between rounded-lg border p-3"><div><p className="text-sm font-semibold">{task.name}</p><p className="text-xs text-muted-foreground">{task.taskCode}</p></div><span className="text-sm font-semibold text-rose-600">{t("owner.daysDelayed", { count: task.daysDelayed })}</span></div>)}{!data.delayedTasks.length && <p className="text-sm text-muted-foreground">{t("owner.noDelays")}</p>}</div></Card>
        <Card className="p-5"><h2 className="font-semibold">{t("project.openIssues")}</h2><div className="mt-4 space-y-3">{data.openIssues.map((issue) => <div key={issue.id} className="rounded-lg border p-3"><div className="flex justify-between gap-3"><p className="text-sm font-semibold">{issue.title}</p><span className={`text-xs font-semibold capitalize ${issue.severity === "critical" ? "text-rose-600" : issue.severity === "high" ? "text-amber-600" : "text-muted-foreground"}`}>{issue.severity}</span></div><p className="mt-1 text-sm text-muted-foreground">{issue.summary}</p></div>)}{!data.openIssues.length && <p className="text-sm text-muted-foreground">{t("owner.noIssues")}</p>}</div></Card>
      </div>
    </div>
  );
};
