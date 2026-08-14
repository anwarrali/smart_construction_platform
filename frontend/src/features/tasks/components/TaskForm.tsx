import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { Button } from "../../../components/ui/Button";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import type { ProjectMember } from "../../../types/project";
import type { CreateTaskRequest, Task, TaskPriority, TaskStatus } from "../../../types/task";
import { inclusiveDurationDays } from "../../../utils/scheduleDates";
import { projectsService } from "../../projects/services/projects.service";
import { tasksService } from "../services/tasks.service";
import api from "../../../services/api";
import type { Milestone } from "../../../types/milestone";

interface TaskFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateTaskRequest) => Promise<void>;
  task?: Task | null;
  projectId?: string;
}

const CREATE_STATUSES = [
  { value: "backlog", label: "Backlog" },
  { value: "todo", label: "To Do" },
];

const EDIT_STATUSES = [
  ...CREATE_STATUSES,
  { value: "in_progress", label: "In Progress" },
  { value: "under_review", label: "Under Review (review workflow)", disabled: true },
  { value: "rework_required", label: "Rework Required (review workflow)", disabled: true },
  { value: "blocked", label: "Blocked" },
  { value: "done", label: "Done (review workflow)", disabled: true },
  { value: "cancelled", label: "Cancelled" },
];

const PRIORITIES = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

const titleCase = (value?: string) => value
  ? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
  : "—";

const affiliationLabel = (member: ProjectMember) =>
  member.user.organization
  || (member.user.role === "worker"
    ? "Field Worker"
    : member.user.engineerAffiliation === "external_consultant"
      ? "External Consultant"
      : member.user.engineerAffiliation === "main_contractor"
        ? "Main Contractor"
        : "Internal Engineer");

const memberLabel = (member: ProjectMember) => {
  const discipline = member.projectDiscipline || member.user.engineerProfile?.discipline;
  const responsibility = member.assignmentTitle ? ` · ${member.assignmentTitle}` : "";
  const site = member.isSiteEngineer ? " · Site Engineer" : "";
  return `${member.user.fullName} — ${titleCase(member.user.role)} · ${titleCase(discipline)} · ${affiliationLabel(member)}${responsibility}${site}`;
};

