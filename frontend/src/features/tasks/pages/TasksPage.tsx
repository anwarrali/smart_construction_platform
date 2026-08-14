import { useState, useEffect, useCallback, useRef } from "react";
import i18n from "../../../i18n";
import { useVocabulary } from "../../../utils/vocabulary";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { TaskBoard } from "../components/TaskBoard";
import { TaskForm } from "../components/TaskForm";
import { tasksService } from "../services/tasks.service";
import { useDebounce } from "../../../hooks/useDebounce";
import { useRole } from "../../../hooks/useRole";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import toast from "react-hot-toast";
import { Badge } from "../../../components/ui/Badge";
import { useNavigate } from "react-router-dom";
import type {
  Task,
  CreateTaskRequest,
  TaskFilters,
  TaskStatus,
  TaskPriority,
} from "../../../types/task";

const EngineerTasksPage = () => {
  const { t } = useTranslation();
  const workspace = useProjectWorkspace();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [overdueOnly, setOverdueOnly] = useState(false);

  const load = useCallback(async () => {
    if (!workspace.projectId) {
      setError("Select an assigned project before opening My Tasks.");
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const response = await tasksService.getByProject(workspace.projectId);
      setTasks(Array.isArray(response) ? response : response.data || response.items || []);
    } catch (err: any) {
      setTasks([]);
      setError(errorMessage(err, "Unable to load your assigned tasks."));
    } finally {
      setIsLoading(false);
    }
  }, [workspace.projectId]);

  useEffect(() => { load(); }, [load]);

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const filtered = tasks.filter((task) => {
    const query = search.trim().toLowerCase();
    const matchesSearch = !query || [task.name, task.taskCode, task.description]
      .filter(Boolean).some((value) => String(value).toLowerCase().includes(query));
    const due = task.plannedEndDate ? new Date(`${task.plannedEndDate}T00:00:00`) : null;
    return matchesSearch
      && (!status || task.status === status)
      && (!priority || task.priority === priority)
      && (!discipline || task.discipline === discipline)
      && (!dueDate || task.plannedEndDate === dueDate)
      && (!criticalOnly || task.isCriticalPath)
      && (!overdueOnly || Boolean(due && due < today && !["done", "cancelled"].includes(task.status)));
  });

  const timing = (task: Task) => {
    if (!task.plannedEndDate) return "No due date";
    const due = new Date(`${task.plannedEndDate}T00:00:00`);
    const days = Math.round((due.getTime() - today.getTime()) / 86400000);
    if (days < 0 && !["done", "cancelled"].includes(task.status)) return `${Math.abs(days)} days overdue`;
    if (days === 0) return i18n.t("tasksPage.due_today");
    return `${days} days remaining`;
  };

  return <div className="page-container space-y-6">
    <div><h1 className="text-2xl font-bold">{t("tasksPage.my_tasks")}{workspace.project ? ` · ${workspace.project.name}` : ""}</h1><p className="text-muted-foreground">{t("tasksPage.only_work_assigned_to_you_in_the")}</p></div>
    <Card className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-4">
      <Input placeholder={t("tasksPage.search_title_id_or_description")} value={search} onChange={(event) => setSearch(event.target.value)} />
      <Select value={status} onChange={(event) => setStatus(event.target.value)} options={[{ value: "", label: "All statuses" }, ...["backlog", "todo", "in_progress", "under_review", "rework_required", "blocked", "done", "cancelled"].map((value) => ({ value, label: value.replaceAll("_", " ") }))]} />
      <Select value={priority} onChange={(event) => setPriority(event.target.value)} options={[{ value: "", label: "All priorities" }, ...["low", "medium", "high", "critical"].map((value) => ({ value, label: value }))]} />
      <Select value={discipline} onChange={(event) => setDiscipline(event.target.value)} options={[{ value: "", label: "All disciplines" }, ...["civil", "architectural", "electrical", "mechanical"].map((value) => ({ value, label: value }))]} />
      <Input label={t("tasksPage.due_date")} type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={criticalOnly} onChange={(event) => setCriticalOnly(event.target.checked)} /> Critical only</label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={overdueOnly} onChange={(event) => setOverdueOnly(event.target.checked)} /> Overdue only</label>
    </Card>
    {error && <Card className="border-destructive/30 p-4 text-destructive">{error}</Card>}
    {isLoading ? <Card className="p-8 text-center text-muted-foreground">{t("tasksPage.loading_assigned_tasks")}</Card> : !filtered.length ? <Card className="p-10 text-center"><p className="font-medium">{t("tasksPage.no_tasks_assigned")}</p><p className="mt-1 text-sm text-muted-foreground">{t("tasksPage.no_authorized_tasks_match_the_selected")}</p></Card> : <div className="grid gap-4 lg:grid-cols-2">
      {filtered.map((task) => <Card key={task.id} isHoverable className="cursor-pointer p-4" onClick={() => navigate(workspace.path(`tasks/${task.id}`))}>
        <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="font-mono text-xs font-semibold text-primary">{task.taskCode}</p><h2 className="truncate font-semibold">{task.name}</h2><p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{task.description || "No description"}</p></div><Badge variant={task.priority === "critical" || task.priority === "high" ? "danger" : task.priority === "medium" ? "warning" : "neutral"}>{task.priority}</Badge></div>
        <div className="mt-4 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4"><div><p className="text-muted-foreground">{t("tasksPage.status")}</p><p className="font-medium capitalize">{task.status.replaceAll("_", " ")}</p></div><div><p className="text-muted-foreground">{t("tasksPage.discipline")}</p><p className="font-medium capitalize">{task.discipline || "General"}</p></div><div><p className="text-muted-foreground">{t("tasksPage.progress")}</p><p className="font-medium">{task.progressPercentage}%</p></div><div><p className="text-muted-foreground">{t("tasksPage.timing")}</p><p className={timing(task).includes("overdue") ? "font-medium text-destructive" : "font-medium"}>{timing(task)}</p></div></div>
        <div className="mt-4 flex flex-wrap gap-2 border-t pt-3 text-xs text-muted-foreground"><span>Start: {task.plannedStartDate || "—"}</span><span>Due: {task.plannedEndDate || "—"}</span><span>Assigned by: {task.createdBy?.fullName || "Project Manager"}</span><span>Dependencies: {task.dependencies?.length || 0}</span>{task.isCriticalPath && <Badge size="sm" variant="danger">{t("tasksPage.critical_path")}</Badge>}{task.status === "blocked" && <Badge size="sm" variant="danger">{t("tasksPage.blocked")}</Badge>}{task.reviewStatus && <Badge size="sm" variant="warning">Review: {task.reviewStatus}</Badge>}</div>
      </Card>)}
    </div>}
  </div>;
};

