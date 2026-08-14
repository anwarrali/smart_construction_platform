import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { formatDate, isOverdue } from "../../../utils/date";
import { formatAssigneeRole, getInitials, getAvatarColor } from "../../../utils/helpers";
import { ROUTES } from "../../../utils/constants";
import type { Task } from "../../../types/task";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";

interface TaskCardProps {
  task: Task;
  onEdit?: (task: Task) => void;
  onDelete?: (task: Task) => void;
}

const statusVariant: Record<
  string,
  "neutral" | "info" | "success" | "danger" | "warning"
> = {
  backlog: "neutral",
  todo: "neutral",
  in_progress: "info",
  under_review: "warning",
  rework_required: "danger",
  done: "success",
  blocked: "danger",
  cancelled: "neutral",
};

const priorityVariant: Record<string, "neutral" | "warning" | "danger"> = {
  low: "neutral",
  medium: "warning",
  high: "danger",
  critical: "danger",
};

export const TaskCard = ({ task, onEdit, onDelete }: TaskCardProps) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const workspace = useProjectWorkspace();
  const overdue =
    isOverdue(task.plannedEndDate || "") && task.status !== "done";
  const assignees = task.assignees || [];
  const primaryAssignee = assignees[0];

  return (
    <Card
      isHoverable
      className="cursor-pointer"
      onClick={() => navigate(workspace.isProjectWorkspace ? workspace.path(`tasks/${task.id}`) : `${ROUTES.TASKS}/${task.id}`)}
    >
      <div className="space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1"><p className="text-xs font-semibold text-primary">{task.taskCode}</p><h4 className="font-medium text-sm line-clamp-1">{task.name}</h4></div>
          <Badge
            variant={priorityVariant[task.priority] || "neutral"}
            size="sm"
          >
            {task.priority}
          </Badge>
        </div>

        <div className="flex items-center gap-1">
          <Badge variant={statusVariant[task.status] || "neutral"} size="sm">
            {task.status.replace("_", " ")}
          </Badge>
          {task.isCriticalPath && (
            <Badge variant="danger" size="sm" dot>
              {t("taskCard.critical")}
            </Badge>
          )}
          {task.isMilestone && (
            <Badge variant="info" size="sm" dot>
              {t("taskCard.milestone")}
            </Badge>
          )}
        </div>

        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Due: {formatDate(task.plannedEndDate || "")}</span>
          {overdue && <span className="text-state-overdue font-medium">{t("taskCard.overdue")}</span>}
        </div>

        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">
            {task.progressPercentage}%
          </span>
          <div className="progress-bar w-24">
            <div
              className="progress-fill"
              style={{ width: `${task.progressPercentage}%` }}
            />
          </div>
        </div>

        <div className="flex min-w-0 items-center gap-3 border-t pt-2" title={assignees.map((assignee) => assignee.fullName).join(", ") || "Unassigned"}>
          {primaryAssignee ? <>
            <div className="flex shrink-0 -space-x-2">
              {assignees.slice(0, 2).map((assignee) => <div key={assignee.id} className="relative flex h-7 w-7 items-center justify-center overflow-hidden rounded-full border-2 border-card text-[10px] font-semibold text-white" style={{ backgroundColor: getAvatarColor(assignee.fullName) }}>
                {assignee.avatarUrl ? <img src={assignee.avatarUrl} alt="" className="h-full w-full object-cover" /> : getInitials(assignee.fullName)}
              </div>)}
            </div>
            <div className="min-w-0 flex-1"><p className="truncate text-xs font-medium text-foreground">{primaryAssignee.fullName}{assignees.length > 1 && <span className="ml-1 text-primary">+{assignees.length - 1}</span>}</p><p className="truncate text-[11px] text-muted-foreground">{formatAssigneeRole(primaryAssignee.role, primaryAssignee.engineerProfile?.discipline)}</p></div>
          </> : <span className="text-xs text-muted-foreground">{t("taskCard.unassigned")}</span>}
        </div>
        {(onEdit || onDelete) && <div className="flex justify-end gap-2 border-t pt-2">
          {onEdit && <button type="button" className="text-xs font-medium text-primary hover:underline" onClick={(event) => { event.stopPropagation(); onEdit(task); }}>{t("taskCard.edit")}</button>}
          {onDelete && <button type="button" className="text-xs font-medium text-destructive hover:underline" onClick={(event) => { event.stopPropagation(); onDelete(task); }}>{t("taskCard.delete")}</button>}
        </div>}
      </div>
    </Card>
  );
};
