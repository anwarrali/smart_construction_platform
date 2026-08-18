import { useCallback, useEffect, useMemo, useState } from "react";
import { formatDateTime } from "../../../utils/dates";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { useNavigate, useParams } from "react-router-dom";
import toast from "react-hot-toast";
import api from "../../../services/api";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { AttachmentPanel } from "../../../components/shared/AttachmentPanel";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import { formatAssigneeRole, getAvatarColor, getInitials } from "../../../utils/helpers";
import type { Task } from "../../../types/task";
import type { Issue } from "../../../types/issue";
import type { FieldSubmission } from "../../../types/fieldSubmission";
import type { PhotoCategory } from "../../../types/photoArchive";
import { ContextDiscussion } from "../../messages/components/ContextDiscussion";
import { CommunicationActions } from "../../../components/shared/CommunicationActions";

interface Comment { id: string; content: string; createdAt: string; author?: { fullName: string } }
interface Review { id: string; status: string; comments?: string; rejectionReason?: string; requiredCorrections?: string; clarificationQuestion?: string; clarificationResponse?: string; submissionNumber?: number; createdAt: string; submittedBy?: { fullName: string }; reviewedBy?: { fullName: string } }
interface Activity { id: string; action: string; actorName: string; timestamp: string; details?: Record<string, unknown> }
interface DocumentItem { id: string; title: string; fileUrl: string; documentType: string; createdAt: string }

const blockerCategories = [
  "material_unavailable", "previous_task_incomplete", "drawing_unavailable",
  "consultant_clarification_required", "equipment_unavailable", "labor_shortage",
  "site_access_issue", "safety_restriction", "technical_conflict", "other",
];

