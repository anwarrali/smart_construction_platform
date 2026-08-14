import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../../utils/errorMessage";
import { useNavigate, useParams } from "react-router-dom";
import toast from "react-hot-toast";
import { ArrowLeft, CheckCircle2, FileText, GitBranch, MessageSquare, Paperclip, RotateCcw } from "lucide-react";
import api from "../../../../services/api";
import { AttachmentPanel } from "../../../../components/shared/AttachmentPanel";
import { Badge } from "../../../../components/ui/Badge";
import { Button } from "../../../../components/ui/Button";
import { Card } from "../../../../components/ui/Card";
import { Input } from "../../../../components/ui/Input";
import { Modal, ModalActions } from "../../../../components/ui/Modal";
import { useProjectWorkspace } from "../../../projects/context/ProjectWorkspaceContext";
import type { ConsultantReviewDetail } from "../../../../types/consultant";

const title = (value?: string) => (value || "—").replaceAll("_", " ").replace(/\b\w/g, (x) => x.toUpperCase());
type Action = "approve" | "reject" | "clarification" | "comment" | null;

export const ConsultantReviewDetailPage = () => {
  const { t } = useTranslation();
  const { reviewId } = useParams<{ reviewId: string }>();
  const workspace = useProjectWorkspace();
  const navigate = useNavigate();
  const [data, setData] = useState<ConsultantReviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState<Action>(null);
  const [comments, setComments] = useState("");
  const [reason, setReason] = useState("");
  const [corrections, setCorrections] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    if (!workspace.projectId || !reviewId) return;
    setLoading(true); setError("");
    try { setData(await api.consultant.review(workspace.projectId, reviewId)); }
    catch (err: any) { setError(errorMessage(err, "Unable to open this review submission.")); }
    finally { setLoading(false); }
  }, [reviewId, workspace.projectId]);
  useEffect(() => { load(); }, [load]);
  const run = async () => {
    if (!data || !action) return;
    if (action === "reject" && (!reason.trim() || !corrections.trim())) { toast.error("Rejection reason and required corrections are mandatory."); return; }
    if ((action === "clarification" || action === "comment") && !comments.trim()) { toast.error("Enter a comment or clarification question."); return; }
    setBusy(true);
    try {
      if (action === "approve") await api.tasks.approve(data.review.taskId, comments);
      if (action === "reject") await api.tasks.reject(data.review.taskId, comments, reason, corrections);
      if (action === "clarification") await api.tasks.requestClarification(data.review.taskId, comments);
      if (action === "comment") await api.tasks.addComment(data.review.taskId, `[Consultant Review] ${comments}`);
      toast.success(action === "approve" ? "Approval completed successfully." : action === "reject" ? "Rework request recorded." : action === "clarification" ? "Clarification requested." : "Review comment added.");
      setAction(null); setComments(""); setReason(""); setCorrections(""); await load();
    } catch (err: any) { toast.error(errorMessage(err, "Review action failed.")); }
    finally { setBusy(false); }
  };
  if (loading) return <div className="p-8 text-center text-muted-foreground">{t("consultantReview.loading_the_review_submission_and")}</div>;
  if (error || !data) return <Card><p className="text-destructive">{error || "Review not found."}</p><Button className="mt-4" onClick={() => navigate(workspace.path("reviews"))}>{t("consultantReview.back_to_reviews")}</Button></Card>;
  const active = ["pending", "in_review", "clarification_requested"].includes(data.review.reviewStatus);
  const canDecide = ["pending", "in_review"].includes(data.review.reviewStatus);
  return <div className="page-container space-y-6">
    <button className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground" onClick={() => navigate(workspace.path("reviews"))}><ArrowLeft size={16}/> Back to Reviews</button>
    <div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex flex-wrap items-center gap-2"><h1 className="text-2xl font-bold">{data.task.taskCode} · {data.task.title}</h1>{data.review.isCritical && <Badge variant="danger">{t("consultantReview.critical")}</Badge>}<Badge variant="info">{title(data.review.reviewStatus)}</Badge></div><p className="mt-1 text-muted-foreground">{data.task.projectName} · {title(data.task.discipline)} · submission #{data.review.submissionNumber}</p></div>
      <div className="flex flex-wrap gap-2">{data.review.reviewStatus === "pending" && <Button variant="outline" disabled={busy} onClick={async () => { setBusy(true); try { await api.tasks.startReview(data.review.taskId); toast.success("Review started."); await load(); } catch (err:any) { toast.error(errorMessage(err, "Unable to start review.")); } finally { setBusy(false); } }}>{t("consultantReview.start_review")}</Button>}{canDecide && <><Button variant="outline" onClick={() => setAction("clarification")}>{t("consultantReview.request_clarification")}</Button><Button variant="outline" onClick={() => setAction("reject")}>{t("consultantReview.request_rework")}</Button><Button onClick={() => setAction("approve")}>{t("consultantReview.approve")}</Button></>}<Button variant="ghost" onClick={() => setAction("comment")}>{t("consultantReview.add_comment")}</Button></div>
    </div>
    {data.review.clarificationQuestion && <Card className="border-state-review/30 bg-wash-review/50"><h2 className="font-semibold">{t("consultantReview.clarification")}</h2><p className="mt-2 text-sm">{data.review.clarificationQuestion}</p><p className="mt-2 text-sm text-muted-foreground">Contractor response: {data.review.clarificationResponse || "Awaiting response"}</p></Card>}
    <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]"><div className="space-y-6"><Card><h2 className="font-semibold">{t("consultantReview.task_and_submission")}</h2><div className="mt-4 grid gap-4 sm:grid-cols-2 text-sm"><p><span className="block text-muted-foreground">{t("consultantReview.contractor_engineer")}</span>{data.review.submittedBy?.fullName || "—"}</p><p><span className="block text-muted-foreground">{t("consultantReview.submitted")}</span>{new Date(data.review.submittedAt).toLocaleString()}</p><p><span className="block text-muted-foreground">{t("consultantReview.execution_progress")}</span>{data.task.progressPercentage}%</p><p><span className="block text-muted-foreground">{t("consultantReview.planned_dates")}</span>{data.task.plannedStartDate || "—"} to {data.task.plannedEndDate || "—"}</p><p><span className="block text-muted-foreground">{t("consultantReview.priority")}</span>{title(data.task.priority)}</p><p><span className="block text-muted-foreground">{t("consultantReview.project_manager")}</span>{data.task.projectManager?.fullName || "—"}</p></div><p className="mt-4 text-sm">{data.task.description || "No task description."}</p>{data.review.completionNote && <div className="mt-4 rounded bg-muted/40 p-3 text-sm"><strong>{t("consultantReview.completion_note")}</strong> {data.review.completionNote}</div>}</Card>
      <Card><h2 className="flex items-center gap-2 font-semibold"><Paperclip size={17}/> Submitted Evidence ({data.submissionEvidence.length})</h2><div className="mt-3 space-y-2">{data.submissionEvidence.map((item) => <a key={item.id} href={item.file_url} target="_blank" rel="noreferrer" className="flex items-center justify-between rounded border p-3 text-sm text-primary hover:bg-muted/30"><span>{item.filename}</span><span className="text-xs text-muted-foreground">{item.mime_type}</span></a>)}{!data.submissionEvidence.length && <p className="text-sm text-muted-foreground">{t("consultantReview.no_evidence_was_attached_to_this")}</p>}</div>{active && workspace.projectId && <AttachmentPanel projectId={workspace.projectId} entityType="TASK_REVIEW" entityId={data.review.id} />}</Card>
      <Card><h2 className="flex items-center gap-2 font-semibold"><GitBranch size={17}/> Dependency Impact</h2><div className="mt-3 grid gap-4 md:grid-cols-2"><div><p className="mb-2 text-sm font-medium">{t("consultantReview.predecessors")}</p>{data.dependencies.map((item) => <p key={item.id} className="border-b py-2 text-sm">{item.taskCode} · {item.title} <Badge>{title(item.status)}</Badge></p>)}{!data.dependencies.length && <p className="text-sm text-muted-foreground">{t("consultantReview.no_predecessors")}</p>}</div><div><p className="mb-2 text-sm font-medium">{t("consultantReview.dependent_tasks")}</p>{data.dependents.map((item) => <p key={item.id} className="border-b py-2 text-sm">{item.taskCode} · {item.title} {item.blockedByApproval && <Badge variant="warning">{t("consultantReview.approval_gated")}</Badge>}</p>)}{!data.dependents.length && <p className="text-sm text-muted-foreground">{t("consultantReview.no_dependent_tasks")}</p>}</div></div></Card>
      </div><div className="space-y-6"><Card><h2 className="flex items-center gap-2 font-semibold"><RotateCcw size={17}/> Review History</h2>{data.history.map((item) => <div key={item.id} className="border-b py-3 text-sm last:border-0"><div className="flex justify-between"><span>Attempt {item.submissionNumber}</span><Badge variant={item.reviewStatus === "approved" ? "success" : item.reviewStatus === "rejected" ? "danger" : "info"}>{title(item.reviewStatus)}</Badge></div>{item.rejectionReason && <p className="mt-1 text-state-overdue">{item.rejectionReason}</p>}<p className="mt-1 text-xs text-muted-foreground">{item.reviewedAt ? new Date(item.reviewedAt).toLocaleString() : new Date(item.submittedAt).toLocaleString()}</p></div>)}</Card>
      <Card><h2 className="flex items-center gap-2 font-semibold"><MessageSquare size={17}/> Task Comments</h2>{data.comments.map((item) => <div key={item.id} className="border-b py-3 text-sm last:border-0"><p>{item.content}</p><p className="mt-1 text-xs text-muted-foreground">{item.author?.fullName} · {new Date(item.createdAt).toLocaleString()}</p></div>)}{!data.comments.length && <p className="mt-3 text-sm text-muted-foreground">{t("consultantReview.no_comments")}</p>}</Card>
      <Card><h2 className="flex items-center gap-2 font-semibold"><FileText size={17}/> Project References</h2><p className="mt-2 text-sm text-muted-foreground">{data.documents.length} related documents · {data.siteReports.length} site reports · {data.issues.length} issues</p>{data.documents.slice(0,5).map((item) => <a key={item.id} href={item.fileUrl} target="_blank" rel="noreferrer" className="block border-b py-2 text-sm text-primary">{item.title} · v{item.version}</a>)}</Card></div></div>
    <Modal isOpen={!!action} onClose={() => !busy && setAction(null)} title={action === "approve" ? "Approve Submission" : action === "reject" ? "Request Rework" : action === "clarification" ? "Request Clarification" : "Add Review Comment"}><div className="space-y-4">{action === "approve" && <p className="rounded border border-state-verified/30 bg-wash-verified p-3 text-sm">Approval will mark this review-required task Done and unlock only its eligible dependent tasks.</p>}{action === "reject" && <><Input label={t("consultantReview.rejection_reason")} value={reason} onChange={(event) => setReason(event.target.value)}/><label className="block text-sm"><span className="font-medium">{t("consultantReview.required_corrections")}</span><textarea className="mt-1 w-full rounded-md border bg-background p-2" rows={4} value={corrections} onChange={(event) => setCorrections(event.target.value)}/></label></>}<label className="block text-sm"><span className="font-medium">{action === "clarification" ? "Clarification Question *" : action === "comment" ? "Review Comment *" : "Review Note"}</span><textarea className="mt-1 w-full rounded-md border bg-background p-2" rows={4} value={comments} onChange={(event) => setComments(event.target.value)}/></label><ModalActions><Button variant="outline" onClick={() => setAction(null)} disabled={busy}>{t("consultantReview.cancel")}</Button><Button isLoading={busy} onClick={run}>{action === "approve" ? <><CheckCircle2 size={15}/> Approve</> : action === "reject" ? "Request Rework" : "Save"}</Button></ModalActions></div></Modal>
  </div>;
};
