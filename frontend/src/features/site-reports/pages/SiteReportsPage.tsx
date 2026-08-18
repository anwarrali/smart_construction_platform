import { useState, useEffect, useCallback, useRef } from "react";
import { useVocabulary } from "../../../utils/vocabulary";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { useParams, useSearchParams } from "react-router-dom";
import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { Loader } from "../../../components/ui/Loader";
import { siteReportsService } from "../services/siteReports.service";
import { formatDate } from "../../../utils/date";
import { Button } from "../../../components/ui/Button";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import api from "../../../services/api";
import axios from "../../../services/axios";
import { useRole } from "../../../hooks/useRole";
import { AttachmentPanel } from "../../../components/shared/AttachmentPanel";
import { CommunicationActions } from "../../../components/shared/CommunicationActions";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import toast from "react-hot-toast";
import type { Task } from "../../../types/task";
import { useAuth } from "../../../hooks/useAuth";

interface SiteReport {
  id: string;
  projectId: string;
  reportDate: string;
  summaryText?: string;
  progressPercentageReported?: number;
  weatherConditions?: string;
  workersCount?: number;
  reviewStatus?: string;
  submittedById: string;
  taskId?: string;
  equipment?: string;
  workCompleted?: string;
  workInProgress?: string;
  delays?: string;
  issuesSummary?: string;
  notes?: string;
  attachmentCount: number;
  rejectionReason?: string;
  reviewedBy?: { id: string; fullName: string };
  reviewedAt?: string;
}