export const EngineerTaskDetailPage = () => {
  const { t } = useTranslation();
  const { taskId } = useParams<{ taskId: string }>();
  const workspace = useProjectWorkspace();
  const navigate = useNavigate();
  const [task, setTask] = useState<Task | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [blockers, setBlockers] = useState<Issue[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [fieldSubmissions, setFieldSubmissions] = useState<FieldSubmission[]>([]);
  const [photoCategories, setPhotoCategories] = useState<PhotoCategory[]>([]);
  const [rejectionReasons, setRejectionReasons] = useState<Record<string, string>>({});
  const [milestoneName, setMilestoneName] = useState("");
  const [progress, setProgress] = useState(0);
  const [progressNote, setProgressNote] = useState("");
  const [comment, setComment] = useState("");
  const [completionNote, setCompletionNote] = useState("");
  const [clarificationResponse, setClarificationResponse] = useState("");
  const [workOpen, setWorkOpen] = useState(false);
  const [workCompleted, setWorkCompleted] = useState("");
  const [remainingWork, setRemainingWork] = useState("");
  const [workersCount, setWorkersCount] = useState("");
  const [equipment, setEquipment] = useState("");
  const [materials, setMaterials] = useState("");
  const [problems, setProblems] = useState("");
  const [blockerOpen, setBlockerOpen] = useState(false);
  const [blockerCategory, setBlockerCategory] = useState(blockerCategories[0]);
  const [blockerSeverity, setBlockerSeverity] = useState("medium");
  const [blockerDescription, setBlockerDescription] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!taskId || !workspace.projectId) {
      setError("The selected project or task is missing.");
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const taskData: Task = await api.tasks.getById(taskId);
      if (taskData.projectId !== workspace.projectId) throw new Error("Task is outside the active project");
      const [commentData, reviewData, activityData, blockerData, issueData, documentData, milestoneData, fieldData, categoryData] = await Promise.all([
        api.tasks.comments(taskId),
        api.tasks.reviews(taskId),
        api.tasks.activity(taskId),
        api.tasks.blockers(taskId),
        api.issues.list({ projectId: workspace.projectId, taskId }),
        api.documents.list({ projectId: workspace.projectId, taskId }),
        api.milestones.list(workspace.projectId),
        api.fieldSubmissions.byTask(taskId),
        api.photoArchive.categories(workspace.projectId),
      ]);
      setTask(taskData);
      setProgress(taskData.progressPercentage);
      setComments(commentData);
      setReviews(reviewData);
      setActivity(activityData);
      setBlockers(blockerData);
      setIssues(issueData);
      setDocuments(Array.isArray(documentData) ? documentData : documentData.data || documentData.items || []);
      setMilestoneName(milestoneData.find((item: any) => item.id === taskData.milestoneId)?.name || "");
      setFieldSubmissions(fieldData);
      setPhotoCategories(categoryData);
    } catch (err: any) {
      setTask(null);
      setError(errorMessage(err, "Unable to load this task or you no longer have access."));
    } finally {
      setIsLoading(false);
    }
  }, [taskId, workspace.projectId]);

  useEffect(() => { load(); }, [load]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await load();
      toast.success(success);
      return true;
    } catch (err: any) {
      const message = errorMessage(err, "Action failed. Please try again.");
      setError(message);
      toast.error(message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const togglePhotoCategory = async (
    photoId: string,
    currentIds: string[],
    categoryId: string,
  ) => {
    const next = currentIds.includes(categoryId)
      ? currentIds.filter((id) => id !== categoryId)
      : [...currentIds, categoryId];
    await run(
      () => api.fieldSubmissions.replacePhotoCategories(photoId, next),
      "Photo categories updated.",
    );
  };

  const latestRejectedReview = useMemo(() => reviews.find((review) => review.status === "rejected"), [reviews]);
  const clarificationReview = useMemo(() => reviews.find((review) => review.status === "clarification_requested"), [reviews]);

  if (isLoading) return <Card className="p-10 text-center text-muted-foreground">{t("engineerTask.loading_task_details")}</Card>;
  if (error && !task) return <Card className="mx-auto max-w-xl p-8 text-center text-destructive">{error}<div><Button className="mt-4" onClick={load}>{t("engineerTask.retry")}</Button></div></Card>;
  if (!task) return null;

  const executionLocked = ["under_review", "done", "cancelled"].includes(task.status);
  const unresolvedBlockers = blockers.filter((item) => ["open", "in_progress"].includes(item.status));

  return <div className="page-container space-y-6">
    <Button variant="ghost" onClick={() => navigate(workspace.path("tasks"))}>← Back to My Tasks</Button>
    <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="font-mono text-sm font-semibold text-primary">{task.taskCode}</p><h1 className="text-2xl font-bold">{task.name}</h1><p className="mt-1 max-w-3xl text-muted-foreground">{task.description || "No description provided."}</p></div><div className="flex flex-col items-end gap-2"><div className="flex gap-2"><Badge variant={task.status === "blocked" || task.status === "rework_required" ? "danger" : task.status === "done" ? "success" : "info"}>{task.status.replaceAll("_", " ")}</Badge>{task.isCriticalPath && <Badge variant="danger">{t("engineerTask.critical_path")}</Badge>}</div>
      {/* Consultation only — sharing never reassigns this task. */}
      <CommunicationActions entityType="TASK" entityId={task.id} projectId={task.projectId} intents={["opinion"]} /></div></div>
    {error && <Card className="border-destructive/30 p-3 text-sm text-destructive">{error}</Card>}

    {task.status === "rework_required" && <Card className="border-state-review/30 bg-wash-review p-4"><h2 className="font-semibold text-state-review">{t("engineerTask.rework_required")}</h2><p className="mt-2 text-sm text-state-review">{latestRejectedReview?.rejectionReason || task.rejectionReason || "Review corrections are required."}</p>{latestRejectedReview?.comments && <p className="mt-1 text-sm text-state-review">{latestRejectedReview.comments}</p>}<Button className="mt-3" disabled={busy} onClick={() => run(() => api.tasks.startRework(task.id), "Corrective work started.")}>{t("engineerTask.start_corrective_work")}</Button></Card>}
    {task.status === "under_review" && <Card className="border-state-blocked/30 bg-wash-blocked p-4"><h2 className="font-semibold text-state-blocked">{t("engineerTask.work_is_under_review")}</h2><p className="mt-1 text-sm text-state-blocked">{t("engineerTask.execution_values_and_submitted_evidence")}</p><p className="mt-2 text-xs text-state-blocked">Submitted {task.submittedForReviewAt || "recently"}</p>{clarificationReview && <div className="mt-4 rounded border border-state-review/30 bg-white p-3"><p className="text-sm font-medium text-state-review">Consultant clarification: {clarificationReview.clarificationQuestion}</p><div className="mt-3 flex flex-col gap-2 sm:flex-row"><Input value={clarificationResponse} onChange={(event) => setClarificationResponse(event.target.value)} placeholder={t("engineerTask.provide_the_requested_clarification")}/><Button disabled={busy || clarificationResponse.trim().length < 3} onClick={() => run(() => api.tasks.respondClarification(task.id, clarificationResponse.trim()), "Clarification response sent.").then((ok) => { if (ok) setClarificationResponse(""); })}>{t("engineerTask.send_response")}</Button></div></div>}</Card>}

    <div className="grid gap-6 xl:grid-cols-3">
      <Card className="space-y-5 xl:col-span-2">
        <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4"><div><p className="text-muted-foreground">{t("engineerTask.project")}</p><p className="font-medium">{workspace.project?.name}</p></div><div><p className="text-muted-foreground">{t("engineerTask.discipline")}</p><p className="font-medium capitalize">{task.discipline || "General"}</p></div><div><p className="text-muted-foreground">{t("engineerTask.priority")}</p><p className="font-medium capitalize">{task.priority}</p></div><div><p className="text-muted-foreground">{t("engineerTask.progress")}</p><p className="font-medium">{task.progressPercentage}%</p></div><div><p className="text-muted-foreground">{t("engineerTask.planned_start")}</p><p>{task.plannedStartDate || "—"}</p></div><div><p className="text-muted-foreground">{t("engineerTask.due_date")}</p><p>{task.plannedEndDate || "—"}</p></div><div><p className="text-muted-foreground">{t("engineerTask.duration")}</p><p>{task.durationDays ? `${task.durationDays} days` : "—"}</p></div><div><p className="text-muted-foreground">{t("engineerTask.milestone")}</p><p>{milestoneName || "—"}</p></div></div>
        <div className="border-t pt-4"><p className="mb-3 text-sm font-medium">{t("engineerTask.assigned_execution_team")}</p><div className="flex flex-wrap gap-3">{task.assignees.map((assignee) => <div key={assignee.id} className="flex items-center gap-2 rounded-full border py-1 pl-1 pr-3"><div className="flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold text-white" style={{ backgroundColor: getAvatarColor(assignee.fullName) }}>{getInitials(assignee.fullName)}</div><span><span className="block text-sm font-medium">{assignee.fullName}</span><span className="block text-xs text-muted-foreground">{formatAssigneeRole(assignee.role, assignee.engineerProfile?.discipline)}</span></span></div>)}</div></div>
        <div className="border-t pt-4"><p className="text-sm font-medium">{t("engineerTask.dependencies")}</p><div className="mt-2 space-y-2">{task.dependencies.map((dependency) => <div key={dependency.id} className="rounded border p-2 text-sm"><span className="font-medium">{dependency.dependsOnTaskCode || "Predecessor"}</span>{dependency.dependsOnTaskName ? ` — ${dependency.dependsOnTaskName}` : ""}<span className="text-muted-foreground"> · {dependency.dependencyType.replaceAll("_", " ")}{dependency.dependsOnTaskStatus ? ` · ${dependency.dependsOnTaskStatus.replaceAll("_", " ")}` : ""}</span></div>)}{!task.dependencies.length && <p className="text-sm text-muted-foreground">{t("engineerTask.no_predecessor_dependencies")}</p>}</div></div>

        {task.status === "todo" && <Button disabled={busy} onClick={() => run(() => api.tasks.start(task.id), "Task started.")}>{t("engineerTask.start_task")}</Button>}
        {task.status === "blocked" && <div><p className="mb-2 text-sm text-destructive">{unresolvedBlockers.length ? `${unresolvedBlockers.length} blocker(s) still require Project Manager resolution.` : "All blockers are resolved. You may resume execution."}</p><Button disabled={busy || unresolvedBlockers.length > 0} onClick={() => run(() => api.tasks.resumeAfterBlocker(task.id), "Task resumed.")}>{t("engineerTask.resume_work")}</Button></div>}
        {task.status === "in_progress" && <div className="space-y-3 border-t pt-4"><h2 className="font-semibold">{t("engineerTask.update_progress")}</h2><div className="grid gap-3 sm:grid-cols-[160px_1fr_auto]"><Input label={t("engineerTask.progress_2")} type="number" min="0" max="100" value={progress} onChange={(event) => setProgress(Number(event.target.value))} /><Input label={t("engineerTask.progress_note_optional")} value={progressNote} onChange={(event) => setProgressNote(event.target.value)} /><Button className="self-end" disabled={busy} onClick={() => run(() => api.tasks.updateProgress(task.id, progress, progressNote), "Progress updated.").then((ok) => { if (ok) setProgressNote(""); })}>{t("engineerTask.save")}</Button></div><div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => setWorkOpen((value) => !value)}>{t("engineerTask.add_work_update")}</Button><Button variant="outline" onClick={() => setBlockerOpen((value) => !value)}>{t("engineerTask.report_blocker")}</Button></div>{task.progressPercentage === 100 && <div className="rounded border p-3"><Input label={task.reviewRequired ? "Completion note for Consultant (optional)" : "Completion note (optional)"} value={completionNote} onChange={(event) => setCompletionNote(event.target.value)} /><Button className="mt-3" disabled={busy} onClick={() => run(() => task.reviewRequired ? api.tasks.submitReview(task.id, completionNote) : api.tasks.completeExecution(task.id), task.reviewRequired ? "Work submitted for review." : "Execution completed.")}>{task.reviewRequired ? "Submit for Consultant Review" : "Complete Internal Task"}</Button></div>}</div>}

        {workOpen && !executionLocked && <form className="space-y-3 rounded-lg border bg-muted/20 p-4" onSubmit={async (event) => { event.preventDefault(); const ok = await run(() => api.tasks.addWorkUpdate(task.id, { progressPercentage: progress, workCompletedToday: workCompleted, remainingWork: remainingWork || undefined, workersCount: workersCount ? Number(workersCount) : undefined, equipmentUsed: equipment || undefined, materialsUsed: materials || undefined, problemsEncountered: problems || undefined }), "Work update added."); if (ok) { setWorkOpen(false); setWorkCompleted(""); setRemainingWork(""); setWorkersCount(""); setEquipment(""); setMaterials(""); setProblems(""); } }}><h2 className="font-semibold">{t("engineerTask.daily_work_update")}</h2><label className="block text-sm font-medium">{t("engineerTask.work_completed_today")}<textarea className="mt-1 min-h-24 w-full rounded-md border bg-background p-3 text-sm" value={workCompleted} onChange={(event) => setWorkCompleted(event.target.value)} required /></label><div className="grid gap-3 sm:grid-cols-2"><Input label={t("engineerTask.remaining_work")} value={remainingWork} onChange={(event) => setRemainingWork(event.target.value)} /><Input label={t("engineerTask.number_of_workers")} type="number" min="0" value={workersCount} onChange={(event) => setWorkersCount(event.target.value)} /><Input label={t("engineerTask.equipment_used")} value={equipment} onChange={(event) => setEquipment(event.target.value)} /><Input label={t("engineerTask.materials_used")} value={materials} onChange={(event) => setMaterials(event.target.value)} /></div><Input label={t("engineerTask.problems_encountered")} value={problems} onChange={(event) => setProblems(event.target.value)} /><div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setWorkOpen(false)}>{t("engineerTask.cancel")}</Button><Button type="submit" disabled={busy || !workCompleted.trim()}>{t("engineerTask.save_update")}</Button></div></form>}

        {blockerOpen && !executionLocked && <form className="space-y-3 rounded-lg border border-state-overdue/30 bg-wash-overdue p-4" onSubmit={async (event) => { event.preventDefault(); const ok = await run(() => api.tasks.reportBlocker(task.id, { category: blockerCategory, description: blockerDescription, severity: blockerSeverity }), "Blocker reported to the Project Manager."); if (ok) { setBlockerOpen(false); setBlockerDescription(""); } }}><h2 className="font-semibold text-state-overdue">{t("engineerTask.report_task_blocker")}</h2><div className="grid gap-3 sm:grid-cols-2"><Select label={t("engineerTask.category")} value={blockerCategory} onChange={(event) => setBlockerCategory(event.target.value)} options={blockerCategories.map((value) => ({ value, label: value.replaceAll("_", " ") }))} /><Select label={t("engineerTask.severity")} value={blockerSeverity} onChange={(event) => setBlockerSeverity(event.target.value)} options={["low", "medium", "high", "critical"].map((value) => ({ value, label: value }))} /></div><label className="block text-sm font-medium">{t("engineerTask.description")}<textarea className="mt-1 min-h-24 w-full rounded-md border bg-background p-3 text-sm" value={blockerDescription} onChange={(event) => setBlockerDescription(event.target.value)} required /></label><div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setBlockerOpen(false)}>{t("engineerTask.cancel")}</Button><Button type="submit" disabled={busy || !blockerDescription.trim()}>{t("engineerTask.report_blocker")}</Button></div></form>}
      </Card>

      <div className="space-y-6"><Card><h2 className="font-semibold">{t("engineerTask.task_evidence")}</h2><p className="mt-1 text-sm text-muted-foreground">Upload JPG, PNG, PDF, or supported technical files. Submitted evidence is preserved during review.</p><AttachmentPanel projectId={task.projectId} entityType="TASK" entityId={task.id} /></Card><Card><h2 className="font-semibold">{t("engineerTask.related_documents")}</h2><div className="mt-3 space-y-2">{documents.map((item) => <a key={item.id} href={item.fileUrl} target="_blank" rel="noreferrer" className="block rounded border p-2 text-sm text-primary hover:bg-muted/30">{item.title}</a>)}{!documents.length && <p className="text-sm text-muted-foreground">{t("engineerTask.no_linked_technical_documents")}</p>}</div></Card><Card><h2 className="font-semibold">{t("engineerTask.related_issues_blockers")}</h2><div className="mt-3 space-y-2">{issues.map((item) => <div key={item.id} className="rounded border p-2 text-sm"><div className="flex justify-between gap-2"><span className="font-medium">{item.title}</span><Badge size="sm" variant={item.status === "open" ? "warning" : "neutral"}>{item.status}</Badge></div><p className="mt-1 text-xs text-muted-foreground">{item.description}</p></div>)}{!issues.length && <p className="text-sm text-muted-foreground">{t("engineerTask.no_related_issues")}</p>}</div></Card></div>
    </div>

    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h2 className="font-semibold">{t("engineerTask.worker_field_evidence")}</h2><p className="text-sm text-muted-foreground">Verification confirms evidence only; it does not change official task progress or Consultant review status.</p></div>
        <Badge variant="info">{fieldSubmissions.filter((item) => item.status === "SUBMITTED").length} pending</Badge>
      </div>
      <div className="mt-4 space-y-4">
        {fieldSubmissions.map((submission) => <div key={submission.id} className="rounded-lg border p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><p className="font-medium">{submission.worker.fullName}</p><p className="text-xs text-muted-foreground">{formatDateTime(submission.createdAt)}</p></div>
            <Badge variant={submission.status === "VERIFIED" ? "success" : submission.status === "REJECTED" ? "danger" : "warning"}>{submission.status.toLowerCase()}</Badge>
          </div>
          {submission.description && <p className="mt-3 whitespace-pre-line text-sm">{submission.description}</p>}
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {submission.photos.map((photo) => <div key={photo.id} className="overflow-hidden rounded-lg border bg-muted/20">
              <a href={photo.attachment.fileUrl} target="_blank" rel="noreferrer">
                <img src={photo.attachment.fileUrl} alt={photo.attachment.originalFilename} className="aspect-square w-full object-cover" />
              </a>
              <p className="truncate px-2 pt-2 text-xs">{photo.direction?.toLowerCase() || "Unlabelled view"}</p>
              <div className="flex flex-wrap gap-1 p-2">
                {photoCategories.filter((item) => item.active).map((category) => {
                  const active = photo.categories.some((item) => item.id === category.id);
                  return <button key={category.id} type="button" disabled={busy}
                    onClick={() => togglePhotoCategory(photo.id, photo.categories.map((item) => item.id), category.id)}
                    className={`rounded-full border px-2 py-1 text-[10px] ${active ? "border-primary bg-primary text-primary-foreground" : "bg-background text-muted-foreground"}`}>
                    {category.name}
                  </button>;
                })}
              </div>
            </div>)}
          </div>
          {submission.reviewComment && <p className={`mt-3 rounded p-2 text-sm ${submission.status === "REJECTED" ? "bg-wash-overdue text-state-overdue" : "bg-wash-verified text-state-verified"}`}>{submission.reviewComment}</p>}
          {submission.status === "SUBMITTED" && <div className="mt-4 flex flex-col gap-2 sm:flex-row">
            <Button disabled={busy} onClick={() => run(() => api.fieldSubmissions.verify(submission.id), "Worker evidence verified. Official progress was not changed.")}>{t("engineerTask.verify_evidence")}</Button>
            <Input value={rejectionReasons[submission.id] || ""} onChange={(event) => setRejectionReasons((current) => ({ ...current, [submission.id]: event.target.value }))} placeholder={t("engineerTask.required_rejection_reason")} />
            <Button variant="outline" disabled={busy || (rejectionReasons[submission.id] || "").trim().length < 3} onClick={() => run(() => api.fieldSubmissions.reject(submission.id, rejectionReasons[submission.id].trim()), "Evidence returned to the Worker.")}>{t("engineerTask.reject")}</Button>
          </div>}
        </div>)}
        {!fieldSubmissions.length && <p className="py-6 text-center text-sm text-muted-foreground">{t("engineerTask.no_worker_evidence_has_been_submitted")}</p>}
      </div>
    </Card>

    <ContextDiscussion projectId={task.projectId} contextType="TASK" contextId={task.id} title={t("engineerTask.task_discussion")} />

    <div className="grid gap-6 xl:grid-cols-2"><Card><h2 className="font-semibold">{t("engineerTask.comments_notes")}</h2><div className="mt-3 flex gap-2"><Input value={comment} onChange={(event) => setComment(event.target.value)} placeholder={t("engineerTask.add_a_task_comment")} /><Button disabled={busy || !comment.trim()} onClick={() => run(() => api.tasks.addComment(task.id, comment.trim()), "Comment added.").then((ok) => { if (ok) setComment(""); })}>Add</Button></div><div className="mt-4 space-y-3">{comments.map((item) => <div key={item.id} className="border-t pt-3"><div className="flex justify-between gap-2"><p className="text-sm font-medium">{item.author?.fullName || "Team member"}</p><p className="text-xs text-muted-foreground">{formatDateTime(item.createdAt)}</p></div><p className="whitespace-pre-line text-sm text-muted-foreground">{item.content}</p></div>)}{!comments.length && <p className="text-sm text-muted-foreground">{t("engineerTask.no_comments_yet")}</p>}</div></Card><Card><h2 className="font-semibold">{t("engineerTask.review_history")}</h2><div className="mt-3 space-y-3">{reviews.map((item, index) => <div key={item.id} className="rounded border p-3 text-sm"><div className="flex justify-between gap-2"><Badge variant={item.status === "rejected" ? "danger" : item.status === "approved" ? "success" : "warning"}>Attempt {reviews.length - index} · {item.status}</Badge><span className="text-xs text-muted-foreground">{formatDateTime(item.createdAt)}</span></div><p className="mt-2">{item.rejectionReason || item.comments || "Waiting for review feedback."}</p><p className="mt-1 text-xs text-muted-foreground">Submitted by {item.submittedBy?.fullName || "execution team"}{item.reviewedBy ? ` · Reviewed by ${item.reviewedBy.fullName}` : ""}</p></div>)}{!reviews.length && <p className="text-sm text-muted-foreground">{t("engineerTask.no_review_submissions_yet")}</p>}</div></Card></div>
    <Card><h2 className="font-semibold">{t("engineerTask.activity_history")}</h2><div className="mt-3 divide-y">{activity.map((item) => <div key={item.id} className="py-3"><p className="text-sm font-medium">{t("activity.action." + item.action, { defaultValue: item.action.replaceAll("_", " ") })}</p><p className="text-xs text-muted-foreground">{item.actorName} · {formatDateTime(item.timestamp)}</p></div>)}{!activity.length && <p className="py-6 text-sm text-muted-foreground">{t("engineerTask.no_execution_activity_recorded")}</p>}</div></Card>
  </div>;
};
