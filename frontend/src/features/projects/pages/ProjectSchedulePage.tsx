import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Gantt, ViewMode } from "gantt-task-react";
import type { Task } from "gantt-task-react";
import "gantt-task-react/dist/index.css";
import api from "../../../services/api";
import { ArrowLeft, RefreshCw, AlertTriangle, Link2, Route } from "lucide-react";
import toast from "react-hot-toast";
import { useProjectWorkspace } from "../context/ProjectWorkspaceContext";
import { apiDateToLocalDate, ganttBoundaryToInclusiveEnd, inclusiveEndToGanttBoundary } from "../../../utils/scheduleDates";

interface ScheduleTask {
  id: string;
  task_code: string;
  name: string;
  start?: string;
  end?: string;
  progress: number;
  type: "task" | "milestone";
  dependencies: string[];
  is_critical: boolean;
  status: string;
  priority: string;
  duration_days?: number;
  total_float_days?: number | null;
  is_disabled?: boolean;
}

interface CriticalTask {
  taskId: string;
  taskCode: string;
  name: string;
  durationDays: number;
  earliestStart: number;
  earliestFinish: number;
  latestStart: number;
  latestFinish: number;
  totalFloatDays: number;
  drivingPredecessorId?: string | null;
  drivingDependencyType?: string | null;
  drivingLagDays: number;
}

interface CriticalPathResult {
  projectDurationDays: number;
  criticalTaskCount: number;
  criticalTaskIds: string[];
  criticalTasks: CriticalTask[];
  dependencyCount: number;
  calculationMethod: "CPM_DEPENDENCY_NETWORK";
  reason?: string | null;
}

