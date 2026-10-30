import { useCallback, useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { formatDateTime } from "../../../utils/dates";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { useNavigate, useParams } from "react-router-dom";
import api from "../../../services/api";
import { useAuth } from "../../../hooks/useAuth";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { Input } from "../../../components/ui/Input";
import type { Task } from "../../../types/task";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import { useRole } from "../../../hooks/useRole";
import { Select } from "../../../components/ui/Select";
import { formatAssigneeRole, getAvatarColor, getInitials } from "../../../utils/helpers";
import { EngineerTaskDetailPage } from "./EngineerTaskDetailPage";
import { ContextDiscussion } from "../../messages/components/ContextDiscussion";
import { CommunicationActions } from "../../../components/shared/CommunicationActions";

interface Comment { id: string; content: string; createdAt: string; author?: { fullName: string } }
interface Review { id: string; status: string; comments?: string; rejectionReason?: string; createdAt: string; submittedBy?: { fullName: string }; reviewedBy?: { fullName: string } }

const ManagedTaskDetailPage = () => {
  const { t } = useTranslation();
  const { id, taskId } = useParams<{ id?: string; taskId?: string }>();
  const activeTaskId = taskId || id;
  const workspace = useProjectWorkspace();
  const { hasCapability } = useRole();
  /** Editing tasks — and so their dependencies — is `task.edit`. */
  const editsTasks = hasCapability("task.edit");
  const navigate = useNavigate();
  const { user } = useAuth();
  const [task, setTask] = useState<Task | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [progress, setProgress] = useState(0);
  const [text, setText] = useState("");
  const [reviewText, setReviewText] = useState("");
  const [error, setError] = useState("");
  const [projectTasks, setProjectTasks] = useState<Task[]>([]);
  const [predecessorId, setPredecessorId] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [actionError, setActionError] = useState("");
  const load = useCallback(async () => {
    if (!activeTaskId) return;
    try {
      const [taskData, commentData, reviewData] = await Promise.all([api.tasks.getById(activeTaskId), api.tasks.comments(activeTaskId), api.tasks.reviews(activeTaskId)]);
      if (workspace.projectId && taskData.projectId !== workspace.projectId) throw new Error("Task is outside the active project");
      setTask(taskData); setProgress(taskData.progressPercentage); setComments(commentData); setReviews(reviewData);
      if (editsTasks) {
        const response = await api.tasks.getByProject(taskData.projectId);
        const candidates = (Array.isArray(response) ? response : response.data || []).filter((item: Task) => item.id !== taskData.id);
        setProjectTasks(candidates);
        setPredecessorId(candidates[0]?.id || "");
      }
    } catch {
      // A failed *refresh* keeps the task on screen; only a first load that
      // finds nothing replaces the page.
      setError((current) => current || "Unable to load this task or you no longer have access.");
    }
  }, [activeTaskId, editsTasks, workspace.projectId]);
  useEffect(() => { load(); }, [load]);
  if (error && !task) return <Card><p className="text-destructive">{error}</p></Card>;
  if (!task) return <p className="text-muted-foreground">{t("taskDetail.loading_task")}</p>;
  const engineer = !!user && task.assigneeIds.includes(user.id) && hasCapability("task.update_progress");
  const canReview = hasCapability("task.review");
  /* One request at a time, and the outcome comes from the change itself:
     the old version reported a failure when the *reload after* a committed
     save failed, and allowed repeated clicks to send the same save again. */
  const run = async (action: () => Promise<unknown>, success = t("taskDetail.saved")) => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setActionError("");
    try {
      try { await action(); } catch (e: any) { setActionError(errorMessage(e, "Action failed")); return; }
      toast.success(success);
      await load();
    } finally { inFlight.current = false; setBusy(false); }
  };
  // The server accepts execution progress only on started work
  // (`validate_progress_change`); offering the box on To Do/Backlog work just
  // produced "Start the task before updating progress".
  const progressOpen = ["in_progress", "rework_required"].includes(task.status);
  return <div className="space-y-6">
    <Button variant="ghost" onClick={() => navigate(workspace.isProjectWorkspace ? workspace.path("tasks") : "/tasks")}>← Back to Tasks</Button>
    <div className="page-header"><div><p className="page-kicker">{task.taskCode}</p><h1 className="page-title">{task.name}</h1><p className="text-muted-foreground">{task.description || "No description"}</p></div><div className="flex flex-col items-end gap-2"><Badge>{task.status.replaceAll("_", " ")}</Badge>
      {/* Consultation only — this is not task transfer: the assignee and
          status are untouched by sharing (enforced server-side). */}
      <CommunicationActions entityType="TASK" entityId={task.id} projectId={task.projectId} intents={["opinion"]} /></div></div>
    {error && <p className="text-sm text-destructive">{error}</p>}
    <ContextDiscussion projectId={task.projectId} contextType="TASK" contextId={task.id} title={t("taskDetail.task_discussion")} />
    <div className="grid lg:grid-cols-3 gap-6"><Card className="lg:col-span-2 space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm"><div><p className="text-muted-foreground">{t("taskDetail.priority")}</p><p>{task.priority}</p></div><div><p className="text-muted-foreground">{t("taskDetail.discipline")}</p><p>{task.discipline || "General"}</p></div><div><p className="text-muted-foreground">{t("taskDetail.start_date")}</p><p>{task.plannedStartDate || "—"}</p></div><div><p className="text-muted-foreground">{t("taskDetail.end_date")}</p><p>{task.plannedEndDate || "—"}</p></div><div><p className="text-muted-foreground">{t("taskDetail.duration")}</p><p>{task.durationDays ? `${task.durationDays} days` : "—"}</p></div></div>
      <div className="border-t pt-4"><p className="mb-3 text-sm font-medium">{t("taskDetail.assigned_team")}</p>{task.assignees.length ? <div className="flex flex-wrap gap-3">{task.assignees.map(assignee => <div key={assignee.id} className="flex items-center gap-2 border bg-background py-1 pl-1 pr-3"><div className="flex h-8 w-8 items-center justify-center overflow-hidden text-xs font-semibold text-white" style={{ backgroundColor: getAvatarColor(assignee.fullName) }}>{assignee.avatarUrl ? <img src={assignee.avatarUrl} alt="" className="h-full w-full object-cover" /> : getInitials(assignee.fullName)}</div><span><span className="block text-sm font-medium leading-tight">{assignee.fullName}</span><span className="block text-xs text-muted-foreground">{formatAssigneeRole(assignee)}</span></span></div>)}</div> : <p className="text-sm text-muted-foreground">{t("taskDetail.unassigned")}</p>}</div>
      {actionError && <p className="border border-state-overdue/30 bg-wash-overdue px-3 py-2 text-sm text-state-overdue">{actionError}</p>}
      {engineer && progressOpen && <div className="flex items-end gap-3"><Input label={t("taskDetail.progress")} type="number" min="0" max="100" value={progress} onChange={e => setProgress(Number(e.target.value))}/><Button isLoading={busy} disabled={busy} onClick={() => run(() => api.tasks.updateProgress(task.id, progress))}>{t("taskDetail.save_progress")}</Button>{progress === 100 && <Button disabled={busy} onClick={() => run(() => api.tasks.submitReview(task.id))}>{t("taskDetail.submit_for_review")}</Button>}</div>}
      {engineer && task.status === "todo" && <div className="flex flex-wrap items-center gap-3"><p className="text-sm text-muted-foreground">{t("taskDetail.start_before_progress")}</p><Button isLoading={busy} disabled={busy} onClick={() => run(() => api.tasks.start(task.id))}>{t("engineerTask.start_task")}</Button></div>}
      {canReview && task.status === "under_review" && <div className="space-y-3"><Input label={t("taskDetail.review_comment_required_for_rejection")} value={reviewText} onChange={e => setReviewText(e.target.value)}/><div className="flex gap-2"><Button onClick={() => run(() => api.tasks.approve(task.id, reviewText))}>{t("taskDetail.approve")}</Button><Button variant="destructive" disabled={!reviewText.trim()} onClick={() => run(() => api.tasks.reject(task.id, reviewText.trim(), reviewText.trim()))}>{t("taskDetail.reject_needs_rework")}</Button></div></div>}
    </Card><Card><h2 className="font-semibold mb-3">{t("taskDetail.review_history")}</h2><div className="space-y-3">{reviews.map(r => <div key={r.id} className="border-b pb-2 text-sm"><div className="flex items-center justify-between gap-2"><Badge>{r.status === "pending" ? "Under Review" : r.status === "approved" ? "Approved" : "Rejected · Needs Rework"}</Badge><span className="text-xs text-muted-foreground">{formatDateTime(r.createdAt)}</span></div><p className="mt-1">{r.comments || r.rejectionReason || "No comments"}</p><p className="mt-1 text-xs text-muted-foreground">Submitted by {r.submittedBy?.fullName || "team member"}{r.reviewedBy ? ` · Reviewed by ${r.reviewedBy.fullName}` : ""}</p></div>)}{reviews.length === 0 && <p className="text-sm text-muted-foreground">{t("taskDetail.no_reviews_yet")}</p>}</div></Card></div>
    <Card><h2 className="font-semibold mb-3">{t("taskDetail.comments")}</h2><div className="flex gap-2 mb-4"><Input value={text} onChange={e => setText(e.target.value)} placeholder={t("taskDetail.add_a_project_comment")}/><Button disabled={!text.trim()} onClick={() => run(async () => { await api.tasks.addComment(task.id, text); setText(""); })}>Add</Button></div><div className="space-y-3">{comments.map(c => <div key={c.id} className="border-t pt-3"><p className="text-sm font-medium">{c.author?.fullName || "Team member"}</p><p className="text-sm text-muted-foreground">{c.content}</p></div>)}</div></Card>
    {/* Dependencies drive the schedule: `schedule.edit`, as on the server. */}
    {hasCapability("schedule.edit") && <Card><h2 className="font-semibold">{t("taskDetail.finish_to_start_dependencies")}</h2><p className="mt-1 text-sm text-muted-foreground">Predecessors are stored on this project task and used by Gantt and critical-path calculations.</p>
      <div className="mt-3 flex items-end gap-2"><div className="min-w-64"><Select label={t("taskDetail.add_predecessor")} value={predecessorId} onChange={e => setPredecessorId(e.target.value)} options={projectTasks.map(item => ({ value: item.id, label: `${item.taskCode} — ${item.name} — ${item.status.replaceAll("_", " ")}` }))}/></div><Button disabled={!predecessorId} onClick={() => run(() => api.tasks.addDependency(task.id, predecessorId))}>{t("taskDetail.add_dependency")}</Button></div>
      <div className="mt-4 space-y-2">{task.dependencies.map(dependency => { const predecessor = projectTasks.find(item => item.id === dependency.dependsOnTaskId); return <div key={dependency.id} className="flex items-center justify-between rounded border p-2 text-sm"><span>{predecessor ? `${predecessor.taskCode} — ${predecessor.name}` : "Stored predecessor"} · {dependency.dependencyType.replaceAll("_", " ")}</span><Button size="sm" variant="ghost" onClick={() => run(() => api.tasks.removeDependency(task.id, dependency.id))}>{t("taskDetail.remove")}</Button></div>; })}{task.dependencies.length === 0 && <p className="text-sm text-muted-foreground">{t("taskDetail.no_predecessors")}</p>}</div>
    </Card>}
  </div>;
};

/**
 * People who manage or review work get the full task view; people whose work
 * is the tasks they hold get the execution view. Decided by capability, so a
 * role an office invents lands on the right one.
 */
export const TaskDetailPage = () => {
  const { hasCapability, permissionsReady } = useRole();
  if (!permissionsReady) return null;
  const managesWork = hasCapability("task.edit") || hasCapability("task.review") || hasCapability("task.view_all");
  return managesWork ? <ManagedTaskDetailPage /> : <EngineerTaskDetailPage />;
};