export const TaskForm = ({ isOpen, onClose, onSubmit, task, projectId }: TaskFormProps) => {
  const { t } = useTranslation();
  const activeProjectId = projectId || task?.projectId || "";
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<TaskStatus>("todo");
  const [priority, setPriority] = useState<TaskPriority>("medium");
  const [plannedStartDate, setPlannedStartDate] = useState("");
  const [plannedEndDate, setPlannedEndDate] = useState("");
  const [durationDays, setDurationDays] = useState("");
  const [discipline, setDiscipline] = useState("civil");
  const [assigneeIds, setAssigneeIds] = useState<string[]>([]);
  const [assigneeSearch, setAssigneeSearch] = useState("");
  const [dependencySearch, setDependencySearch] = useState("");
  const [dependencyIds, setDependencyIds] = useState<string[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [projectTasks, setProjectTasks] = useState<Task[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [milestoneId, setMilestoneId] = useState("");
  const [reviewRequired, setReviewRequired] = useState(true);
  const [reviewDueDate, setReviewDueDate] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    setName(task?.name || "");
    setDescription(task?.description || "");
    setStatus(task?.status || "todo");
    setPriority(task?.priority || "medium");
    setPlannedStartDate(task?.plannedStartDate?.split("T")[0] || "");
    setPlannedEndDate(task?.plannedEndDate?.split("T")[0] || "");
    setDurationDays(task?.durationDays?.toString() || "");
    setDiscipline(task?.discipline || "civil");
    setAssigneeIds(task?.assigneeIds || []);
    setDependencyIds(task?.dependencies?.map((dependency) => dependency.dependsOnTaskId) || []);
    setMilestoneId(task?.milestoneId || "");
    setReviewRequired(task?.reviewRequired ?? true);
    setReviewDueDate(task?.reviewDueDate?.split("T")[0] || "");
    setAssigneeSearch("");
    setDependencySearch("");
    setError("");
  }, [isOpen, task]);

  useEffect(() => {
    if (!plannedStartDate || !plannedEndDate) { setDurationDays(""); return; }
    const days = inclusiveDurationDays(plannedStartDate, plannedEndDate);
    setDurationDays(days === null ? "" : String(days));
  }, [plannedStartDate, plannedEndDate]);

  useEffect(() => {
    if (!isOpen || !activeProjectId) { setMembers([]); setProjectTasks([]); return; }
    Promise.all([
      projectsService.getMembers(activeProjectId),
      tasksService.getByProject(activeProjectId),
      api.milestones.list(activeProjectId),
    ]).then(([team, response, milestoneData]) => {
      setMembers(team);
      setMilestones(milestoneData);
      const tasks = Array.isArray(response) ? response : response.data || response.items || [];
      setProjectTasks(tasks.filter((candidate) => candidate.id !== task?.id));
    }).catch((err: any) => setError(errorMessage(err, "Unable to load project task options.")));
  }, [activeProjectId, isOpen, task?.id]);

  const eligibleMembers = useMemo(() => members.filter((member) => {
    if (!member.isActive || member.user.status !== "active") return false;
    if (!["engineer", "consultant", "project_manager", "worker"].includes(member.user.role)) return false;
    if (member.user.engineerAffiliation === "external_consultant" || member.roleOnProject === "consultant") return false;
    const haystack = memberLabel(member).toLowerCase();
    return !assigneeSearch.trim() || haystack.includes(assigneeSearch.trim().toLowerCase());
  }), [assigneeSearch, members]);

  const dependencyOptions = useMemo(() => projectTasks.filter((candidate) => {
    const haystack = `${candidate.taskCode} ${candidate.name} ${candidate.status}`.toLowerCase();
    return !dependencySearch.trim() || haystack.includes(dependencySearch.trim().toLowerCase());
  }), [dependencySearch, projectTasks]);

  const toggleDependency = (taskId: string) => setDependencyIds((current) =>
    current.includes(taskId) ? current.filter((value) => value !== taskId) : [...current, taskId]);

  const toggleAssignee = (userId: string) => setAssigneeIds((current) =>
    current.includes(userId) ? current.filter((value) => value !== userId) : [...current, userId]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    if (!activeProjectId) { setError("Open a project before creating a task."); return; }
    if (!name.trim()) { setError("Task name is required."); return; }
    if (plannedStartDate && plannedEndDate && plannedEndDate < plannedStartDate) {
      setError("End date must be on or after the start date."); return;
    }

    setIsLoading(true);
    try {
      await onSubmit({
        projectId: activeProjectId,
        name: name.trim(),
        description: description.trim() || undefined,
        status,
        priority,
        plannedStartDate: plannedStartDate || undefined,
        plannedEndDate: plannedEndDate || undefined,
        assigneeIds,
        discipline,
        dependencyIds,
        milestoneId: milestoneId || undefined,
        reviewRequired,
        reviewDueDate: reviewRequired && reviewDueDate ? reviewDueDate : undefined,
      });
      onClose();
    } catch (err: any) {
      setError(errorMessage(err, "Unable to save this task."));
    } finally { setIsLoading(false); }
  };

  return <Modal isOpen={isOpen} onClose={onClose} title={task ? `Edit ${task.taskCode}` : "Create Task"} size="xl">
    <form onSubmit={handleSubmit} className="space-y-5">
      {error && <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>}
      {!activeProjectId && <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">Open a project workspace to create a task. The project is taken automatically from that context.</div>}
      <div className="grid gap-4 md:grid-cols-2">
        <Input label={t("taskForm.task_name")} value={name} onChange={(event) => setName(event.target.value)} required />
        <Input label={t("taskForm.description")} value={description} onChange={(event) => setDescription(event.target.value)} />
        <Select label={t("taskForm.status")} options={task ? EDIT_STATUSES : CREATE_STATUSES} value={status} onChange={(event) => setStatus(event.target.value as TaskStatus)} />
        <Select label={t("taskForm.priority")} options={PRIORITIES} value={priority} onChange={(event) => setPriority(event.target.value as TaskPriority)} />
        <Select label={t("taskForm.discipline")} value={discipline} onChange={(event) => setDiscipline(event.target.value)} options={[
          { value: "civil", label: "Civil" }, { value: "architectural", label: "Architectural" },
          { value: "electrical", label: "Electrical" }, { value: "mechanical", label: "Mechanical" },
        ]} />
        <Select label={t("taskForm.milestone")} value={milestoneId} onChange={(event) => setMilestoneId(event.target.value)} options={[{ value: "", label: "No milestone" }, ...milestones.map((milestone) => ({ value: milestone.id, label: `${milestone.milestoneCode} — ${milestone.name}` }))]} />
      </div>

      <div className="rounded-lg border p-4">
        <div className="flex items-center justify-between gap-3"><h3 className="font-medium">{t("taskForm.assigned_team_members")}</h3><span className="rounded-full bg-muted px-2 py-1 text-xs font-medium">{assigneeIds.length ? `${assigneeIds.length} selected` : "Unassigned"}</span></div>
        <p className="mb-3 text-xs text-muted-foreground">Select one or multiple active project members. Leave every option unchecked to keep the task unassigned.</p>
        <Input label={t("taskForm.search_assignees")} value={assigneeSearch} onChange={(event) => setAssigneeSearch(event.target.value)} placeholder={t("taskForm.name_role_discipline_company")} />
        <div className="mt-3 max-h-52 space-y-2 overflow-y-auto rounded border p-2">
          {eligibleMembers.map((member) => <label key={member.userId} className="flex cursor-pointer items-start gap-3 rounded p-2 hover:bg-muted/50">
            <input type="checkbox" className="mt-1" checked={assigneeIds.includes(member.userId)} onChange={() => toggleAssignee(member.userId)} />
            <span className="min-w-0 text-sm"><span className="block font-medium">{member.user.fullName}</span><span className="block text-xs text-muted-foreground">{memberLabel(member).split(" — ")[1]}</span></span>
          </label>)}
          {!eligibleMembers.length && <p className="p-3 text-sm text-muted-foreground">{t("taskForm.no_eligible_active_project_members_match")}</p>}
        </div>
      </div>

      <div className="rounded-lg border p-4">
        <h3 className="font-medium">{t("taskForm.task_dependencies")} <span className="font-normal text-muted-foreground">(optional)</span></h3>
        <p className="mb-3 text-xs text-muted-foreground">{t("taskForm.select_zero_one_or_multiple_predecessor")}</p>
        {projectTasks.length ? <>
          <Input label={t("taskForm.search_dependencies")} value={dependencySearch} onChange={(event) => setDependencySearch(event.target.value)} placeholder={t("taskForm.task_code_name_or_status")} />
          <div className="mt-3 max-h-52 space-y-2 overflow-y-auto rounded border p-2">
            {dependencyOptions.map((candidate) => <label key={candidate.id} className="flex cursor-pointer items-start gap-3 rounded p-2 hover:bg-muted/50">
              <input type="checkbox" className="mt-1" checked={dependencyIds.includes(candidate.id)} onChange={() => toggleDependency(candidate.id)} />
              <span><span className="font-medium">{candidate.taskCode} — {candidate.name}</span><span className="block text-xs text-muted-foreground">{titleCase(candidate.status)}{candidate.plannedStartDate && candidate.plannedEndDate ? ` · ${candidate.plannedStartDate} to ${candidate.plannedEndDate}` : ""}</span></span>
            </label>)}
            {!dependencyOptions.length && <p className="p-3 text-sm text-muted-foreground">{t("taskForm.no_project_tasks_match_this_search")}</p>}
          </div>
        </> : <p className="rounded bg-muted/40 p-3 text-sm text-muted-foreground">No existing tasks are available as dependencies. You can create the first task without a predecessor.</p>}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Input label={t("taskForm.start_date")} type="date" value={plannedStartDate} onChange={(event) => setPlannedStartDate(event.target.value)} />
        <Input label={t("taskForm.end_date")} type="date" value={plannedEndDate} onChange={(event) => setPlannedEndDate(event.target.value)} />
        <Input label={t("taskForm.duration_days")} type="number" value={durationDays} readOnly helperText="Both dates are included; the backend recalculates this value." />
      </div>

      <div className="rounded-lg border p-4">
        <label className="flex cursor-pointer items-start gap-3">
          <input type="checkbox" className="mt-1" checked={reviewRequired} onChange={(event) => setReviewRequired(event.target.checked)} />
          <span><span className="block font-medium">{t("taskForm.consultant_review_required")}</span><span className="block text-xs text-muted-foreground">When enabled, 100% execution is submitted to the authorized discipline Consultant and dependent tasks remain gated until approval.</span></span>
        </label>
        {reviewRequired && <div className="mt-4 max-w-sm"><Input label={t("taskForm.review_due_date")} type="date" value={reviewDueDate} onChange={(event) => setReviewDueDate(event.target.value)} helperText="Optional supervision deadline; it does not change the execution end date." /></div>}
      </div>

      <ModalActions><Button variant="outline" onClick={onClose} type="button">{t("taskForm.cancel")}</Button><Button type="submit" isLoading={isLoading} disabled={!activeProjectId}>{task ? "Save Task" : "Create Task"}</Button></ModalActions>
    </form>
  </Modal>;
};