const ManagedTasksPage = () => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const debouncedSearch = useDebounce(search);
  const { checkPermission, isProjectManager } = useRole();
  const workspace = useProjectWorkspace();
  const activeProjectId = workspace.projectId;
  const canCreate = checkPermission("create_task");
  const isFirstRender = useRef(true);

  const fetchTasks = useCallback(async () => {
    setIsLoading(true);
    const filters: TaskFilters = {
      search: debouncedSearch || undefined,
      status: (statusFilter as TaskStatus) || undefined,
      priority: (priorityFilter as TaskPriority) || undefined,
    };
    try {
      const response = activeProjectId
        ? await tasksService.getByProject(activeProjectId, filters)
        : await tasksService.list(filters);
      setTasks(Array.isArray(response) ? response : response.data || response.items || []);
    } catch (err: any) {
      setTasks([]);
      toast.error(errorMessage(err, "Unable to load tasks."));
    } finally { setIsLoading(false); }
  }, [activeProjectId, debouncedSearch, statusFilter, priorityFilter]);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      fetchTasks();
      return;
    }

    const timer = setTimeout(() => {
      fetchTasks();
    }, 0);

    return () => clearTimeout(timer);
  }, [fetchTasks]);

  const handleCreate = async (data: CreateTaskRequest) => {
    const payload = activeProjectId ? { ...data, projectId: activeProjectId } : data;
    const created = await tasksService.create(payload);
    await fetchTasks();
    toast.success(`${created.taskCode} created.`);
  };

  const handleSave = async (data: CreateTaskRequest) => {
    if (!editingTask) return handleCreate(data);
    const updated = await tasksService.update(editingTask.id, {
      name: data.name, description: data.description, discipline: data.discipline,
      status: data.status, priority: data.priority, assigneeIds: data.assigneeIds,
      plannedStartDate: data.plannedStartDate, plannedEndDate: data.plannedEndDate,
      dependencyIds: data.dependencyIds,
      milestoneId: data.milestoneId || null,
      reviewRequired: data.reviewRequired,
      reviewDueDate: data.reviewRequired ? (data.reviewDueDate || null) : null,
    });
    setEditingTask(null);
    await fetchTasks();
    toast.success(`${updated.taskCode} updated.`);
  };

  const handleDelete = async (task: Task) => {
    if (!window.confirm(`Delete task "${task.name}"?`)) return;
    try { await tasksService.delete(task.id); await fetchTasks(); toast.success("Task deleted."); }
    catch (err: any) { toast.error(errorMessage(err, "Unable to delete task.")); }
  };

  return (
    <div className="page-container space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("nav.tasks")}{workspace.project ? ` · ${workspace.project.name}` : ""}</h1>
          <p className="text-muted-foreground">
            {t("tasksPage.manage_and_track_project_tasks")}
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => { setEditingTask(null); setIsFormOpen(true); }}>+ {t("tasksPage.new_task")}</Button>
        )}
      </div>

      <Card>
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="flex-1">
            <Input
              placeholder={t("tasksPage.search_tasks")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Select
            options={[
              { value: "", label: t("tasksPage.all_statuses") },
              ...["backlog", "todo", "in_progress", "under_review", "rework_required", "done"]
                .map((value) => ({ value, label: vocabulary.taskStatus(value) })),
            ]}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full sm:w-44"
          />
          <Select
            options={[
              { value: "", label: t("tasksPage.all_priorities") },
              ...["low", "medium", "high", "critical"]
                .map((value) => ({ value, label: vocabulary.priority(value) })),
            ]}
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="w-full sm:w-44"
          />
        </div>

        <TaskBoard tasks={tasks} isLoading={isLoading} onEdit={isProjectManager ? (task) => { setEditingTask(task); setIsFormOpen(true); } : undefined} onDelete={isProjectManager ? handleDelete : undefined} />
      </Card>

      <TaskForm
        isOpen={isFormOpen}
        onClose={() => { setIsFormOpen(false); setEditingTask(null); }}
        onSubmit={handleSave}
        task={editingTask}
        projectId={activeProjectId}
      />
    </div>
  );
};

export const TasksPage = () => {
  const { isEngineer } = useRole();
  return isEngineer ? <EngineerTasksPage /> : <ManagedTasksPage />;
};
