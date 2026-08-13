import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
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
  activeProjectsSub: string;
  openIssues: number;
  openIssuesSub: string;
  tasksDueToday: number;
  tasksDueTodaySub: string;
  teamMembers: number;
  teamMembersSub: string;
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

/* ─── Priority colour map ─── */
const severityColor: Record<string, string> = {
  critical: "bg-rose-100 text-rose-700 border-rose-200",
  high: "bg-amber-100 text-amber-700 border-amber-200",
  medium: "bg-sky-100 text-sky-700 border-sky-200",
  low: "bg-slate-100 text-slate-600 border-slate-200",
};

/* ─── Dynamic date helpers ─── */
function getDayLabel(): string {
  const now = new Date();
  const dayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const monthNames = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December",
  ];
  const day = dayNames[now.getDay()];
  const date = now.getDate();
  const month = monthNames[now.getMonth()];
  const year = now.getFullYear();

  // ISO week number
  const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);

  return `${day}, ${date} ${month} ${year} — Week ${week} of 52`;
}

function formatAge(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(diff / 86400000);
  return `${days}d`;
}

function formatReportDate(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  if (d.toDateString() === today.toDateString()) return `Today`;
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";

  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
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
  const navigate = useNavigate();
  const { role, isConsultantEngineer } = useRole();
  const affiliation = isConsultantEngineer ? ("external_consultant" as const) : undefined;
  const [dayLabel] = useState(getDayLabel);

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
          label: "Assigned Projects",
          value: String(stats.totalAssignedProjects),
          sub: "Your complete portfolio",
          icon: ClipboardList,
          color: "bg-indigo-50 text-indigo-600",
        },
        {
          label: "Active Projects",
          value: String(stats.activeProjects),
          sub: stats.activeProjectsSub,
          icon: ClipboardList,
          color: "bg-blue-50 text-blue-600",
        },
        {
          label: "Open Issues",
          value: String(stats.openIssues),
          sub: stats.openIssuesSub,
          icon: AlertTriangle,
          color: "bg-amber-50 text-amber-600",
        },
        {
          label: "Tasks Due Today",
          value: String(stats.tasksDueToday),
          sub: stats.tasksDueTodaySub,
          icon: Clock,
          color: "bg-rose-50 text-rose-600",
        },
        {
          label: "Team Members",
          value: String(stats.teamMembers),
          sub: stats.teamMembersSub,
          icon: Users,
          color: "bg-emerald-50 text-emerald-600",
        },
        {
          label: "Delayed Tasks",
          value: String(stats.delayedTasks),
          sub: `${stats.criticalTasks} on critical path`,
          icon: Clock,
          color: "bg-rose-50 text-rose-600",
        },
        {
          label: "Scheduled Task-Days",
          value: String(stats.scheduledTaskDays),
          sub: "Inclusive planned dates",
          icon: Calendar,
          color: "bg-cyan-50 text-cyan-600",
        },
        {
          label: "Design Changes",
          value: String(stats.unresolvedDesignChanges),
          sub: "Awaiting resolution",
          icon: AlertTriangle,
          color: "bg-violet-50 text-violet-600",
        },
        {
          label: "Milestones",
          value: String(stats.milestoneCompleted),
          sub: `${stats.milestonePending} pending of ${stats.milestoneTotal}`,
          icon: Flag,
          color: "bg-indigo-50 text-indigo-600",
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

  /* ─── Render ─── */
  return (
    <div className="space-y-8 animate-fade-in">
      {/* ── Header ── */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Project Management Center</h1>
          <p className="text-muted-foreground mt-1">{dayLabel}</p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-outline btn-sm flex items-center gap-2"
            onClick={handleScheduleReview}
          >
            <Calendar size={14} /> Schedule Review
          </button>
          <button
            className="btn-primary btn-sm flex items-center gap-2"
            onClick={handleSiteReport}
          >
            <FileText size={14} /> Site Reports
          </button>
        </div>
      </div>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 xl:grid-cols-3 gap-4">
        {statsLoading
          ? [0, 1, 2, 3].map((i) => <SkeletonCard key={i} />)
          : statsError
          ? (
            <div className="col-span-full text-center text-sm text-muted-foreground py-8">
              Failed to load statistics. Please refresh.
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
          <div><h2 className="font-semibold">Assigned Projects</h2><p className="text-xs text-muted-foreground">Select a project to open its scoped dashboard</p></div>
          <button className="text-xs text-primary hover:underline" onClick={() => navigate(ROUTES.PM_PROJECTS)}>View projects</button>
        </div>
        {projects.length === 0 ? <p className="py-6 text-center text-sm text-muted-foreground">No projects are assigned to your account.</p> :
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{projects.map(project =>
            <button key={project.id} onClick={() => navigate(projectModulePath(project.id, "dashboard", role, affiliation))} className="rounded-lg border p-4 text-left transition-colors hover:bg-muted/30">
              <div className="flex items-center justify-between gap-2"><span className="font-medium">{project.name}</span><span className="text-xs capitalize text-muted-foreground">{project.status.replace('_',' ')}</span></div>
              <div className="mt-3 flex justify-between text-xs text-muted-foreground"><span>{project.completionPercentage}% complete</span><span>{project.openIssueCount || 0} open issues</span></div>
              <div className="mt-1 h-1.5 rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{width:`${project.completionPercentage}%`}} /></div>
            </button>)}</div>}
      </section>

      <section className="bg-card border rounded-xl p-6 shadow-sm">
        <h2 className="font-semibold">Recent Project Activity</h2>
        <div className="mt-3 divide-y">{(stats?.recentActivity || []).map(activity =>
          <button key={activity.id} onClick={() => activity.projectId && navigate(`/project-manager/projects/${activity.projectId}/dashboard`)} className="flex w-full items-center justify-between py-2 text-left text-sm hover:text-primary">
            <span className="capitalize">{activity.entityType.replace('_',' ')} · {activity.action.replace('_',' ')}</span><span className="text-xs text-muted-foreground">{formatAge(activity.timestamp)} ago</span>
          </button>)}{!stats?.recentActivity?.length && <p className="py-4 text-sm text-muted-foreground">No recent activity.</p>}</div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Urgent Issues ── */}
        <div className="lg:col-span-2 bg-card border rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2">
              <Flame size={18} className="text-rose-500" />
              <h2 className="text-base font-semibold">Urgent Issues Backlog</h2>
            </div>
            <button
              className="text-xs text-primary hover:underline flex items-center gap-1"
              onClick={() => navigate(ROUTES.ISSUES)}
            >
              View all <ArrowRight size={12} />
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
              No open issues. All clear! ✅
            </p>
          ) : (
            <div className="space-y-3">
              {issues.slice(0, 4).map((issue) => {
                const severityKey = issue.severity?.toLowerCase() ?? "medium";
                const colorClass =
                  severityColor[severityKey] ?? "bg-slate-100 text-slate-600 border-slate-200";
                const label =
                  severityKey.charAt(0).toUpperCase() + severityKey.slice(1);
                const projectName = issue.project?.name
                  ?? projects.find((project) => project.id === issue.projectId)?.name
                  ?? "Project";
                const age = formatAge(issue.createdAt);
                return (
                  <div
                    key={issue.id}
                    className="flex items-center gap-4 p-3 rounded-lg border hover:bg-muted/30 transition-colors"
                  >
                    <span
                      className={`px-2 py-0.5 rounded border text-xs font-semibold shrink-0 ${colorClass}`}
                    >
                      {label}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{issue.title}</p>
                      <p className="text-xs text-muted-foreground">{projectName}</p>
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0">{age} ago</span>
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
              <h2 className="text-base font-semibold">Task Completion</h2>
            </div>
            <button
              className="text-xs text-primary hover:underline flex items-center gap-1"
              onClick={() => navigate(ROUTES.TASKS)}
            >
              View all <ArrowRight size={12} />
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
            <p className="text-sm text-muted-foreground text-center py-6">No project data yet.</p>
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
                          isHigh ? "text-emerald-600" : "text-amber-600"
                        }`}
                      >
                        {pct}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${
                          isHigh ? "bg-emerald-500" : "bg-amber-500"
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {proj.done} / {proj.total} tasks
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
          <h2 className="text-base font-semibold">Site Report Reviews</h2>
          <button
            className="text-xs text-primary hover:underline flex items-center gap-1"
            onClick={() => navigate(ROUTES.SITE_REPORTS)}
          >
            View all <ArrowRight size={12} />
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
            No site reports submitted yet.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/30">
                <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Report
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Submitted By
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Date
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {reports.slice(0, 3).map((r) => {
                const projectName = r.project?.name
                  ?? projects.find((project) => project.id === r.projectId)?.name
                  ?? "Project";
                const summary = r.summaryText
                  ? r.summaryText.slice(0, 50) + (r.summaryText.length > 50 ? "…" : "")
                  : "Daily progress update";
                const author = r.submittedBy?.fullName ?? "Team Member";
                const dateLabel = formatReportDate(r.reportDate ?? r.createdAt);
                return (
                  <tr key={r.id} className="hover:bg-muted/20 transition-colors">
                    <td className="px-6 py-3.5 font-medium">
                      <p className="truncate max-w-xs">{projectName}</p>
                      <p className="text-xs text-muted-foreground font-normal">{summary}</p>
                    </td>
                    <td className="px-6 py-3.5 text-muted-foreground">{author}</td>
                    <td className="px-6 py-3.5 text-muted-foreground">{dateLabel}</td>
                    <td className="px-6 py-3.5">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                        Pending Review
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