export const SiteReportsPage = () => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const { id } = useParams<{ id: string }>();
  const workspace = useProjectWorkspace();
  const activeProjectId = workspace.projectId || id;
  const [reports, setReports] = useState<SiteReport[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const isFirstRender = useRef(true);
  const { role } = useRole();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const focusedReportId = searchParams.get("reportId");
  const [formOpen, setFormOpen] = useState(false);
  const [prefilledVisit, setPrefilledVisit] = useState<{ id: string; visitType: string; reportDate: string } | null>(null);
  const [projects, setProjects] = useState<{id:string;name:string}[]>([]);
  const [projectId, setProjectId] = useState("");
  const [summary, setSummary] = useState("");
  const [weather, setWeather] = useState("");
  const [workers, setWorkers] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState("");
  const [equipment, setEquipment] = useState("");
  const [workCompleted, setWorkCompleted] = useState("");
  const [workInProgress, setWorkInProgress] = useState("");
  const [delays, setDelays] = useState("");
  const [issuesSummary, setIssuesSummary] = useState("");
  const [notes, setNotes] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [siteProjectIds, setSiteProjectIds] = useState<string[]>([]);
  const [filterProject, setFilterProject] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterDiscipline, setFilterDiscipline] = useState("");
  const [rejectingReport, setRejectingReport] = useState<SiteReport | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [verifyingId, setVerifyingId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [onlyAttachments, setOnlyAttachments] = useState(false);

  const fetchReports = useCallback(async () => {
    setIsLoading(true);
    try {
      let data;
      if (activeProjectId) {
        data = await siteReportsService.getByProject(activeProjectId);
      } else {
        data = await siteReportsService.list({ projectId: filterProject || undefined,
          status: filterStatus || undefined, discipline: filterDiscipline || undefined,
          dateFrom: dateFrom || undefined, dateTo: dateTo || undefined,
          hasAttachments: onlyAttachments ? true : undefined });
      }
      setReports(data || []);
    } catch (err: any) {
      setReports([]);
      toast.error(errorMessage(err, "Unable to load site reports."));
    }
    setIsLoading(false);
  }, [activeProjectId, filterProject, filterStatus, filterDiscipline, dateFrom, dateTo, onlyAttachments]);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      fetchReports();
      return;
    }
    const timer = setTimeout(() => fetchReports(), 0);
    return () => clearTimeout(timer);
  }, [fetchReports]);
  useEffect(() => {
    if (activeProjectId && workspace.project) {
      setProjects([workspace.project]); setProjectId(activeProjectId);
      api.tasks.getByProject(activeProjectId).then((response: any) => setTasks(Array.isArray(response) ? response : response.data || [])).catch(() => setTasks([]));
    }
    else api.projects.list().then(r => { setProjects(r.data); if(r.data[0]) setProjectId(r.data[0].id); });
    api.field.context().then(context => { const ids = context.projects.filter(project => project.isSiteEngineer).map(project => project.id); setSiteProjectIds(ids); if (role === "engineer" && ids[0]) setProjectId(ids[0]); }).catch(() => setSiteProjectIds([]));
  }, [activeProjectId, role, workspace.project]);
  const canSubmit = role === "project_manager" || (role === "engineer" && siteProjectIds.length > 0);

  // Opening a site report from a scheduled visit prefills the report from that
  // visit instead of asking the engineer to retype what the platform knows.
  const siteVisitId = searchParams.get("siteVisitId");
  useEffect(() => {
    if (!siteVisitId) return;
    let cancelled = false;
    axios.get(`/site-visits/${siteVisitId}/report-prefill`).then(({ data }) => {
      if (cancelled) return;
      setPrefilledVisit({ id: siteVisitId, visitType: data.visitType, reportDate: data.reportDate });
      setProjectId((current) => data.projectId || current);
      setSummary((current) => current || data.summaryText || "");
      setFormOpen(true);
    }).catch(() => {
      toast.error("The linked site visit could not be loaded; start the report manually.");
    });
    return () => { cancelled = true; };
  }, [siteVisitId]);
  const saveReport = async (reviewStatus: "draft" | "submitted") => {
    setIsSaving(true);
    try {
      if (editingId) {
        await api.reports.update(editingId, { taskId: taskId || null, summaryText: summary, weatherConditions: weather || null, workersCount: workers ? Number(workers) : null, equipment: equipment || null, workCompleted: workCompleted || null, workInProgress: workInProgress || null, delays: delays || null, issuesSummary: issuesSummary || null, notes: notes || null, reviewStatus });
      } else {
        await api.reports.create({projectId:activeProjectId || projectId,reportType:"site_report",title:"Site report",content:summary,reportDate:new Date().toISOString().slice(0,10),weatherConditions:weather,workersCount:workers?Number(workers):undefined,photos,taskId:taskId||undefined,equipment:equipment||undefined,workCompleted:workCompleted||undefined,workInProgress:workInProgress||undefined,delays:delays||undefined,issuesSummary:issuesSummary||undefined,notes:notes||undefined,reviewStatus});
      }
      setFormOpen(false); setEditingId(""); setSummary(""); setPhotos([]); setTaskId(""); setEquipment(""); setWorkCompleted(""); setWorkInProgress(""); setDelays(""); setIssuesSummary(""); setNotes("");
      await fetchReports();
      toast.success(reviewStatus === "draft" ? t("siteReports.draft_saved") : t("siteReports.report_submitted"));
    } catch (err: any) {
      toast.error(errorMessage(err, t("siteReports.save_failed")));
    } finally {
      setIsSaving(false);
    }
  };
  const submitReport = (e: React.FormEvent) => { e.preventDefault(); saveReport("submitted"); };
  const editDraft = (report: SiteReport) => {
    setEditingId(report.id); setSummary(report.summaryText || ""); setWeather(report.weatherConditions || "");
    setWorkers(report.workersCount?.toString() || ""); setTaskId(report.taskId || ""); setEquipment(report.equipment || "");
    setWorkCompleted(report.workCompleted || ""); setWorkInProgress(report.workInProgress || ""); setDelays(report.delays || "");
    setIssuesSummary(report.issuesSummary || ""); setNotes(report.notes || ""); setPhotos([]); setFormOpen(true);
  };

  // Verification is a Manager-only backend action (`site_report.verify`); this
  // button only ever appears for a report already in the "submitted" state, but
  // the server re-validates the role, the project assignment and the state
  // transition regardless of what the UI shows.
  const verifyReport = async (report: SiteReport) => {
    setVerifyingId(report.id);
    try {
      await api.siteReports.review(report.id, { approved: true });
      await fetchReports();
      toast.success(t("siteReports.report_verified"));
    } catch (err: any) {
      toast.error(errorMessage(err, t("siteReports.review_failed")));
    } finally {
      setVerifyingId("");
    }
  };
  const submitRejection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectingReport || !rejectionReason.trim()) return;
    setVerifyingId(rejectingReport.id);
    try {
      await api.siteReports.review(rejectingReport.id, { approved: false, rejectionReason: rejectionReason.trim() });
      setRejectingReport(null); setRejectionReason("");
      await fetchReports();
      toast.success(t("siteReports.report_rejected"));
    } catch (err: any) {
      toast.error(errorMessage(err, t("siteReports.review_failed")));
    } finally {
      setVerifyingId("");
    }
  };

  if (isLoading) return <Loader fullPage />;
  const visibleReports = focusedReportId ? reports.filter((report) => report.id === focusedReportId) : reports;

  return (
    <div className="page-container space-y-6">
      <div className="flex items-center justify-between">
        <div>
        <h1 className="text-2xl font-bold">{t("siteReports.site_reports")}{workspace.project ? ` · ${workspace.project.name}` : ""}</h1>
        <p className="text-muted-foreground">{t("siteReports.daily_site_progress_reports")}</p>
        </div>{canSubmit && <Button onClick={() => setFormOpen(true)}>+ {t("siteReports.site_reports_singular")}</Button>}
      </div>
      {focusedReportId && <div className="flex items-center justify-between rounded-lg border bg-card p-3 text-sm"><span>{t("siteReports.showing_the_site_report_opened_from_your")}</span><Button size="sm" variant="ghost" onClick={() => setSearchParams({})}>{t("siteReports.show_all_reports")}</Button></div>}

      <Card className="grid gap-3 p-4 md:grid-cols-6">
        {activeProjectId ? <div className="flex items-center text-sm font-medium">{workspace.project?.name || t("project.selectedProject")}</div> : <Select value={filterProject} onChange={e=>setFilterProject(e.target.value)} options={[{value:"",label:t("project.allProjects")},...projects.map(project=>({value:project.id,label:project.name}))]}/>}
        <Select value={filterStatus} onChange={e=>setFilterStatus(e.target.value)} options={[{value:"",label:t("siteReports.all_statuses")},...['draft','submitted','approved','rejected'].map(value=>({value,label:vocabulary.reviewStatus(value)}))]}/>
        <Select value={filterDiscipline} onChange={e=>setFilterDiscipline(e.target.value)} options={[{value:"",label:t("siteReports.all_disciplines")},...['civil','architectural','electrical','mechanical'].map(value=>({value,label:vocabulary.discipline(value)}))]}/>
        <Input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}/>
        <Input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}/>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyAttachments} onChange={e=>setOnlyAttachments(e.target.checked)}/> {t("siteReports.has_attachments")}</label>
      </Card>

      {visibleReports.length === 0 ? (
        <Card>
          <div className="empty-state">
            <div className="empty-state-icon">🏗️</div>
            <p className="empty-state-title">{t("siteReports.no_site_reports")}</p>
          </div>
        </Card>
      ) : (
        <div className="space-y-2">
          {visibleReports.map((report) => (
            <Card key={report.id} className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">{formatDate(report.reportDate)}</p>
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {report.summaryText}
                  </p>
                  {report.weatherConditions && (
                    <Badge size="sm" className="mt-1">
                      {report.weatherConditions}
                    </Badge>
                  )}
                  {report.reviewStatus && <Badge size="sm" className="mt-1 ml-2" variant={report.reviewStatus === "approved" ? "success" : report.reviewStatus === "rejected" ? "danger" : "neutral"}>{vocabulary.reviewStatus(report.reviewStatus)}</Badge>}
                  {report.reviewStatus === "draft" && report.submittedById === user?.id && <Button className="ml-2" size="sm" variant="ghost" onClick={() => editDraft(report)}>{t("siteReports.edit_draft")}</Button>}
                  <AttachmentPanel projectId={report.projectId} entityType="SITE_REPORT" entityId={report.id} initialCount={report.attachmentCount} />
                  {/* Forward only: a site report is circulated for awareness,
                      while its formal review is the separate PM verification
                      action below — offering "Ask for Opinion" here would blur
                      the two. */}
                  <CommunicationActions className="mt-2" entityType="SITE_REPORT" entityId={report.id} projectId={report.projectId} intents={["forward"]} />

                  {/* Verification: server-enforced for the assigned Project
                      Manager only (site_report.verify); this UI merely hides
                      the action for everyone else — it is not the guard. */}
                  {role === "project_manager" && report.reviewStatus === "submitted" && (
                    <div className="mt-3 flex items-center gap-2 rounded-lg border bg-muted/20 p-3">
                      <span className="text-sm font-medium">{t("siteReports.verification_needed")}</span>
                      <Button size="sm" isLoading={verifyingId === report.id} onClick={() => verifyReport(report)}>{t("siteReports.verify")}</Button>
                      <Button size="sm" variant="outline" disabled={verifyingId === report.id} onClick={() => { setRejectingReport(report); setRejectionReason(""); }}>{t("siteReports.reject")}</Button>
                    </div>
                  )}
                  {report.reviewStatus === "rejected" && report.rejectionReason && (
                    <p className="mt-2 rounded-lg border border-state-overdue/30 bg-wash-overdue px-3 py-2 text-sm text-state-overdue">
                      <span className="font-medium">{t("siteReports.rejection_reason")}:</span> {report.rejectionReason}
                    </p>
                  )}
                  {(report.reviewStatus === "approved" || report.reviewStatus === "rejected") && report.reviewedBy && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t("siteReports.reviewed_by", { name: report.reviewedBy.fullName, date: report.reviewedAt ? formatDate(report.reviewedAt) : "" })}
                    </p>
                  )}
                </div>
                {report.progressPercentageReported !== undefined && report.progressPercentageReported !== null && <div className="text-right">
                  <p className="text-lg font-bold">
                    {report.progressPercentageReported}%
                  </p>
                  <p className="text-xs text-muted-foreground">{t("siteReports.progress")}</p>
                </div>}
              </div>
            </Card>
          ))}
        </div>
      )}
      <Modal isOpen={!!rejectingReport} onClose={() => setRejectingReport(null)} title={t("siteReports.reject_report_title")}>
        <form onSubmit={submitRejection} className="space-y-4">
          <p className="text-sm text-muted-foreground">{t("siteReports.reject_report_description")}</p>
          <Input label={t("siteReports.rejection_reason")} value={rejectionReason} onChange={e => setRejectionReason(e.target.value)} required />
          <ModalActions>
            <Button type="button" variant="outline" onClick={() => setRejectingReport(null)}>{t("siteReports.cancel")}</Button>
            <Button type="submit" isLoading={!!rejectingReport && verifyingId === rejectingReport.id} disabled={!rejectionReason.trim()}>{t("siteReports.reject")}</Button>
          </ModalActions>
        </form>
      </Modal>
      <Modal isOpen={formOpen} onClose={() => { setFormOpen(false); setEditingId(""); setPrefilledVisit(null); if (siteVisitId) { const next = new URLSearchParams(searchParams); next.delete("siteVisitId"); setSearchParams(next, { replace: true }); } }} title={editingId ? t("siteReports.edit_draft_title") : t("siteReports.create_title")}>
        <form onSubmit={submitReport} className="space-y-4">
          {prefilledVisit && <div className="rounded-lg border border-primary/40 bg-primary/5 p-3 text-sm"><p className="font-medium">{t("siteReports.prefilled_from_a_scheduled_site_visit")}</p><p className="mt-0.5 text-muted-foreground">{t("siteReports.visit_summary", { type: vocabulary.siteVisitType(prefilledVisit.visitType), date: prefilledVisit.reportDate })}</p></div>}
          {activeProjectId ? <p className="text-sm"><span className="text-muted-foreground">{t("siteReports.project")}</span> {workspace.project?.name}</p> : <Select label={t("siteReports.project_2")} value={projectId} onChange={e=>setProjectId(e.target.value)} options={projects.filter(project => role === "project_manager" || siteProjectIds.includes(project.id)).map(p=>({value:p.id,label:p.name}))}/>}
          <Input label={t("siteReports.work_summary")} value={summary} onChange={e=>setSummary(e.target.value)} required/>
          <Select label={t("siteReports.related_task_optional")} value={taskId} onChange={e=>setTaskId(e.target.value)} options={[{value:"",label:t("siteReports.general_daily_report")},...tasks.map(task=>({value:task.id,label:`${task.taskCode} — ${task.name}`}))]}/>
          <Input label={t("siteReports.weather")} value={weather} onChange={e=>setWeather(e.target.value)}/>
          <Input label={t("siteReports.workers_count")} type="number" min="0" value={workers} onChange={e=>setWorkers(e.target.value)}/>
          <Input label={t("siteReports.equipment")} value={equipment} onChange={e=>setEquipment(e.target.value)}/>
          <Input label={t("siteReports.work_completed")} value={workCompleted} onChange={e=>setWorkCompleted(e.target.value)}/>
          <Input label={t("siteReports.work_in_progress")} value={workInProgress} onChange={e=>setWorkInProgress(e.target.value)}/>
          <Input label={t("siteReports.delay_notes")} value={delays} onChange={e=>setDelays(e.target.value)}/>
          <Input label={t("siteReports.issue_references_summary")} value={issuesSummary} onChange={e=>setIssuesSummary(e.target.value)}/>
          <Input label={t("siteReports.additional_notes")} value={notes} onChange={e=>setNotes(e.target.value)}/>
          <label className="block text-sm font-medium">{t("siteReports.optional_photos")}<input className="mt-1 block w-full text-sm" type="file" accept="image/*,.pdf" multiple onChange={e=>setPhotos(Array.from(e.target.files || []))}/></label>
          <ModalActions><Button type="button" variant="outline" onClick={()=>setFormOpen(false)}>{t("siteReports.cancel")}</Button><Button type="button" variant="outline" isLoading={isSaving} disabled={!(activeProjectId || projectId)||!summary.trim()} onClick={()=>saveReport("draft")}>{t("siteReports.save_draft")}</Button><Button type="submit" isLoading={isSaving} disabled={!(activeProjectId || projectId)||!summary.trim()}>{t("siteReports.submit_report")}</Button></ModalActions>
        </form>
      </Modal>
    </div>
  );
};
