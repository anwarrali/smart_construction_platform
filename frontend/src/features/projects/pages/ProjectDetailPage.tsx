import { useState, useEffect } from "react";
import { useVocabulary } from "../../../utils/vocabulary";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { Link, useParams, useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { PageHeader } from "../../../components/ui/PageHeader";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { Loader } from "../../../components/ui/Loader";
import { projectsService } from "../services/projects.service";
import { formatDate, getDaysRemaining } from "../../../utils/date";
import { formatCurrency } from "../../../utils/helpers";
import { ROUTES } from "../../../utils/constants";
import type { Project } from "../../../types/project";
import type { User } from "../../../types/auth";
import api from "../../../services/api";
import { Select } from "../../../components/ui/Select";
import { useRole } from "../../../hooks/useRole";
import { useProjectWorkspace } from "../context/ProjectWorkspaceContext";

export const ProjectDetailPage = () => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const { id, projectId: routeProjectId } = useParams<{ id?: string; projectId?: string }>();
  const workspace = useProjectWorkspace();
  const activeProjectId = routeProjectId || id || workspace.projectId;
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [availableEngineers, setAvailableEngineers] = useState<User[]>([]);
  const [engineerId, setEngineerId] = useState("");
  const [error, setError] = useState("");
  const [recentChanges, setRecentChanges] = useState<Array<{id:string;title:string;status:string;createdAt:string}>>([]);
  const [recentReports, setRecentReports] = useState<Array<{id:string;summaryText?:string;reportDate:string;reviewStatus?:string}>>([]);
  const [projectStats, setProjectStats] = useState<null | { taskTotal: number; taskDone: number; taskInProgress: number; taskBlocked: number; tasksDueToday: number; taskProgressPercentage: number; delayedTasks: number; criticalPathTasks: number; openIssues: number; urgentIssues: number; unresolvedDesignChanges: number; siteReports: number; teamMembers: number; milestoneTotal: number; milestoneCompleted: number; milestonePending: number; recentActivity: Array<{action:string;entityType:string;timestamp:string}> }>(null);
  const { hasCapability } = useRole();
  const canStaff = hasCapability("project.manage_members");

  const loadProject = async (projectId: string) => {
    setIsLoading(true);
    setError("");
    try {
      const [data, stats, changes, reports] = await Promise.all([
        projectsService.getById(projectId), api.dashboard.getProjectStats(projectId),
        api.designChanges.list({projectId}), api.siteReports.list({projectId}),
      ]);
      setProject(data); setProjectStats(stats);
      setRecentChanges((changes || []).slice(0, 5)); setRecentReports((reports || []).slice(0, 5));
      if (canStaff) {
        const available = await api.projects.getAvailableTeamMembers(projectId);
        setAvailableEngineers(available); setEngineerId(available[0]?.id || "");
      }
    } catch (err: any) {
      setError(errorMessage(err, "Unable to load this project dashboard."));
      setProject(null);
    } finally { setIsLoading(false); }
  };

  useEffect(() => {
    if (!activeProjectId) return;
    const fetchProject = async () => {
      await loadProject(activeProjectId);
    };
    fetchProject();
  }, [activeProjectId, canStaff]);

  if (isLoading) return <Loader fullPage />;

  if (error) return <div className="page-container"><Card><p className="text-sm text-state-overdue">{error}</p><Button className="mt-4" variant="outline" onClick={()=>navigate(ROUTES.PROJECTS)}>{t("projectDetail.back_to_projects")}</Button></Card></div>;

  if (!project) {
    return (
      <div className="page-container">
        <Card>
          <div className="empty-state">
            <p className="empty-state-title">{t("projectDetail.project_not_found")}</p>
          </div>
        </Card>
      </div>
    );
  }

  const daysRemaining = getDaysRemaining(project.plannedEndDate || "");
  const statusTone = project.status === "active" ? "success" : project.status === "on_hold" ? "warning" : "neutral";

  /* Things that need a decision, in order of consequence. Only the ones that
     are actually non-zero are shown, each linked to where it is resolved —
     and only when the person may open that page. */
  const attention = projectStats ? ([
    { key: "delayed", value: projectStats.delayedTasks, tone: "text-state-overdue", module: "tasks", permission: "task.view" },
    { key: "urgentIssues", value: projectStats.urgentIssues, tone: "text-state-overdue", module: "issues", permission: "issue.view" },
    { key: "blocked", value: projectStats.taskBlocked, tone: "text-state-blocked", module: "tasks", permission: "task.view" },
    { key: "designChanges", value: projectStats.unresolvedDesignChanges, tone: "text-state-review", module: "design-changes", permission: "design_change.view" },
    { key: "dueToday", value: projectStats.tasksDueToday, tone: "text-state-review", module: "tasks", permission: "task.view" },
  ] as const).filter((item) => item.value > 0) : [];

  const metrics = projectStats ? ([
    { key: "tasks", value: `${projectStats.taskDone}/${projectStats.taskTotal}`, module: "tasks", permission: "task.view" },
    { key: "inProgress", value: projectStats.taskInProgress, module: "tasks", permission: "task.view" },
    { key: "criticalPath", value: projectStats.criticalPathTasks, module: "schedule", permission: "schedule.view" },
    { key: "openIssues", value: projectStats.openIssues, module: "issues", permission: "issue.view" },
    { key: "milestones", value: `${projectStats.milestoneCompleted}/${projectStats.milestoneTotal}`, module: "milestones", permission: "schedule.view" },
    { key: "siteReports", value: projectStats.siteReports, module: "site-reports", permission: "site_report.view" },
  ] as const) : [];

  return (
    <div className="page-container space-y-5">
      <PageHeader
        context={t("nav.projectOverview")}
        title={project.name}
        meta={[
          { label: t("projectDetail.meta.status"), value: <Badge variant={statusTone}>{vocabulary.projectStatus(project.status)}</Badge> },
          ...(project.location ? [{ label: t("projectDetail.meta.location"), value: project.location }] : []),
          ...(project.projectType ? [{ label: t("projectDetail.meta.type"), value: project.projectType }] : []),
          { label: t("projectDetail.meta.start"), value: formatDate(project.startDate || "") },
          { label: t("projectDetail.meta.plannedEnd"), value: formatDate(project.plannedEndDate || "") },
          ...(project.status === "active" && project.plannedEndDate ? [{
            label: t("projectDetail.meta.remaining"),
            value: <span className={daysRemaining < 0 ? "text-state-overdue" : daysRemaining <= 7 ? "text-state-review" : ""}>
              {daysRemaining >= 0 ? t("projectDetail.days_remaining", { count: daysRemaining }) : t("projectDetail.days_overdue", { count: -daysRemaining })}
            </span>,
          }] : []),
        ]}
      />

      {attention.length > 0 && (
        <section className="attention-band" aria-labelledby="attention-title">
          <div className="attention-head">
            <AlertTriangle size={15} className="text-state-review" aria-hidden />
            <h2 id="attention-title" className="text-[13px] font-semibold">{t("projectDetail.needs_attention")}</h2>
          </div>
          <div className="attention-grid sm:grid-cols-2 lg:grid-cols-5">
            {attention.map((item) => {
              const body = <>
                <span className={`decision-kicker ${item.tone}`}>{t(`projectDetail.stat.${item.key}`)}</span>
                <span className="metric-value">{item.value}</span>
              </>;
              return hasCapability(item.permission)
                ? <Link key={item.key} to={workspace.path(item.module)} className="decision">{body}</Link>
                : <div key={item.key} className="decision">{body}</div>;
            })}
          </div>
        </section>
      )}

      {projectStats && (
        <div className="grid gap-px border bg-border lg:grid-cols-[minmax(16rem,22rem)_1fr]">
          <div className="bg-card px-4 py-3">
            <p className="metric-label">{t("projectDetail.progress")}</p>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="metric-value">{project.completionPercentage}%</span>
              <span className="text-xs text-muted-foreground">{t("projectDetail.complete")}</span>
            </div>
            <div className="gauge gauge-ticked mt-3"><div className="gauge-fill" style={{ width: `${project.completionPercentage}%` }} /></div>
            <p className="mt-2 text-xs text-muted-foreground">
              {t("projectDetail.stat.taskProgress")}: <span className="text-measured text-foreground">{projectStats.taskProgressPercentage}%</span>
            </p>
          </div>
          <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-3 xl:grid-cols-6">
            {metrics.map((item) => {
              const body = <>
                <span className="metric-label">{t(`projectDetail.stat.${item.key}`)}</span>
                <span className="metric-value">{item.value}</span>
              </>;
              return hasCapability(item.permission)
                ? <Link key={item.key} to={workspace.path(item.module)} className="metric bg-card px-4 py-3 transition-colors hover:bg-well">{body}</Link>
                : <div key={item.key} className="metric bg-card px-4 py-3">{body}</div>;
            })}
          </div>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <section className="panel lg:col-span-2">
          <div className="panel-head"><h2 className="panel-title">{t("projectDetail.project_details")}</h2></div>
          <div className="panel-body space-y-4">
            {project.description && <p className="text-sm leading-relaxed text-foreground/85">{project.description}</p>}
            <dl className="kv">
              <dt>{t("projectDetail.meta.start")}</dt><dd className="text-measured">{formatDate(project.startDate || "")}</dd>
              <dt>{t("projectDetail.meta.plannedEnd")}</dt><dd className="text-measured">{formatDate(project.plannedEndDate || "")}</dd>
              {project.location && <><dt>{t("projectDetail.meta.location")}</dt><dd>{project.location}</dd></>}
              {project.projectType && <><dt>{t("projectDetail.meta.type")}</dt><dd>{project.projectType}</dd></>}
              <dt>{t("projectDetail.planned")}</dt><dd className="text-measured">{formatCurrency(project.budgetTotal || 0)}</dd>
              <dt>{t("projectDetail.spent")}</dt><dd className="text-measured">{formatCurrency(project.budgetSpent || 0)}</dd>
            </dl>
          </div>
        </section>

        {/* The team list is for whoever staffs the project, as on the members
            endpoint; the server leaves `members` empty for everyone else, and
            an empty card would wrongly read "no team members assigned". */}
        {canStaff && <section className="panel">
          <div className="panel-head">
            <h2 className="panel-title">{t("projectDetail.stat.team")}</h2>
            <span className="text-measured text-xs text-muted-foreground">{project.members?.length || 0}</span>
          </div>
          {canStaff && availableEngineers.length > 0 && <div className="flex items-start gap-2 border-b p-3 [&_.form-group]:mb-0"><div className="min-w-0 flex-1"><Select aria-label={t("common.add")} value={engineerId} onChange={e=>setEngineerId(e.target.value)} options={availableEngineers.map(engineer=>({value:engineer.id,label:`${engineer.fullName} · ${vocabulary.orgRole(engineer.orgRole)} · ${engineer.engineerProfile?.discipline ? vocabulary.discipline(engineer.engineerProfile.discipline) : t("projectTeam.no_discipline")}`}))}/></div><Button disabled={!engineerId} onClick={async()=>{const user=availableEngineers.find(item=>item.id===engineerId);if(!user)return;await api.projects.addMember(project.id,user.id);await loadProject(project.id);}}>{t("common.add")}</Button></div>}
          <ul className="data-list">
            {project.members?.map((member) => (
              <li key={member.id} className="flex items-center justify-between gap-3 px-4 py-2">
                <span className="min-w-0 truncate text-sm">{member.user?.fullName}</span>
                <div className="flex shrink-0 items-center gap-2"><span className="text-xs text-muted-foreground">{member.projectRoleName || vocabulary.orgRole(member.user?.orgRole)}</span>{canStaff && member.userId !== project.ownerId && member.userId !== project.projectManagerId && <Button size="sm" variant="ghost" onClick={async()=>{await api.projects.removeMember(project.id,member.userId);await loadProject(project.id);}}>{t("projectDetail.remove")}</Button>}</div>
              </li>
            ))}
          </ul>
          {(!project.members || project.members.length === 0) && (
            <p className="px-4 py-3 text-sm text-muted-foreground">{t("projectDetail.no_team_members_assigned")}</p>
          )}
        </section>}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <section className="panel">
          <div className="panel-head"><h2 className="panel-title">{t("projectDetail.recent_design_changes")}</h2></div>
          <ul className="data-list">{recentChanges.map(change=><li key={change.id} className="px-4 py-2.5"><p className="truncate text-sm font-medium">{change.title}</p><p className="text-xs text-muted-foreground">{vocabulary.designChangeStatus(change.status)}</p></li>)}</ul>
          {recentChanges.length===0&&<p className="px-4 py-3 text-sm text-muted-foreground">{t("projectDetail.no_design_changes")}</p>}
        </section>
        <section className="panel">
          <div className="panel-head"><h2 className="panel-title">{t("projectDetail.recent_site_reports")}</h2></div>
          <ul className="data-list">{recentReports.map(report=><li key={report.id} className="px-4 py-2.5"><p className="text-measured text-sm font-medium">{formatDate(report.reportDate)}</p><p className="line-clamp-1 text-xs text-muted-foreground">{report.summaryText || t("projectDetail.site_progress_report")}</p></li>)}</ul>
          {recentReports.length===0&&<p className="px-4 py-3 text-sm text-muted-foreground">{t("projectDetail.no_site_reports")}</p>}
        </section>
        <section className="panel">
          <div className="panel-head"><h2 className="panel-title">{t("projectDetail.recent_activity")}</h2></div>
          <ul className="data-list">{(projectStats?.recentActivity||[]).map((activity,index)=><li key={`${activity.timestamp}-${index}`} className="flex items-baseline justify-between gap-3 px-4 py-2.5"><p className="min-w-0 truncate text-sm">{t("activity.entity."+activity.entityType,{defaultValue:activity.entityType.replaceAll("_"," ")})} · {t("activity.action."+activity.action,{defaultValue:activity.action.replaceAll("_"," ")})}</p><p className="text-measured shrink-0 text-xs text-muted-foreground">{formatDate(activity.timestamp)}</p></li>)}</ul>
          {!projectStats?.recentActivity?.length&&<p className="px-4 py-3 text-sm text-muted-foreground">{t("projectDetail.no_recent_activity")}</p>}
        </section>
      </div>
    </div>
  );
};
