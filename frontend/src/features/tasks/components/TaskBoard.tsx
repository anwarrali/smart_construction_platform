import { TaskCard } from "./TaskCard";
import { Loader } from "../../../components/ui/Loader";
import type { Task, TaskStatus } from "../../../types/task";

interface TaskBoardProps {
  tasks: Task[];
  isLoading: boolean;
  onStatusChange?: (taskId: string, status: TaskStatus) => void;
  onEdit?: (task: Task) => void;
  onDelete?: (task: Task) => void;
}

const COLUMNS: { status: TaskStatus; label: string; color: string }[] = [
  { status: "backlog", label: "Backlog", color: "border-t-gray-400" },
  { status: "todo", label: "To Do", color: "border-t-blue-400" },
  { status: "in_progress", label: "In Progress", color: "border-t-blue-600" },
  { status: "under_review", label: "Review", color: "border-t-yellow-500" },
  { status: "rework_required", label: "Rework", color: "border-t-orange-500" },
  { status: "done", label: "Done", color: "border-t-green-500" },
  { status: "blocked", label: "Blocked", color: "border-t-red-500" },
];

export const TaskBoard = ({ tasks, isLoading, onEdit, onDelete }: TaskBoardProps) => {
  if (isLoading) return <Loader text="Loading tasks..." />;

  return (
    <div className="flex gap-4 overflow-x-auto pb-4 snap-x">
      {COLUMNS.map((col) => {
        const columnTasks = (tasks || []).filter((t) => t.status === col.status);
        return (
          <div
            key={col.status}
            className={`flex-none w-80 snap-start bg-muted/30 rounded-lg border-t-2 ${col.color} min-h-[200px]`}
          >
            <div className="p-3 font-medium text-sm flex items-center justify-between">
              <span>{col.label}</span>
              <span className="text-muted-foreground">
                {columnTasks.length}
              </span>
            </div>
            <div className="p-2 space-y-2">
              {columnTasks.map((task) => (
                <TaskCard key={task.id} task={task} onEdit={onEdit} onDelete={onDelete} />
              ))}
              {columnTasks.length === 0 && (
                <p className="text-xs text-muted-foreground text-center py-8">
                  No tasks
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
