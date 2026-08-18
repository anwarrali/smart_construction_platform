import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { Loader } from "../../../components/ui/Loader";
import { designChangesService } from "../services/designChanges.service";
import { formatDate } from "../../../utils/date";
import type { DesignChange } from "../../../types/designChange";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import api from "../../../services/api";
import { useRole } from "../../../hooks/useRole";
import { AttachmentPanel } from "../../../components/shared/AttachmentPanel";
import { CommunicationActions } from "../../../components/shared/CommunicationActions";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import { useSearchParams } from "react-router-dom";
import { useVocabulary } from "../../../utils/vocabulary";

export const DesignChangesPage = () => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const workspace = useProjectWorkspace();
  const activeProjectId = workspace.projectId;
  const [changes, setChanges] = useState<DesignChange[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const isFirstRender = useRef(true);
  const { role } = useRole();
  const [formOpen, setFormOpen] = useState(false);
  const [projects, setProjects] = useState<{id:string;name:string}[]>([]);
  const [projectId, setProjectId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [discipline, setDiscipline] = useState("civil");
  const [reason, setReason] = useState("");
  const [costImpact, setCostImpact] = useState("");
  const [scheduleImpact, setScheduleImpact] = useState("");
  const [filterProject, setFilterProject] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterDiscipline, setFilterDiscipline] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [onlyAttachments, setOnlyAttachments] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const focusedChangeId = searchParams.get("changeId");

  const fetchChanges = useCallback(async () => {
    setIsLoading(true);
    const response = await designChangesService.getByProject(activeProjectId || filterProject || undefined, {
      status: filterStatus || undefined, discipline: filterDiscipline || undefined,
      dateFrom: dateFrom || undefined, dateTo: dateTo || undefined,
      hasAttachments: onlyAttachments ? true : undefined,
    });
    setChanges(response.data || []);
    setIsLoading(false);
  }, [activeProjectId, filterProject, filterStatus, filterDiscipline, dateFrom, dateTo, onlyAttachments]);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      fetchChanges();
      return;
    }
    const timer = setTimeout(() => fetchChanges(), 0);
    return () => clearTimeout(timer);
  }, [fetchChanges]);
  useEffect(() => {
    if (activeProjectId && workspace.project) { setProjects([workspace.project]); setProjectId(activeProjectId); return; }
    api.projects.list().then(r => { setProjects(r.data); if(r.data[0]) setProjectId(r.data[0].id); });
  }, [activeProjectId, workspace.project]);
  const canPropose = role === "project_manager" || role === "engineer";
  const createChange = async (e: React.FormEvent) => { e.preventDefault(); await designChangesService.create({projectId:activeProjectId || projectId,title,description,reason,sourceDiscipline:discipline,affectedDisciplines:[discipline],expectedCostImpact:costImpact?Number(costImpact):undefined,expectedScheduleImpactDays:scheduleImpact?Number(scheduleImpact):undefined}); setFormOpen(false); setTitle(""); setDescription(""); fetchChanges(); };

  if (isLoading) return <Loader fullPage />;

  const statusVariant: Record<
    string,
    "warning" | "info" | "success" | "danger" | "neutral"
  > = {
    proposed: "warning",
    under_review: "info",
    approved: "success",
    rejected: "danger",
    implemented: "neutral",
  };
  const visibleChanges = focusedChangeId ? changes.filter((change) => change.id === focusedChangeId) : changes;

  return (
    <div className="page-container space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Design Changes{workspace.project ? ` · ${workspace.project.name}` : ""}</h1>
          <p className="text-muted-foreground">{t("designChanges.engineering_change_requests")}</p>
        </div>
        {canPropose && <Button onClick={() => setFormOpen(true)}>+ Propose Change</Button>}
      </div>
      {focusedChangeId && <div className="flex items-center justify-between rounded-lg border bg-card p-3 text-sm"><span>{t("designChanges.showing_the_design_change_opened_from")}</span><Button size="sm" variant="ghost" onClick={() => setSearchParams({})}>{t("designChanges.show_all_changes")}</Button></div>}

      <Card className="grid gap-3 p-4 md:grid-cols-6">
        {activeProjectId ? <div className="flex items-center text-sm font-medium">{workspace.project?.name || t("project.selectedProject")}</div> : <Select value={filterProject} onChange={e=>setFilterProject(e.target.value)} options={[{value:"",label:t("project.allProjects")},...projects.map(project=>({value:project.id,label:project.name}))]}/>}
        <Select value={filterStatus} onChange={e=>setFilterStatus(e.target.value)} options={[{value:"",label:t("designChanges.all_statuses")},...['proposed','under_review','approved','rejected','implemented'].map(value=>({value,label:vocabulary.designChangeStatus(value)}))]}/>
        <Select value={filterDiscipline} onChange={e=>setFilterDiscipline(e.target.value)} options={[{value:"",label:t("designChanges.all_disciplines")},...['civil','architectural','electrical','mechanical'].map(value=>({value,label:vocabulary.discipline(value)}))]}/>
        <Input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}/>
        <Input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}/>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyAttachments} onChange={e=>setOnlyAttachments(e.target.checked)}/> {t("designChanges.has_attachments")}</label>
      </Card>

      {visibleChanges.length === 0 ? (
        <Card>
          <div className="empty-state">
            <div className="empty-state-icon">📐</div>
            <p className="empty-state-title">{t("designChanges.no_design_changes")}</p>
          </div>
        </Card>
      ) : (
        <div className="space-y-2">
          {visibleChanges.map((change) => (
            <Card key={change.id} className="p-4">
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-medium">{change.title}</p>
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {change.description}
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <Badge size="sm">{vocabulary.discipline(change.sourceDiscipline)}</Badge>
                    <Badge size="sm" variant={statusVariant[change.status]}>
                      {vocabulary.designChangeStatus(change.status)}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {formatDate(change.createdAt)}
                    </span>
                  </div>
                  <AttachmentPanel projectId={change.projectId} entityType="DESIGN_CHANGE" entityId={change.id} initialCount={change.attachmentCount} />
                  {/* Consultation only — the formal approve/reject decision
                      stays with the assigned consultant engineer (right). */}
                  <CommunicationActions className="mt-2" entityType="DESIGN_CHANGE" entityId={change.id} projectId={change.projectId} />
                </div>
                {change.affectedDisciplines.length > 0 && (
                  <div className="text-xs text-muted-foreground">
                    {t("designChanges.affected_count", { count: change.affectedDisciplines.length })}
                  </div>
                )}
                {role === "consultant" && ["proposed","under_review"].includes(change.status) && <div className="flex gap-2 ml-3"><Button size="sm" onClick={async()=>{await api.designChanges.approve(change.id);fetchChanges();}}>{t("designChanges.approve")}</Button><Button size="sm" variant="destructive" onClick={async()=>{await api.designChanges.reject(change.id,t("designChanges.quick_reject_reason"));fetchChanges();}}>{t("designChanges.reject")}</Button></div>}
              </div>
            </Card>
          ))}
        </div>
      )}
      <Modal isOpen={formOpen} onClose={() => setFormOpen(false)} title={t("designChanges.propose_design_change")}>
        <form onSubmit={createChange} className="space-y-4">
          {activeProjectId ? <p className="text-sm"><span className="text-muted-foreground">{t("designChanges.project")}</span> {workspace.project?.name}</p> : <Select label={t("designChanges.project_2")} value={projectId} onChange={e => setProjectId(e.target.value)} options={projects.map(p=>({value:p.id,label:p.name}))}/>} 
          <Input label={t("designChanges.title")} value={title} onChange={e=>setTitle(e.target.value)} required/>
          <Input label={t("designChanges.description")} value={description} onChange={e=>setDescription(e.target.value)}/>
          <Input label={t("designChanges.reason")} value={reason} onChange={e=>setReason(e.target.value)}/>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2"><Input label={t("designChanges.expected_cost_impact")} type="number" value={costImpact} onChange={e=>setCostImpact(e.target.value)}/><Input label={t("designChanges.schedule_impact_days")} type="number" value={scheduleImpact} onChange={e=>setScheduleImpact(e.target.value)}/></div>
          <Select label={t("designChanges.source_discipline")} value={discipline} onChange={e=>setDiscipline(e.target.value)} options={["civil","architectural","electrical","mechanical"].map(value=>({value,label:vocabulary.discipline(value)}))}/>
          <ModalActions><Button type="button" variant="outline" onClick={()=>setFormOpen(false)}>{t("designChanges.cancel")}</Button><Button type="submit" disabled={!(activeProjectId || projectId)||!title.trim()}>{t("designChanges.submit_change")}</Button></ModalActions>
        </form>
      </Modal>
    </div>
  );
};
