import { useCallback, useEffect, useState } from "react";
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

interface Comment { id: string; content: string; createdAt: string; author?: { fullName: string } }
interface Review { id: string; status: string; comments?: string; rejectionReason?: string; createdAt: string; submittedBy?: { fullName: string }; reviewedBy?: { fullName: string } }

const ManagedTaskDetailPage = () => {
  const { id, taskId } = useParams<{ id?: string; taskId?: string }>();
  const activeTaskId = taskId || id;
  const workspace = useProjectWorkspace();
  const { isProjectManager } = useRole();
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
  const load = useCallback(async () => {
    if (!activeTaskId) return;
    try {
      const [taskData, commentData, reviewData] = await Promise.all([api.tasks.getById(activeTaskId), api.tasks.comments(activeTaskId), api.tasks.reviews(activeTaskId)]);
      if (workspace.projectId && taskData.projectId !== workspace.projectId) throw new Error("Task is outside the active project");
      setTask(taskData); setProgress(taskData.progressPercentage); setComments(commentData); setReviews(reviewData);
      if (isProjectManager) {
        const response = await api.tasks.getByProject(taskData.projectId);
        const candidates = (Array.isArray(response) ? response : response.data || []).filter((item: Task) => item.id !== taskData.id);
        setProjectTasks(candidates);
        setPredecessorId(candidates[0]?.id || "");
      }
    } catch { setError("Unable to load this task or you no longer have access."); }
  }, [activeTaskId, isProjectManager, workspace.projectId]);
  useEffect(() => { load(); }, [load]);
  if (error) return <Card><p className="text-destructive">{error}</p></Card>;
  if (!task) return <p className="text-muted-foreground">Loading task…</p>;
  const engineer = user?.role === "engineer" && task.assigneeIds.includes(user.id);
  const consultant = user?.role === "consultant";
  const canReview = consultant || isProjectManager;
  const run = async (action: () => Promise<unknown>) => { setError(""); try { await action(); await load(); } catch (e: any) { setError(e?.response?.data?.detail || "Action failed"); } };
  return <div className="space-y-6">
    <Button variant="ghost" onClick={() => navigate(workspace.isProjectWorkspace ? workspace.path("tasks") : "/tasks")}>← Back to Tasks</Button>
    <div className="flex justify-between gap-4"><div><p className="text-sm font-semibold text-primary">{task.taskCode}</p><h1 className="text-2xl font-bold">{task.name}</h1><p className="text-muted-foreground">{task.description || "No description"}</p></div><Badge>{task.status.replaceAll("_", " ")}</Badge></div>
    {error && <p className="text-sm text-destructive">{error}</p>}
    <ContextDiscussion projectId={task.projectId} contextType="TASK" contextId={task.id} title="Task Discussion" />
    <div className="grid lg:grid-cols-3 gap-6"><Card className="lg:col-span-2 space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm"><div><p className="text-muted-foreground">Priority</p><p>{task.priority}</p></div><div><p className="text-muted-foreground">Discipline</p><p>{task.discipline || "General"}</p></div><div><p className="text-muted-foreground">Start date</p><p>{task.plannedStartDate || "—"}</p></div><div><p className="text-muted-foreground">End date</p><p>{task.plannedEndDate || "—"}</p></div><div><p className="text-muted-foreground">Duration</p><p>{task.durationDays ? `${task.durationDays} days` : "—"}</p></div></div>
      <div className="border-t pt-4"><p className="mb-3 text-sm font-medium">Assigned team</p>{task.assignees.length ? <div className="flex flex-wrap gap-3">{task.assignees.map(assignee => <div key={assignee.id} className="flex items-center gap-2 rounded-full border bg-background py-1 pl-1 pr-3"><div className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full text-xs font-semibold text-white" style={{ backgroundColor: getAvatarColor(assignee.fullName) }}>{assignee.avatarUrl ? <img src={assignee.avatarUrl} alt="" className="h-full w-full object-cover" /> : getInitials(assignee.fullName)}</div><span><span className="block text-sm font-medium leading-tight">{assignee.fullName}</span><span className="block text-xs text-muted-foreground">{formatAssigneeRole(assignee.role, assignee.engineerProfile?.discipline)}</span></span></div>)}</div> : <p className="text-sm text-muted-foreground">Unassigned</p>}</div>
      {engineer && !["under_review", "done"].includes(task.status) && <div className="flex items-end gap-3"><Input label="Progress %" type="number" min="0" max="100" value={progress} onChange={e => setProgress(Number(e.target.value))}/><Button onClick={() => run(() => api.tasks.updateProgress(task.id, progress))}>Save progress</Button>{progress === 100 && <Button onClick={() => run(() => api.tasks.submitReview(task.id))}>Submit for review</Button>}</div>}
      {canReview && task.status === "under_review" && <div className="space-y-3"><Input label="Review comment (required for rejection)" value={reviewText} onChange={e => setReviewText(e.target.value)}/><div className="flex gap-2"><Button onClick={() => run(() => api.tasks.approve(task.id, reviewText))}>Approve</Button><Button variant="destructive" disabled={!reviewText.trim()} onClick={() => run(() => api.tasks.reject(task.id, reviewText.trim(), reviewText.trim()))}>Reject · Needs Rework</Button></div></div>}
    </Card><Card><h2 className="font-semibold mb-3">Review history</h2><div className="space-y-3">{reviews.map(r => <div key={r.id} className="border-b pb-2 text-sm"><div className="flex items-center justify-between gap-2"><Badge>{r.status === "pending" ? "Under Review" : r.status === "approved" ? "Approved" : "Rejected · Needs Rework"}</Badge><span className="text-xs text-muted-foreground">{new Date(r.createdAt).toLocaleString()}</span></div><p className="mt-1">{r.comments || r.rejectionReason || "No comments"}</p><p className="mt-1 text-xs text-muted-foreground">Submitted by {r.submittedBy?.fullName || "team member"}{r.reviewedBy ? ` · Reviewed by ${r.reviewedBy.fullName}` : ""}</p></div>)}{reviews.length === 0 && <p className="text-sm text-muted-foreground">No reviews yet.</p>}</div></Card></div>
    <Card><h2 className="font-semibold mb-3">Comments</h2><div className="flex gap-2 mb-4"><Input value={text} onChange={e => setText(e.target.value)} placeholder="Add a project comment…"/><Button disabled={!text.trim()} onClick={() => run(async () => { await api.tasks.addComment(task.id, text); setText(""); })}>Add</Button></div><div className="space-y-3">{comments.map(c => <div key={c.id} className="border-t pt-3"><p className="text-sm font-medium">{c.author?.fullName || "Team member"}</p><p className="text-sm text-muted-foreground">{c.content}</p></div>)}</div></Card>
    {isProjectManager && <Card><h2 className="font-semibold">Finish-to-start dependencies</h2><p className="mt-1 text-sm text-muted-foreground">Predecessors are stored on this project task and used by Gantt and critical-path calculations.</p>
      <div className="mt-3 flex items-end gap-2"><div className="min-w-64"><Select label="Add predecessor" value={predecessorId} onChange={e => setPredecessorId(e.target.value)} options={projectTasks.map(item => ({ value: item.id, label: `${item.taskCode} — ${item.name} — ${item.status.replaceAll("_", " ")}` }))}/></div><Button disabled={!predecessorId} onClick={() => run(() => api.tasks.addDependency(task.id, predecessorId))}>Add dependency</Button></div>
      <div className="mt-4 space-y-2">{task.dependencies.map(dependency => { const predecessor = projectTasks.find(item => item.id === dependency.dependsOnTaskId); return <div key={dependency.id} className="flex items-center justify-between rounded border p-2 text-sm"><span>{predecessor ? `${predecessor.taskCode} — ${predecessor.name}` : "Stored predecessor"} · {dependency.dependencyType.replaceAll("_", " ")}</span><Button size="sm" variant="ghost" onClick={() => run(() => api.tasks.removeDependency(task.id, dependency.id))}>Remove</Button></div>; })}{task.dependencies.length === 0 && <p className="text-sm text-muted-foreground">No predecessors.</p>}</div>
    </Card>}
  </div>;
};

export const TaskDetailPage = () => {
  const { isEngineer } = useRole();
  return isEngineer ? <EngineerTaskDetailPage /> : <ManagedTaskDetailPage />;
};
