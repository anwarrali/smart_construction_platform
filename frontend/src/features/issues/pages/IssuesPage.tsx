import { useState, useEffect, useCallback, useRef } from "react";
import { useVocabulary } from "../../../utils/vocabulary";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { Loader } from "../../../components/ui/Loader";
import { issuesService } from "../services/issues.service";
import { formatDate } from "../../../utils/date";
import type { Issue } from "../../../types/issue";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import api from "../../../services/api";
import { AttachmentPanel } from "../../../components/shared/AttachmentPanel";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import toast from "react-hot-toast";
import type { Task } from "../../../types/task";
import { useRole } from "../../../hooks/useRole";
import { useSearchParams } from "react-router-dom";
import { ContextDiscussion } from "../../messages/components/ContextDiscussion";
import { CommunicationActions } from "../../../components/shared/CommunicationActions";

export const IssuesPage = () => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const workspace = useProjectWorkspace();
  const { isProjectManager } = useRole();
  const [searchParams, setSearchParams] = useSearchParams();
  const focusedIssueId = searchParams.get("issueId");
  const activeProjectId = workspace.projectId;
  const [issues, setIssues] = useState<Issue[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const isFirstRender = useRef(true);
  const [formOpen, setFormOpen] = useState(false);
  const [projects, setProjects] = useState<{id: string; name: string}[]>([]);
  const [projectId, setProjectId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState("medium");
  const [category, setCategory] = useState("technical");
  const [taskId, setTaskId] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filterProject, setFilterProject] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterDiscipline, setFilterDiscipline] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [onlyAttachments, setOnlyAttachments] = useState(false);
  const [discussionIssueId, setDiscussionIssueId] = useState("");

  const fetchIssues = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await issuesService.list({ projectId: activeProjectId || filterProject || undefined, status: filterStatus || undefined,
        discipline: filterDiscipline || undefined, dateFrom: dateFrom || undefined, dateTo: dateTo || undefined,
        hasAttachments: onlyAttachments ? true : undefined });
      setIssues(response.data || []);
    } catch (err: any) {
      setIssues([]);
      toast.error(errorMessage(err, "Unable to load project issues."));
    } finally {
      setIsLoading(false);
    }
  }, [activeProjectId, filterProject, filterStatus, filterDiscipline, dateFrom, dateTo, onlyAttachments]);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      fetchIssues();
      return;
    }
    const timer = setTimeout(() => fetchIssues(), 0);
    return () => clearTimeout(timer);
  }, [fetchIssues]);

  useEffect(() => {
    if (activeProjectId && workspace.project) {
      setProjects([workspace.project]); setProjectId(activeProjectId);
      api.tasks.getByProject(activeProjectId).then((response: any) => setTasks(Array.isArray(response) ? response : response.data || [])).catch(() => setTasks([]));
      return;
    }
    api.projects.list().then(r => { setProjects(r.data); if (r.data[0]) setProjectId(r.data[0].id); });
  }, [activeProjectId, workspace.project]);
  const createIssue = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await issuesService.create({ projectId: activeProjectId || projectId, taskId: taskId || undefined, title, description, severity, category });
      setFormOpen(false); setTitle(""); setDescription(""); setTaskId("");
      await fetchIssues();
      toast.success("Site issue created.");
    } catch (err: any) {
      toast.error(errorMessage(err, "Issue creation failed."));
    }
  };

  if (isLoading) return <Loader fullPage />;

  const severityVariant: Record<string, "warning" | "danger"> = {
    low: "warning",
    medium: "warning",
    high: "danger",
    critical: "danger",
  };

  const statusVariant: Record<
    string,
    "warning" | "info" | "success" | "neutral"
  > = {
    open: "warning",
    in_progress: "info",
    resolved: "success",
    closed: "neutral",
  };
  const visibleIssues = focusedIssueId ? issues.filter((issue) => issue.id === focusedIssueId) : issues;

  return (
    <div className="page-container space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("issue.issues")}{workspace.project ? ` · ${workspace.project.name}` : ""}</h1>
          <p className="text-muted-foreground">
            {t("issuesPage.track_and_resolve_project_issues")}
          </p>
        </div>
        <Button onClick={() => setFormOpen(true)}>+ {t("issue.newIssue")}</Button>
      </div>
      {focusedIssueId && <div className="flex items-center justify-between rounded-lg border bg-card p-3 text-sm"><span>{t("issuesPage.showing_the_issue_opened_from_your")}</span><Button size="sm" variant="ghost" onClick={() => setSearchParams({})}>{t("issuesPage.show_all_issues")}</Button></div>}

      <Card className="grid gap-3 p-4 md:grid-cols-6">
        {activeProjectId ? <div className="flex items-center text-sm font-medium">{workspace.project?.name || t("project.selectedProject")}</div> : <Select value={filterProject} onChange={e=>setFilterProject(e.target.value)} options={[{value:"",label:t("project.allProjects")},...projects.map(project=>({value:project.id,label:project.name}))]}/>}
        {/* The option values are the API's own status and category vocabulary, so
            the labels come from the shared catalogue rather than a text tweak. */}
        <Select value={filterStatus} onChange={e=>setFilterStatus(e.target.value)} options={[{value:"",label:t("issue.allStatuses")},...['open','in_progress','resolved','closed'].map(value=>({value,label:vocabulary.issueStatus(value)}))]}/>
        <Select value={filterDiscipline} onChange={e=>setFilterDiscipline(e.target.value)} options={[{value:"",label:t("issue.allCategories")},...['technical','material','design','coordination','quality','schedule','equipment','site_condition','other'].map(value=>({value,label:vocabulary.issueCategory(value)}))]}/>
        <Input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}/>
        <Input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}/>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyAttachments} onChange={e=>setOnlyAttachments(e.target.checked)}/> {t("issue.hasAttachments")}</label>
      </Card>

      {visibleIssues.length === 0 ? (
        <Card>
          <div className="empty-state">
            <div className="empty-state-icon">⚠️</div>
            <p className="empty-state-title">{t("issuesPage.no_issues_found")}</p>
          </div>
        </Card>
      ) : (
        <div className="space-y-2">
          {visibleIssues.map((issue) => (
            <Card key={issue.id} className="p-4">
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-medium">{issue.title}</p>
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {issue.description}
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <Badge size="sm" variant={severityVariant[issue.severity]}>
                      {vocabulary.severity(issue.severity)}
                    </Badge>
                    <Badge size="sm" variant={statusVariant[issue.status]}>
                      {vocabulary.issueStatus(issue.status)}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {formatDate(issue.createdAt)}
                    </span>
                  </div>
                  <AttachmentPanel projectId={issue.projectId} entityType="ISSUE" entityId={issue.id} initialCount={issue.attachmentCount} />
                  <CommunicationActions className="mt-2 me-2 align-middle" entityType="ISSUE" entityId={issue.id} projectId={issue.projectId} />
                  <Button className="mt-2 mr-2" size="sm" variant="outline" onClick={() => setDiscussionIssueId((current) => current === issue.id ? "" : issue.id)}>{discussionIssueId === issue.id ? t("issue.hideDiscussion") : t("issue.openDiscussion")}</Button>
                  {isProjectManager && ["open", "in_progress"].includes(issue.status) && <Button className="mt-2" size="sm" variant="outline" onClick={async () => { const resolution = window.prompt("Resolution note (required)"); if (!resolution?.trim()) return; try { await issuesService.update(issue.id, { status: "resolved", resolutionNotes: resolution.trim() }); await fetchIssues(); toast.success("Issue resolved. The assigned Engineer can resume if no blockers remain."); } catch (err: any) { toast.error(errorMessage(err, "Issue could not be resolved.")); } }}>{t("issuesPage.resolve")}</Button>}
                  {discussionIssueId === issue.id && <div className="mt-3"><ContextDiscussion projectId={issue.projectId} contextType="ISSUE" contextId={issue.id} title={t("issuesPage.issue_discussion")} /></div>}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      <Modal isOpen={formOpen} onClose={() => setFormOpen(false)} title={t("issuesPage.raise_site_issue")}>
        <form onSubmit={createIssue} className="space-y-4">
          {activeProjectId ? <p className="text-sm"><span className="text-muted-foreground">{t("issuesPage.project")}</span> {workspace.project?.name}</p> : <Select label={t("issuesPage.project_2")} value={projectId} onChange={e => setProjectId(e.target.value)} options={projects.map(p => ({value:p.id,label:p.name}))}/>} 
          <Input label={t("issuesPage.title")} value={title} onChange={e => setTitle(e.target.value)} required/>
          <Input label={t("issuesPage.description")} value={description} onChange={e => setDescription(e.target.value)}/>
          <Select label={t("issuesPage.category")} value={category} onChange={e => setCategory(e.target.value)} options={["technical","material","design","coordination","quality","schedule","equipment","site_condition","other"].map(value => ({value,label:vocabulary.issueCategory(value)}))}/>
          <Select label={t("issuesPage.related_task_optional")} value={taskId} onChange={e => setTaskId(e.target.value)} options={[{ value: "", label: t("issue.projectLevel") }, ...tasks.map(task => ({ value: task.id, label: `${task.taskCode} — ${task.name}` }))]} />
          <Select label={t("issuesPage.severity")} value={severity} onChange={e => setSeverity(e.target.value)} options={["low","medium","high","critical"].map(value => ({value,label:vocabulary.severity(value)}))}/>
          <ModalActions><Button type="button" variant="outline" onClick={() => setFormOpen(false)}>{t("issuesPage.cancel")}</Button><Button type="submit" disabled={!(activeProjectId || projectId) || !title.trim()}>{t("issuesPage.create_issue")}</Button></ModalActions>
        </form>
      </Modal>
    </div>
  );
};
