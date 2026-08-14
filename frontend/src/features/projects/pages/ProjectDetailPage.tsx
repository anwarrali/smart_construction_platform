import { useState, useEffect } from "react";
import { useVocabulary } from "../../../utils/vocabulary";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { useParams, useNavigate } from "react-router-dom";
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
  const { isProjectManager, isAdmin } = useRole();

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
      if (isProjectManager || isAdmin) {
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
  }, [activeProjectId, isProjectManager, isAdmin]);

  if (isLoading) return <Loader fullPage />;

  if (error) return <div className="page-container"><Card><p className="text-sm text-state-overdue">{error}</p><Button className="mt-4" variant="outline" onClick={()=>navigate(isProjectManager ? ROUTES.PM_PROJECTS : ROUTES.PROJECTS)}>{t("projectDetail.back_to_projects")}</Button></Card></div>;

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

  return (
    <div className="page-container space-y-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate(isProjectManager ? ROUTES.PM_PROJECTS : ROUTES.PROJECTS)}
      >
        ← Back to Projects
      </Button>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{project.name}</h1>
        <div className="flex flex-wrap items-center gap-2"><Button size="sm" variant="outline" onClick={() => navigate(isProjectManager ? workspace.path("ifc") : `/projects/${project.id}/ifc`)}>{t("projectDetail.ifc_intelligence")}</Button><Button size="sm" variant="outline" onClick={() => navigate(isAdmin ? `/projects/${project.id}/evidence` : workspace.path("evidence"))}>{t("projectDetail.evidence_photos")}</Button>{isProjectManager && <Button size="sm" variant="outline" onClick={() => navigate(workspace.path("schedule"))}>{t("projectDetail.schedule")}</Button>}{(isProjectManager || isAdmin) && <Button size="sm" variant="outline" onClick={() => navigate(isAdmin ? `/projects/${project.id}/milestones` : workspace.path("milestones"))}>{t("projectDetail.milestones")}</Button>}{isProjectManager && <Button size="sm" variant="outline" onClick={() => navigate(workspace.path("messages"))}>{t("projectDetail.messages")}</Button>}{(isProjectManager || isAdmin) && <Button size="sm" variant="outline" onClick={() => navigate(isAdmin ? `/admin/projects/${project.id}/team` : workspace.path("team"))}>{t("projectDetail.team")}</Button>}<Badge variant={project.status === "active" ? "success" : "neutral"}>
          {project.status.replace("_", " ")}
        </Badge></div>
      </div>

      {projectStats && <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {([
          ["tasks", `${projectStats.taskDone}/${projectStats.taskTotal}`],
          ["inProgress", projectStats.taskInProgress],
          ["blocked", projectStats.taskBlocked],
          ["dueToday", projectStats.tasksDueToday],
          ["taskProgress", `${projectStats.taskProgressPercentage}%`],
          ["delayed", projectStats.delayedTasks],
          ["criticalPath", projectStats.criticalPathTasks],
          ["openIssues", projectStats.openIssues],
          ["urgentIssues", projectStats.urgentIssues],
          ["designChanges", projectStats.unresolvedDesignChanges],
          ["siteReports", projectStats.siteReports],
          ["team", projectStats.teamMembers],
          ["milestones", `${projectStats.milestoneCompleted}/${projectStats.milestoneTotal}`],
        ] as const).map(([key, value]) => <Card key={key} className="p-3"><p className="text-xs text-muted-foreground">{t(`projectDetail.stat.${key}`)}</p><p className="text-xl font-bold">{value}</p></Card>)}
      </div>}

      <div className="grid md:grid-cols-3 gap-6">
        <Card className="md:col-span-2 space-y-4">
          <h3 className="font-semibold">{t("projectDetail.project_details")}</h3>
          <p className="text-muted-foreground">{project.description}</p>
          <div className="grid grid-cols-2 gap-4 text-sm">
            {project.location && (
              <div>
                <span className="text-muted-foreground">{t("projectDetail.location")}</span>{" "}
                {project.location}
              </div>
            )}
            {project.projectType && (
              <div>
                <span className="text-muted-foreground">{t("projectDetail.type")}</span>{" "}
                {project.projectType}
              </div>
            )}
            <div>
              <span className="text-muted-foreground">{t("projectDetail.start")}</span>{" "}
              {formatDate(project.startDate || "")}
            </div>
            <div>
              <span className="text-muted-foreground">{t("projectDetail.planned_end")}</span>{" "}
              {formatDate(project.plannedEndDate || "")}
            </div>
          </div>
        </Card>

        <Card className="space-y-4">
          <h3 className="font-semibold">{t("projectDetail.progress")}</h3>
          <div className="text-center">
            <p className="text-4xl font-bold text-primary">
              {project.completionPercentage}%
            </p>
            <p className="text-sm text-muted-foreground mt-1">{t("projectDetail.complete")}</p>
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${project.completionPercentage}%` }}
            />
          </div>
          {project.status === "active" && (
            <Badge
              variant={daysRemaining <= 7 ? "warning" : "info"}
              className="w-full justify-center"
            >
              {daysRemaining > 0
                ? `${daysRemaining} days remaining`
                : "Overdue"}
            </Badge>
          )}
        </Card>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <h3 className="font-semibold mb-4">{t("projectDetail.budget")}</h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("projectDetail.planned")}</span>
              <span className="font-medium">
                {formatCurrency(project.budgetTotal || 0)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t("projectDetail.spent")}</span>
              <span className="font-medium">
                {formatCurrency(project.budgetSpent || 0)}
              </span>
            </div>
          </div>
        </Card>

        <Card>
          <h3 className="font-semibold mb-4">
            {t("projectDetail.stat.team")} ({project.members?.length || 0})
          </h3>
          <div className="space-y-2">
            {(isProjectManager || isAdmin) && availableEngineers.length > 0 && <div className="flex gap-2 pb-3 border-b"><Select value={engineerId} onChange={e=>setEngineerId(e.target.value)} options={availableEngineers.map(engineer=>({value:engineer.id,label:`${engineer.fullName} · ${vocabulary.role(engineer.role)} · ${engineer.engineerProfile?.discipline ? vocabulary.discipline(engineer.engineerProfile.discipline) : t("projectTeam.no_discipline")}`}))}/><Button size="sm" disabled={!engineerId} onClick={async()=>{const user=availableEngineers.find(item=>item.id===engineerId);if(!user)return;await api.projects.addMember(project.id,engineerId,user.role);await loadProject(project.id);}}>{t("common.add")}</Button></div>}
            {project.members?.map((member) => (
              <div
                key={member.id}
                className="flex items-center justify-between"
              >
                <span className="text-sm">{member.user?.fullName}</span>
                <div className="flex items-center gap-2"><Badge size="sm">{vocabulary.projectRole(member.roleOnProject)}</Badge>{(isProjectManager || isAdmin) && ["engineer","consultant"].includes(member.roleOnProject) && <Button size="sm" variant="ghost" onClick={async()=>{await api.projects.removeMember(project.id,member.userId);await loadProject(project.id);}}>{t("projectDetail.remove")}</Button>}</div>
              </div>
            ))}
            {(!project.members || project.members.length === 0) && (
              <p className="text-sm text-muted-foreground">
                {t("projectDetail.no_team_members_assigned")}
              </p>
            )}
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card><h3 className="font-semibold mb-3">{t("projectDetail.recent_design_changes")}</h3><div className="space-y-2">{recentChanges.map(change=><div key={change.id} className="border-b pb-2"><p className="text-sm font-medium">{change.title}</p><p className="text-xs text-muted-foreground">{vocabulary.designChangeStatus(change.status)}</p></div>)}{recentChanges.length===0&&<p className="text-sm text-muted-foreground">{t("projectDetail.no_design_changes")}</p>}</div></Card>
        <Card><h3 className="font-semibold mb-3">{t("projectDetail.recent_site_reports")}</h3><div className="space-y-2">{recentReports.map(report=><div key={report.id} className="border-b pb-2"><p className="text-sm font-medium">{formatDate(report.reportDate)}</p><p className="text-xs text-muted-foreground line-clamp-1">{report.summaryText || 'Site progress report'}</p></div>)}{recentReports.length===0&&<p className="text-sm text-muted-foreground">{t("projectDetail.no_site_reports")}</p>}</div></Card>
        <Card><h3 className="font-semibold mb-3">{t("projectDetail.recent_activity")}</h3><div className="space-y-2">{(projectStats?.recentActivity||[]).map((activity,index)=><div key={`${activity.timestamp}-${index}`} className="border-b pb-2"><p className="text-sm">{t("activity.entity."+activity.entityType,{defaultValue:activity.entityType.replaceAll("_"," ")})} · {t("activity.action."+activity.action,{defaultValue:activity.action.replaceAll("_"," ")})}</p><p className="text-xs text-muted-foreground">{formatDate(activity.timestamp)}</p></div>)}{!projectStats?.recentActivity?.length&&<p className="text-sm text-muted-foreground">{t("projectDetail.no_recent_activity")}</p>}</div></Card>
      </div>
    </div>
  );
};