export const ProjectSchedulePage = () => {
  const { id, projectId } = useParams<{ id?: string; projectId?: string }>();
  const workspace = useProjectWorkspace();
  const activeProjectId = projectId || id || workspace.projectId;
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>(ViewMode.Day);
  const [criticalPath, setCriticalPath] = useState<CriticalPathResult | null>(null);
  const [scheduleTasks, setScheduleTasks] = useState<ScheduleTask[]>([]);
  const [unscheduledTasks, setUnscheduledTasks] = useState<ScheduleTask[]>([]);
  const [savingTaskId, setSavingTaskId] = useState<string | null>(null);

  const toApiDate = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

  const taskColor = (task: ScheduleTask, criticalIds?: Set<string>) => {
    // Critical must win over status colours so every activity in the returned
    // ordered CPM sequence is visibly highlighted.
    if (criticalIds?.has(task.id) || task.is_critical) return "#dc2626";
    if (task.status.toLowerCase() === "done") return "#16a34a";
    if (task.end && new Date(task.end) < new Date(new Date().toDateString())) return "#f59e0b";
    return "#2563eb";
  };

  const highlightCriticalPath = (criticalTaskIds: string[]) => {
    const criticalIds = new Set(criticalTaskIds);
    setTasks((current) => current.map((task) => {
      const source = scheduleTasks.find((item) => item.id === task.id);
      if (!source) return task;
      const color = taskColor(source, criticalIds);
      return { ...task, styles: { backgroundColor: color, backgroundSelectedColor: color, progressColor: color, progressSelectedColor: color } };
    }));
  };

  const fetchSchedule = async () => {
    if (!activeProjectId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.scheduling.getGanttData(activeProjectId);
      if (data && data.tasks && data.tasks.length > 0) {
        const sourceTasks = data.tasks as ScheduleTask[];
        setScheduleTasks(sourceTasks);
        setUnscheduledTasks(sourceTasks.filter((task) => !task.start || !task.end));
        const formattedTasks: Task[] = sourceTasks.filter((task) => task.start && task.end).map((t) => {
          const color = taskColor(t);
          return ({
          start: apiDateToLocalDate(t.start!),
          end: t.type === "milestone" ? apiDateToLocalDate(t.end!) : inclusiveEndToGanttBoundary(t.end!),
          name: `${t.task_code} — ${t.name}`,
          id: t.id,
          type: t.type === "milestone" ? "milestone" : "task",
          progress: t.progress,
          isDisabled: Boolean(t.is_disabled),
          styles: { backgroundColor: color, backgroundSelectedColor: color, progressColor: color, progressSelectedColor: color },
          dependencies: t.dependencies,
        });});
        setTasks(formattedTasks);
      } else {
        setTasks([]);
        setScheduleTasks([]);
        setUnscheduledTasks([]);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load schedule.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSchedule();
  }, [activeProjectId]);

  const handleTaskChange = async (task: Task): Promise<boolean> => {
    const previousTasks = tasks.map((item) => ({ ...item, start: new Date(item.start), end: new Date(item.end) }));
    try {
      if (!activeProjectId) return false;
      const original = tasks.find((item) => item.id === task.id);
      if (!original) return false;
      setSavingTaskId(task.id);
      await api.tasks.update(task.id, {
        plannedStartDate: toApiDate(task.start),
        plannedEndDate: ganttBoundaryToInclusiveEnd(task.end),
      });
      setCriticalPath(null);
      setTasks((current) => current.map((item) => item.id === task.id ? { ...task } : item));
      toast.success("Schedule dates saved.");
      return true;
    } catch (e: any) {
      setTasks(previousTasks);
      toast.error(e?.response?.data?.detail || "Schedule update failed. The Gantt change was reverted.");
      return false;
    } finally { setSavingTaskId(null); }
  };

  const handleProgressChange = async (task: Task): Promise<boolean> => {
    const previousTasks = tasks.map((item) => ({ ...item, start: new Date(item.start), end: new Date(item.end) }));
    try {
      if (task.type === "milestone") return false;
      setSavingTaskId(task.id);
      await api.tasks.updateProgress(task.id, task.progress);
      setTasks((current) => current.map((item) => item.id === task.id ? { ...task } : item));
      toast.success("Task progress saved.");
      return true;
    } catch (e: any) {
      setTasks(previousTasks);
      toast.error(e?.response?.data?.detail || "Progress update failed. The Gantt change was reverted.");
      return false;
    } finally { setSavingTaskId(null); }
  };

  const handleCriticalPath = async () => {
    if (!activeProjectId) return;
    try {
      const result = await api.scheduling.getCriticalPath(activeProjectId);
      setCriticalPath(result);
      highlightCriticalPath(result.criticalTaskIds || []);
      if (result.criticalTaskIds?.length) toast.success("Dependency-based CPM path calculated.");
      else toast.error(result.reason || "No dependency-driven critical path exists.");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Critical path calculation failed.");
    }
  };

  const taskName = (taskId: string) => {
    const task = scheduleTasks.find((item) => item.id === taskId);
    return task ? `${task.task_code} — ${task.name}` : "Unknown task";
  };
  const criticalEdgeKeys = new Set(
    (criticalPath?.criticalTaskIds || []).slice(1).map((taskId, index) => `${criticalPath!.criticalTaskIds[index]}:${taskId}`)
  );
  const dependencyEdges = scheduleTasks.flatMap((task) => task.dependencies.map((predecessorId) => ({
    predecessorId,
    predecessorName: taskName(predecessorId),
    successorId: task.id,
    successorName: task.name,
    isCritical: criticalEdgeKeys.has(`${predecessorId}:${task.id}`),
  })));

  if (loading) return <div className="p-8 text-center animate-pulse">Loading Gantt chart...</div>;
  if (error) return <div className="p-8 text-center text-rose-500 flex flex-col items-center gap-2"><AlertTriangle /> {error}</div>;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-start justify-between">
        <div>
          <button onClick={() => workspace.isProjectWorkspace ? navigate(workspace.path("dashboard")) : navigate(-1)} className="text-muted-foreground hover:text-foreground flex items-center gap-2 text-sm mb-2">
            <ArrowLeft size={14} /> Project Dashboard
          </button>
          <h1 className="text-3xl font-bold tracking-tight">Project Schedule{workspace.project ? ` · ${workspace.project.name}` : ""}</h1>
          <p className="text-muted-foreground">Interactive Gantt chart and dependency mapping</p>
        </div>
        <div className="flex gap-2">
          <select 
            className="border rounded-md px-3 py-1.5 text-sm"
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value as ViewMode)}
          >
            <option value={ViewMode.Day}>Day View</option>
            <option value={ViewMode.Week}>Week View</option>
            <option value={ViewMode.Month}>Month View</option>
          </select>
          <button onClick={handleCriticalPath} className="btn-outline btn-sm">
            Calculate Critical Path
          </button>
          <button onClick={fetchSchedule} className="btn-primary btn-sm flex items-center gap-2">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      <div className="bg-card border rounded-xl shadow-sm p-4 overflow-x-auto">
        {savingTaskId && <p className="mb-3 text-sm font-medium text-primary">Saving schedule change…</p>}
        {unscheduledTasks.length > 0 && <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {unscheduledTasks.length} task{unscheduledTasks.length === 1 ? " has" : "s have"} no complete planned date range and {unscheduledTasks.length === 1 ? "is" : "are"} not drawn: {unscheduledTasks.map((task) => task.name).join(", ")}.
        </div>}
        <div className="mb-4 flex flex-wrap gap-4 text-xs text-muted-foreground" aria-label="Gantt legend">
          <span className="flex items-center gap-2"><i className="h-3 w-3 rounded-sm bg-blue-600" /> Scheduled</span>
          <span className="flex items-center gap-2"><i className="h-3 w-3 rounded-sm bg-green-600" /> Completed</span>
          <span className="flex items-center gap-2"><i className="h-3 w-3 rounded-sm bg-amber-500" /> Delayed</span>
          <span className="flex items-center gap-2"><i className="h-3 w-3 rounded-sm bg-red-600" /> Critical path</span>
        </div>
        {tasks.length > 0 ? (
          <Gantt
            tasks={tasks}
            viewMode={viewMode}
            onDateChange={handleTaskChange}
            onProgressChange={handleProgressChange}
            arrowColor="#64748b"
            arrowIndent={20}
            listCellWidth="155px"
            columnWidth={viewMode === ViewMode.Month ? 150 : 60}
          />
        ) : (
          <div className="text-center py-10 text-muted-foreground">No tasks available for this project.</div>
        )}
      </div>
      {criticalPath && <div className="bg-card border rounded-xl p-5 shadow-sm">
        <div className="flex items-center gap-2"><Route size={18} className="text-red-600" /><h2 className="font-semibold">Dependency-based Critical Path (CPM)</h2></div>
        <p className="mt-1 text-sm text-muted-foreground">
          Forward pass (ES/EF) + backward pass (LS/LF) across {criticalPath.dependencyCount} stored dependencies.
          Isolated tasks are excluded; the longest individual task is never used as a fallback.
        </p>
        {criticalPath.criticalTaskIds.length > 0 ? <>
          <p className="mt-3 text-sm font-medium">Ordered driving sequence · {criticalPath.projectDurationDays} days</p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm" aria-label="Ordered critical path task IDs">
            {criticalPath.criticalTasks.map((task, index) => <div key={task.taskId} className="contents">
              {index > 0 && <span className="font-bold text-red-600">→</span>}
              <span className="rounded-md border border-red-300 bg-red-50 px-3 py-1.5 font-medium text-red-800">{index + 1}. {task.taskCode} — {task.name}</span>
            </div>)}
          </div>
          <ol className="mt-4 grid gap-3 text-sm md:grid-cols-2">
            {criticalPath.criticalTasks.map((task, index) => {
              const predecessor = task.drivingPredecessorId ? taskName(task.drivingPredecessorId) : null;
              const relation = task.drivingDependencyType?.replaceAll("_", " ").toUpperCase();
              return <li key={task.taskId} className="rounded-lg border border-red-200 p-3">
                <p className="font-medium text-red-800">{index + 1}. {task.taskCode} — {task.name}</p>
                <p className="mt-2">ES {task.earliestStart} · EF {task.earliestFinish} · LS {task.latestStart} · LF {task.latestFinish} · Float {task.totalFloatDays}</p>
                <p className="mt-1 text-muted-foreground">
                  {predecessor
                    ? `Driven by ${predecessor} through ${relation}${task.drivingLagDays ? ` with ${task.drivingLagDays} day lag` : ""}; the constraint is tight and total float is zero.`
                    : "Starts the driving dependency chain; forward and backward passes both place it at the same start (zero float)."}
                </p>
              </li>;
            })}
          </ol>
        </> : <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {criticalPath.reason || "No connected dependency chain drives the project finish."}
        </div>}
      </div>}
      <div className="bg-card border rounded-xl p-5 shadow-sm">
        <div className="flex items-center gap-2"><Link2 size={18} /><h2 className="font-semibold">Task Dependencies</h2></div>
        <p className="mt-1 text-sm text-muted-foreground">Arrows are rendered between scheduled Gantt bars. The list below also exposes every stored predecessor → successor relation; red rows are edges in the calculated critical sequence.</p>
        {dependencyEdges.length ? <div className="mt-3 grid gap-2 md:grid-cols-2">
          {dependencyEdges.map((edge) => <div key={`${edge.predecessorId}:${edge.successorId}`} className={`rounded border p-2 text-sm ${edge.isCritical ? "border-red-300 bg-red-50 text-red-800" : ""}`}>
            <span className="font-medium">{edge.predecessorName}</span> <span aria-hidden>→</span> <span className="font-medium">{edge.successorName}</span>
          </div>)}
        </div> : <p className="mt-3 text-sm text-muted-foreground">No dependencies are defined. Add finish-to-start predecessors from a task’s detail page before calculating CPM.</p>}
      </div>
    </div>
  );
};
