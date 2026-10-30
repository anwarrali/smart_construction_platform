import { PageHeader } from "../../../components/ui/PageHeader";
import { Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useVocabulary } from "../../../utils/vocabulary";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { useParams } from "react-router-dom";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import api from "../../../services/api";
import type { Milestone } from "../../../types/milestone";
import type { Task } from "../../../types/task";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import { useRole } from "../../../hooks/useRole";


export const MilestonesPage = () => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const { projectId, id } = useParams<{ projectId?: string; id?: string }>();
  const workspace = useProjectWorkspace();
  // Writing a milestone is a schedule change, which is what the server now
  // requires. The page is reachable on `schedule.view`, so without this the
  // Add/Edit/Delete controls render for a consultant or the client and fail
  // with a 403 when pressed.
  const { hasCapability } = useRole();
  const canEditSchedule = hasCapability("schedule.edit");
  const activeProjectId = projectId || id || workspace.projectId;
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [editing, setEditing] = useState<Milestone | null>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [plannedDate, setPlannedDate] = useState("");
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!activeProjectId) return;
    setLoading(true);
    try {
      const [milestoneData, taskResponse] = await Promise.all([
        api.milestones.list(activeProjectId), api.tasks.getByProject(activeProjectId),
      ]);
      setMilestones(milestoneData);
      setTasks(Array.isArray(taskResponse) ? taskResponse : taskResponse.data || taskResponse.items || []);
      setError("");
    } catch (err: any) {
      setError(errorMessage(err, "Unable to load project milestones."));
    } finally { setLoading(false); }
  }, [activeProjectId]);

  useEffect(() => { load(); }, [load]);

  const openForm = (milestone?: Milestone) => {
    setEditing(milestone || null);
    setName(milestone?.name || "");
    setDescription(milestone?.description || "");
    setPlannedDate(milestone?.plannedDate || "");
    setTaskIds(milestone?.taskIds || []);
    setOpen(true);
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!activeProjectId || !name.trim() || !plannedDate) return;
    setSaving(true);
    try {
      const payload = { projectId: activeProjectId, name: name.trim(), description: description.trim() || undefined, plannedDate, taskIds };
      if (editing) await api.milestones.update(editing.id, payload);
      else await api.milestones.create(payload);
      toast.success(editing ? "Milestone updated." : "Milestone created.");
      setOpen(false);
      await load();
    } catch (err: any) {
      toast.error(errorMessage(err, "Unable to save milestone."));
    } finally { setSaving(false); }
  };

  const linkedNames = useMemo(() => new Map(tasks.map((task) => [task.id, `${task.taskCode} — ${task.name}`])), [tasks]);

  if (!activeProjectId) return <Card><p className="text-sm text-muted-foreground">{t("milestonesPage.open_a_project_to_manage_milestones")}</p></Card>;
  return <div className="page-container space-y-6">
    <PageHeader
      title={t("milestonesPage.project_milestones")}
      description={t("milestonesPage.link_scheduled_work_to_measurable")}
      actions={canEditSchedule && <Button leftIcon={<Plus size={15} />} onClick={() => openForm()}>{t("milestonesPage.add_milestone")}</Button>}
    />
    {error && <Card><p className="text-sm text-destructive">{error}</p></Card>}
    {loading ? <p className="text-sm text-muted-foreground">{t("milestonesPage.loading_milestones")}</p> : <div className="grid gap-4 lg:grid-cols-2">
      {milestones.map((milestone) => <Card key={milestone.id} className="space-y-4">
        <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold text-primary">{milestone.milestoneCode}</p><h2 className="font-semibold">{milestone.name}</h2><p className="text-sm text-muted-foreground">Due {milestone.plannedDate}</p></div><Badge variant={milestone.status === "completed" ? "success" : milestone.status === "delayed" ? "danger" : "warning"}>{vocabulary.milestoneStatus(milestone.status)}</Badge></div>
        {milestone.description && <p className="text-sm text-muted-foreground">{milestone.description}</p>}
        <div><div className="mb-1 flex justify-between text-xs"><span>{milestone.completedTaskCount}/{milestone.taskCount} tasks completed</span><span>{milestone.progressPercentage}%</span></div><div className="gauge gauge-ticked"><div className="gauge-fill" style={{ width: `${milestone.progressPercentage}%` }} /></div></div>
        <div className="flex flex-wrap gap-1">{milestone.taskIds.map((taskId) => <span key={taskId} className="border bg-well px-1.5 py-0.5 text-xs">{linkedNames.get(taskId) || "Linked task"}</span>)}{!milestone.taskIds.length && <span className="text-xs text-muted-foreground">{t("milestonesPage.no_tasks_linked_yet")}</span>}</div>
        {canEditSchedule && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => openForm(milestone)}>{t("milestonesPage.edit")}</Button><Button size="sm" variant="destructive" onClick={async () => { if (!window.confirm(`Delete ${milestone.milestoneCode}? Linked tasks will be preserved.`)) return; await api.milestones.delete(milestone.id); toast.success("Milestone deleted."); load(); }}>{t("milestonesPage.delete")}</Button></div>}
      </Card>)}
      {!milestones.length && <Card><p className="text-sm text-muted-foreground">{t("milestonesPage.no_milestones_have_been_created_for_this")}</p></Card>}
    </div>}
    <Modal isOpen={open} onClose={() => setOpen(false)} title={editing ? `Edit ${editing.milestoneCode}` : "Create Milestone"} size="xl">
      <form className="space-y-4" onSubmit={save}>
        <div className="grid gap-4 sm:grid-cols-2"><Input label={t("milestonesPage.milestone_name")} value={name} onChange={(event) => setName(event.target.value)} required /><Input label={t("milestonesPage.planned_date")} type="date" value={plannedDate} onChange={(event) => setPlannedDate(event.target.value)} required /></div>
        <Input label={t("milestonesPage.description")} value={description} onChange={(event) => setDescription(event.target.value)} />
        <div><p className="mb-1 text-sm font-medium">{t("milestonesPage.linked_tasks")}</p><p className="mb-3 text-xs text-muted-foreground">{t("milestonesPage.progress_is_calculated_automatically")}</p><div className="max-h-72 space-y-2 overflow-y-auto rounded border p-2">{tasks.map((task) => <label key={task.id} className="flex cursor-pointer gap-3 rounded p-2 hover:bg-muted/50"><input type="checkbox" checked={taskIds.includes(task.id)} onChange={() => setTaskIds((current) => current.includes(task.id) ? current.filter((value) => value !== task.id) : [...current, task.id])} /><span className="text-sm"><span className="font-medium">{task.taskCode} — {task.name}</span><span className="block text-xs text-muted-foreground">{task.status.replaceAll("_", " ")} · {task.progressPercentage}%</span></span></label>)}</div></div>
        <ModalActions><Button type="button" variant="outline" onClick={() => setOpen(false)}>{t("milestonesPage.cancel")}</Button><Button type="submit" isLoading={saving} disabled={!name.trim() || !plannedDate}>{t("milestonesPage.save_milestone")}</Button></ModalActions>
      </form>
    </Modal>
  </div>;
};
