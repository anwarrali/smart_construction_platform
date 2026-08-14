import { useMemo, useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ClipboardList,
  AlertTriangle,
  Clock,
  Users,
  Calendar,
  ArrowRight,
  Flame,
  FileText,
  BarChart2,
  Flag,
} from "lucide-react";
import api from "../../../../services/api";
import { ROUTES } from "../../../../utils/constants";
import { useRole } from "../../../../hooks/useRole";
import { projectModulePath } from "../../../../utils/projectRoutes";

/* ─── Types ─── */
interface DashboardStats {
  totalAssignedProjects: number;
  activeProjects: number;
  activeProjectsOnSchedule: number;
  openIssues: number;
  criticalIssues: number;
  tasksDueToday: number;
  overdueTasks: number;
  teamMembers: number;
  activeTeamMembersToday: number;
  delayedTasks: number;
  criticalTasks: number;
  scheduledTaskDays: number;
  unresolvedDesignChanges: number;
  milestoneTotal: number;
  milestoneCompleted: number;
  milestonePending: number;
  taskCompletion: { name: string; done: number; total: number }[];
  recentActivity: { id: string; projectId?: string; action: string; entityType: string; timestamp: string }[];
}

interface AssignedProject {
  id: string;
  name: string;
  status: string;
  completionPercentage: number;
  plannedEndDate?: string;
  openIssueCount: number;
}

interface Issue {
  id: string;
  title: string;
  severity: string;
  status: string;
  createdAt: string;
  project?: { name: string };
  projectId?: string;
}

interface SiteReport {
  id: string;
  projectId?: string;
  summaryText?: string;
  reportDate: string;
  createdAt: string;
  submittedBy?: { fullName: string };
  project?: { name: string };
}

/* ─── Priority colour map ───
   Severity runs on the product's semantic state ramp. Previously this page
   mixed indigo, sky, violet, cyan, emerald and rose across its KPIs and
   badges, so a colour carried no consistent meaning from one block to the
   next; now every hue means exactly one thing everywhere. */
const severityColor: Record<string, string> = {
  critical: "bg-wash-overdue text-state-overdue",
  high: "bg-wash-review text-state-review",
  medium: "bg-wash-progress text-state-progress",
  low: "bg-wash-idle text-state-idle",
};

/* ─── Dynamic date helpers ───
   Day and month names come from `Intl` in the active language rather than from
   a hardcoded English table, so the header reads as Arabic in Arabic. */
function isoWeek(now: Date): number {
  const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}

function formatAge(iso: string, locale: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const relative = new Intl.RelativeTimeFormat(locale, { numeric: "auto", style: "narrow" });
  const hours = Math.floor(diff / 3600000);
  if (hours < 24) return relative.format(-hours, "hour");
  return relative.format(-Math.floor(diff / 86400000), "day");
}

function formatReportDate(iso: string, locale: string, labels: { today: string; yesterday: string }): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  if (d.toDateString() === today.toDateString()) return labels.today;
  if (d.toDateString() === yesterday.toDateString()) return labels.yesterday;

  return d.toLocaleDateString(locale, { day: "numeric", month: "short" });
}

/* ─── Skeleton loader ─── */
const SkeletonCard = () => (
  <div className="bg-card border rounded-xl p-5 shadow-sm animate-pulse">
    <div className="flex items-center justify-between mb-3">
      <div className="h-3 bg-muted rounded w-24" />
      <div className="h-8 w-8 bg-muted rounded-lg" />
    </div>
    <div className="h-8 bg-muted rounded w-16 mb-1" />
    <div className="h-3 bg-muted rounded w-20" />
  </div>
);

