import { useNavigate } from "react-router-dom";
import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { formatDate, getDaysRemaining } from "../../../utils/date";
import type { Project } from "../../../types/project";

interface ProjectCardProps {
  project: Project;
}

const statusVariant: Record<
  string,
  "neutral" | "success" | "warning" | "danger" | "info"
> = {
  planning: "info",
  active: "success",
  on_hold: "warning",
  delayed: "danger",
  completed: "neutral",
  cancelled: "neutral",
};

export const ProjectCard = ({ project }: ProjectCardProps) => {
  const navigate = useNavigate();
  const daysRemaining = getDaysRemaining(project.plannedEndDate || "");

  return (
    <Card
      isHoverable
      className="cursor-pointer"
      onClick={() => navigate(`/projects/${project.id}`)}
    >
      <div className="space-y-3">
        <div className="flex items-start justify-between">
          <h3 className="font-semibold text-lg truncate flex-1">
            {project.name}
          </h3>
          <Badge variant={statusVariant[project.status] || "neutral"}>
            {project.status.replace("_", " ")}
          </Badge>
        </div>

        <p className="text-sm text-muted-foreground line-clamp-2">
          {project.description}
        </p>

        {project.location && (
          <div className="flex items-center gap-1 text-sm text-muted-foreground">
            <span>📍</span>
            <span>{project.location}</span>
          </div>
        )}

        <div>
          <div className="flex items-center justify-between text-xs mb-1">
            <span>Progress</span>
            <span className="font-medium">{project.completionPercentage}%</span>
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${project.completionPercentage}%` }}
            />
          </div>
        </div>

        <div className="flex items-center justify-between pt-2 border-t text-sm">
          <span className="text-muted-foreground">
            {formatDate(project.startDate || "")} —{" "}
            {formatDate(project.plannedEndDate || "")}
          </span>
          {project.status === "delayed" && (
            <Badge variant="danger" size="sm">
              Delayed
            </Badge>
          )}
          {project.status === "active" &&
            daysRemaining <= 7 &&
            daysRemaining > 0 && (
              <Badge variant="warning" size="sm">
                {daysRemaining}d left
              </Badge>
            )}
        </div>
      </div>
    </Card>
  );
};
