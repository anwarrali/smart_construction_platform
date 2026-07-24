import { Card } from "../../../components/ui/Card";
import type { ProjectSummary } from "../../../types/project";

interface ProjectStatsProps {
  summary: ProjectSummary | null;
  isLoading: boolean;
}

export const ProjectStats = ({ summary, isLoading }: ProjectStatsProps) => {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <div className="skeleton h-16" />
          </Card>
        ))}
      </div>
    );
  }

  if (!summary) return null;

  const stats = [
    {
      label: "Total Projects",
      value: summary.totalProjects,
      color: "text-blue-600",
    },
    { label: "Active", value: summary.activeProjects, color: "text-green-600" },
    {
      label: "Completed",
      value: summary.completedProjects,
      color: "text-purple-600",
    },
    { label: "Delayed", value: summary.delayedProjects, color: "text-red-600" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {stats.map((stat) => (
        <Card key={stat.label}>
          <p className={`stat-value ${stat.color}`}>{stat.value}</p>
          <p className="stat-label">{stat.label}</p>
        </Card>
      ))}
    </div>
  );
};