/* ─── Component ─── */
export const ProjectManagerDashboard = () => {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage || i18n.language || "en";
  const navigate = useNavigate();
  const { role, isConsultantEngineer } = useRole();
  const affiliation = isConsultantEngineer ? ("external_consultant" as const) : undefined;
  // Recomputed when the language changes so the date reads in that language.
  const dayLabel = useMemo(() => {
    const now = new Date();
    return t("pmDashboard.dayLabel", {
      date: new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(now),
      week: isoWeek(now),
    });
  }, [t, locale]);

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState(false);

  const [issues, setIssues] = useState<Issue[]>([]);
  const [issuesLoading, setIssuesLoading] = useState(true);

  const [reports, setReports] = useState<SiteReport[]>([]);
  const [reportsLoading, setReportsLoading] = useState(true);

  const [projects, setProjects] = useState<AssignedProject[]>([]);

  const [highlightedProject, setHighlightedProject] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    // 1. Dashboard stats
    setStatsLoading(true);
    setStatsError(false);
    try {
      const s = await api.dashboard.getStats();
      setStats(s);
    } catch {
      setStatsError(true);
    }
    setStatsLoading(false);

    // 2. Issues (first 4 shown on dashboard)
    setIssuesLoading(true);
    try {
      const issueData: Issue[] = await api.issues.list({ status: "open" });
      setIssues(issueData);
    } catch {
      setIssues([]);
    }
    setIssuesLoading(false);

    // 3. Site reports (first 3 shown on dashboard)
    setReportsLoading(true);
    try {
      const reportData: SiteReport[] = await api.siteReports.list();
      setReports(reportData);
    } catch {
      setReports([]);
    }
    setReportsLoading(false);

    // 4. Projects (for Schedule Review navigation)
    try {
      const projectData = await api.projects.list();
      const list: AssignedProject[] = (projectData?.data ?? []).map((p: AssignedProject) => p);
      setProjects(list);
    } catch {
      setProjects([]);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  /* ─── KPI Cards config ─── */
  const kpiCards = stats
    ? [
        {
          label: t("pmDashboard.kpi.assignedProjects"),
          value: String(stats.totalAssignedProjects),
          sub: t("pmDashboard.kpi.portfolioSub"),
          icon: ClipboardList,
          color: "bg-primary/10 text-primary",
        },
        {
          label: t("pmDashboard.kpi.activeProjects"),
          value: String(stats.activeProjects),
          sub: t("pmDashboard.kpi.onSchedule", { count: stats.activeProjectsOnSchedule }),
          icon: ClipboardList,
          color: "bg-wash-progress text-state-progress",
        },
        {
          label: t("pmDashboard.kpi.openIssues"),
          value: String(stats.openIssues),
          sub: t("pmDashboard.kpi.criticalCount", { count: stats.criticalIssues }),
          icon: AlertTriangle,
          color: "bg-wash-review text-state-review",
        },
        {
          label: t("pmDashboard.kpi.tasksDueToday"),
          value: String(stats.tasksDueToday),
          sub: t("pmDashboard.kpi.overdueCount", { count: stats.overdueTasks }),
          icon: Clock,
          color: "bg-wash-review text-state-review",
        },
        {
          label: t("pmDashboard.kpi.teamMembers"),
          value: String(stats.teamMembers),
          sub: t("pmDashboard.kpi.activeToday", { count: stats.activeTeamMembersToday }),
          icon: Users,
          color: "bg-wash-idle text-state-idle",
        },
        {
          label: t("pmDashboard.kpi.delayedTasks"),
          value: String(stats.delayedTasks),
          sub: t("pmDashboard.kpi.onCriticalPath", { count: stats.criticalTasks }),
          icon: Clock,
          color: "bg-wash-overdue text-state-overdue",
        },
        {
          label: t("pmDashboard.kpi.scheduledTaskDays"),
          value: String(stats.scheduledTaskDays),
          sub: t("pmDashboard.kpi.plannedDatesSub"),
          icon: Calendar,
          color: "bg-wash-idle text-state-idle",
        },
        {
          label: t("pmDashboard.kpi.designChanges"),
          value: String(stats.unresolvedDesignChanges),
          sub: t("pmDashboard.kpi.awaitingResolution"),
          icon: AlertTriangle,
          color: "bg-wash-blocked text-state-blocked",
        },
        {
          label: t("pmDashboard.kpi.milestones"),
          value: String(stats.milestoneCompleted),
          sub: t("pmDashboard.kpi.milestonePending", { pending: stats.milestonePending, total: stats.milestoneTotal }),
          icon: Flag,
          color: "bg-wash-verified text-state-verified",
        },
      ]
    : [];

  /* ─── Navigation helpers ─── */
  const handleScheduleReview = () => {
    if (projects.length > 0) {
      navigate(projectModulePath(projects[0].id, "schedule", role, affiliation));
    } else {
      navigate(ROUTES.PROJECTS);
    }
  };

  const handleSiteReport = () => {
    navigate(ROUTES.SITE_REPORTS);
  };

  /* ─── Task completion data (first 4 projects) ─── */
  const taskCompletion = stats?.taskCompletion?.slice(0, 4) ?? [];

  /* ─── What needs a decision today ───
     Every entry below is derived from data this page already fetched and
     already shows further down — no separate endpoint, no invented counts.
     An entry only appears when its real count is greater than zero, so an
     empty band means the portfolio genuinely has nothing outstanding rather
     than that the data failed to load.

     This exists because nine equal-weight KPI tiles report the state of the
     portfolio without ever saying which of them needs the manager first. */
  const criticalIssues = issues.filter(
    (issue) => issue.severity?.toLowerCase() === "critical",
  );

  const decisions = [
    stats && stats.delayedTasks > 0 && {
      key: "delayed",
      kicker: t("pmDashboard.decisions.delayed"),
      tone: "text-state-overdue",
      title: t("pmDashboard.decisions.behindSchedule", { count: stats.delayedTasks }),
      meta: t("pmDashboard.kpi.onCriticalPath", { count: stats.criticalTasks }),
      to: ROUTES.TASKS,
    },
    criticalIssues.length > 0 && {
      key: "critical-issues",
      kicker: t("pmDashboard.decisions.criticalIssue"),
      tone: "text-state-overdue",
      title: criticalIssues[0].title,
      meta: t("pmDashboard.decisions.criticalMeta", {
        count: criticalIssues.length,
        age: formatAge(criticalIssues[criticalIssues.length - 1].createdAt, locale),
      }),
      to: ROUTES.ISSUES,
    },
    stats && stats.unresolvedDesignChanges > 0 && {
      key: "design-changes",
      kicker: t("pmDashboard.kpi.awaitingResolution"),
      tone: "text-state-blocked",
      title: t("pmDashboard.decisions.designChangesUnresolved", { count: stats.unresolvedDesignChanges }),
      meta: t("pmDashboard.decisions.blockingDownstream"),
      to: ROUTES.DESIGN_CHANGES,
    },
    stats && stats.tasksDueToday > 0 && {
      key: "due-today",
      kicker: t("pmDashboard.decisions.dueToday"),
      tone: "text-state-review",
      title: t("pmDashboard.decisions.tasksDueToday", { count: stats.tasksDueToday }),
      meta: t("pmDashboard.kpi.overdueCount", { count: stats.overdueTasks }),
      to: ROUTES.TASKS,
    },
    reports.length > 0 && {
      key: "reports",
      kicker: t("pmDashboard.decisions.pendingReview"),
      tone: "text-state-review",
      title: t("pmDashboard.decisions.reportsAwaiting", { count: reports.length }),
      meta: t("pmDashboard.decisions.oldest", { age: formatAge(reports[reports.length - 1].createdAt, locale) }),
      to: ROUTES.SITE_REPORTS,
    },
    stats && stats.milestonePending > 0 && {
      key: "milestones",
      kicker: t("pmDashboard.kpi.milestones"),
      tone: "text-state-progress",
      title: t("pmDashboard.decisions.milestonesOpen", { count: stats.milestonePending }),
      meta: t("pmDashboard.decisions.milestonesMet", { met: stats.milestoneCompleted, total: stats.milestoneTotal }),
      to: ROUTES.SCHEDULE,
    },
  ].filter(Boolean) as {
    key: string; kicker: string; tone: string; title: string; meta: string; to: string;
  }[];

  /* ─── Render ─── */
  return (
    <div className="space-y-8 animate-fade-in">
      {/* ── Header ── */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("pmDashboard.title")}</h1>
          <p className="text-muted-foreground mt-1">{dayLabel}</p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-outline btn-sm flex items-center gap-2"
            onClick={handleScheduleReview}
          >
            <Calendar size={14} /> {t("pmDashboard.scheduleReview")}
          </button>
          <button
            className="btn-primary btn-sm flex items-center gap-2"
            onClick={handleSiteReport}
          >
            <FileText size={14} /> {t("pmDashboard.siteReports")}
          </button>
        </div>
      </div>

      {/* ── What needs a decision today ──
          Placed above the metrics deliberately: the numbers describe the
          portfolio, this says what to do about it. */}
      {!statsLoading && !statsError && (
        <section className="attention-band">
          <div className="attention-head">
            <AlertTriangle size={15} className="text-state-review" />
            <h2 className="text-sm font-semibold">{t("pmDashboard.needsDecision")}</h2>
            {decisions.length > 0 && (
              <span className="text-measured text-xs text-muted-foreground">
                {t("pmDashboard.itemCount", { count: decisions.length })}
              </span>
            )}
            <button
              className="ms-auto text-xs text-primary hover:underline"
              onClick={() => navigate(ROUTES.MY_ACTIONS)}
            >
              {t("pmDashboard.openMyActions")}
            </button>
          </div>

          {decisions.length === 0 ? (
            <p className="px-5 py-6 text-center text-sm text-muted-foreground">
              {t("pmDashboard.nothingWaiting")}
            </p>
          ) : (
            <div className="attention-grid sm:grid-cols-2 xl:grid-cols-3">
              {decisions.map((item) => (
                <button key={item.key} className="decision" onClick={() => navigate(item.to)}>
                  <span className={`decision-kicker ${item.tone}`}>{item.kicker}</span>
                  <span className="decision-title">{item.title}</span>
                  <span className="decision-meta">{item.meta}</span>
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 xl:grid-cols-3 gap-4">
        {statsLoading
          ? [0, 1, 2, 3].map((i) => <SkeletonCard key={i} />)
          : statsError
          ? (
            <div className="col-span-full text-center text-sm text-muted-foreground py-8">
              {t("pmDashboard.statsFailed")}
            </div>
          )
          : kpiCards.map(({ label, value, sub, icon: Icon, color }) => (
              <div
                key={label}
                className="bg-card border rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm text-muted-foreground font-medium">{label}</span>
                  <span className={`p-2 rounded-lg ${color}`}>
                    <Icon size={16} />
                  </span>
                </div>
                <p className="text-3xl font-bold">{value}</p>
                <p className="text-xs text-muted-foreground mt-1">{sub}</p>
              </div>
            ))}
      </div>

      <section className="bg-card border rounded-xl p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div><h2 className="font-semibold">{t("pmDashboard.kpi.assignedProjects")}</h2><p className="text-xs text-muted-foreground">{t("pmDashboard.selectProject")}</p></div>
          <button className="text-xs text-primary hover:underline" onClick={() => navigate(ROUTES.PM_PROJECTS)}>{t("pmDashboard.viewProjects")}</button>
        </div>
        {projects.length === 0 ? <p className="py-6 text-center text-sm text-muted-foreground">{t("pmDashboard.noProjectsAssigned")}</p> :
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{projects.map(project =>
            <button key={project.id} onClick={() => navigate(projectModulePath(project.id, "dashboard", role, affiliation))} className="rounded-lg border p-4 text-left transition-colors hover:bg-muted/30">
              <div className="flex items-center justify-between gap-2"><span className="font-medium">{project.name}</span><span className="text-xs text-muted-foreground">{t("project.status." + project.status, { defaultValue: project.status.replaceAll("_", " ") })}</span></div>
              <div className="mt-3 flex justify-between text-xs text-muted-foreground"><span>{t("pmDashboard.percentComplete", { value: project.completionPercentage })}</span><span>{t("pmDashboard.openIssueCount", { count: project.openIssueCount || 0 })}</span></div>
              <div className="mt-1 h-1.5 rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{width:`${project.completionPercentage}%`}} /></div>
            </button>)}</div>}
      </section>

      <section className="bg-card border rounded-xl p-6 shadow-sm">
        <h2 className="font-semibold">{t("pmDashboard.recentActivity")}</h2>
        <div className="mt-3 divide-y">{(stats?.recentActivity || []).map(activity =>
          <button key={activity.id} onClick={() => activity.projectId && navigate(`/project-manager/projects/${activity.projectId}/dashboard`)} className="flex w-full items-center justify-between py-2 text-left text-sm hover:text-primary">
            <span className="capitalize">{t("activity.entity." + activity.entityType, { defaultValue: activity.entityType.replaceAll("_", " ") })} · {t("activity.action." + activity.action, { defaultValue: activity.action.replaceAll("_", " ") })}</span><span className="text-xs text-muted-foreground">{formatAge(activity.timestamp, locale)}</span>
          </button>)}{!stats?.recentActivity?.length && <p className="py-4 text-sm text-muted-foreground">{t("empty.noActivity")}</p>}</div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Urgent Issues ── */}
        <div className="lg:col-span-2 bg-card border rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2">
              <Flame size={18} className="text-state-overdue" />
              <h2 className="text-base font-semibold">{t("pmDashboard.urgentIssues")}</h2>
            </div>
            <button
              className="text-xs text-primary hover:underline flex items-center gap-1"
              onClick={() => navigate(ROUTES.ISSUES)}
            >
              {t("common.viewAll")} <ArrowRight size={12} className="rtl-flip" />
            </button>
          </div>

          {issuesLoading ? (
            <div className="space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-14 bg-muted/40 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : issues.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              {t("pmDashboard.noOpenIssues")}
            </p>
          ) : (
            <div className="space-y-3">
              {issues.slice(0, 4).map((issue) => {
                const severityKey = issue.severity?.toLowerCase() ?? "medium";
                const colorClass =
                  severityColor[severityKey] ?? "bg-wash-idle text-state-idle";
                const label =
                  severityKey.charAt(0).toUpperCase() + severityKey.slice(1);
                const projectName = issue.project?.name
                  ?? projects.find((project) => project.id === issue.projectId)?.name
                  ?? t("project.project");
                const age = formatAge(issue.createdAt, locale);
                return (
                  <div
                    key={issue.id}
                    className="flex items-center gap-4 p-3 rounded-lg border hover:bg-muted/30 transition-colors"
                  >
                    <span
                      className={`px-2 py-0.5 rounded border text-xs font-semibold shrink-0 ${colorClass}`}
                    >
                      {t("issue.severityLevel." + severityKey, { defaultValue: label })}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{issue.title}</p>
                      <p className="text-xs text-muted-foreground">{projectName}</p>
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0">{age}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Task Completion ── */}
        <div className="bg-card border rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2">
              <BarChart2 size={18} className="text-primary" />
              <h2 className="text-base font-semibold">{t("pmDashboard.taskCompletion")}</h2>
            </div>
            <button
              className="text-xs text-primary hover:underline flex items-center gap-1"
              onClick={() => navigate(ROUTES.TASKS)}
            >
              {t("common.viewAll")} <ArrowRight size={12} className="rtl-flip" />
            </button>
          </div>

          {statsLoading ? (
            <div className="space-y-5">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="space-y-2 animate-pulse">
                  <div className="h-3 bg-muted rounded w-3/4" />
                  <div className="h-1.5 bg-muted rounded" />
                  <div className="h-3 bg-muted rounded w-1/2" />
                </div>
              ))}
            </div>
          ) : taskCompletion.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">{t("pmDashboard.noProjectData")}</p>
          ) : (
            <div className="space-y-5">
              {taskCompletion.map((proj) => {
                const pct = proj.total > 0 ? Math.round((proj.done / proj.total) * 100) : 0;
                const isHigh = pct >= 75;
                return (
                  <div
                    key={proj.name}
                    className={`cursor-pointer rounded-lg p-3 -mx-3 transition-colors ${
                      highlightedProject === proj.name
                        ? "bg-muted/40"
                        : "hover:bg-muted/20"
                    }`}
                    onClick={() =>
                      setHighlightedProject(
                        proj.name === highlightedProject ? null : proj.name
                      )
                    }
                  >
                    <div className="flex justify-between text-sm mb-2">
                      <span className="font-medium truncate max-w-[65%]">{proj.name}</span>
                      <span
                        className={`font-semibold ${
                          isHigh ? "text-state-verified" : "text-state-review"
                        }`}
                      >
                        {pct}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${
                          isHigh ? "bg-state-verified" : "bg-state-review"
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {t("pmDashboard.tasksDoneOfTotal", { done: proj.done, total: proj.total })}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Recent Site Report Reviews ── */}
      <div className="bg-card border rounded-xl shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-base font-semibold">{t("pmDashboard.siteReportReviews")}</h2>
          <button
            className="text-xs text-primary hover:underline flex items-center gap-1"
            onClick={() => navigate(ROUTES.SITE_REPORTS)}
          >
            {t("common.viewAll")} <ArrowRight size={12} className="rtl-flip" />
          </button>
        </div>

        {reportsLoading ? (
          <div className="divide-y divide-border">
            {[0, 1, 2].map((i) => (
              <div key={i} className="px-6 py-3.5 flex gap-4 animate-pulse">
                <div className="h-3 bg-muted rounded flex-1" />
                <div className="h-3 bg-muted rounded w-24" />
                <div className="h-3 bg-muted rounded w-20" />
                <div className="h-5 bg-muted rounded w-24" />
              </div>
            ))}
          </div>
        ) : reports.length === 0 ? (
          <div className="px-6 py-8 text-center text-sm text-muted-foreground">
            {t("pmDashboard.noSiteReports")}
          </div>
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <thead>
              <tr className="bg-muted/30">
                <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t("pmDashboard.table.report")}
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t("pmDashboard.table.submittedBy")}
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t("common.date")}
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t("common.status")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {reports.slice(0, 3).map((r) => {
                const projectName = r.project?.name
                  ?? projects.find((project) => project.id === r.projectId)?.name
                  ?? t("project.project");
                const summary = r.summaryText
                  ? r.summaryText.slice(0, 50) + (r.summaryText.length > 50 ? "…" : "")
                  : t("pmDashboard.dailyProgressUpdate");
                const author = r.submittedBy?.fullName ?? t("pmDashboard.teamMember");
                const dateLabel = formatReportDate(r.reportDate ?? r.createdAt, locale, { today: t("common.today"), yesterday: t("common.yesterday") });
                return (
                  <tr key={r.id} className="hover:bg-muted/20 transition-colors">
                    <td className="px-6 py-3.5 font-medium">
                      <p className="truncate max-w-xs">{projectName}</p>
                      <p className="text-xs text-muted-foreground font-normal">{summary}</p>
                    </td>
                    <td className="px-6 py-3.5 text-muted-foreground">{author}</td>
                    <td className="px-6 py-3.5 text-muted-foreground">{dateLabel}</td>
                    <td className="px-6 py-3.5">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-wash-review text-state-review">
                        {t("pmDashboard.pendingReview")}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
};
