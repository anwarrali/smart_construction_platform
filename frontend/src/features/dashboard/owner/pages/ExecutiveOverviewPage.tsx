import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useVocabulary } from "../../../../utils/vocabulary";
import { Card } from "../../../../components/ui/Card";
import { Loader } from "../../../../components/ui/Loader";
import api from "../../../../services/api";
import type { OwnerDashboardData, Project } from "../../../../types/project";

export const ExecutiveOverviewPage = () => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const [projects, setProjects] = useState<Project[]>([]);
  const [details, setDetails] = useState<OwnerDashboardData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.projects.list({ limit: 100 }).then(async (response) => {
      const assigned = response.data || [];
      setProjects(assigned);
      setDetails(await Promise.all(assigned.map((project) => api.projects.getOwnerDashboard(project.id))));
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <Loader fullPage />;
  const average = projects.length ? Math.round(projects.reduce((sum, item) => sum + Number(item.completionPercentage || 0), 0) / projects.length) : 0;
  const criticalIssues = details.reduce((sum, item) => sum + item.openIssues.filter((issue) => issue.severity === "critical").length, 0);
  const pendingApprovals = details.reduce((sum, item) => sum + item.consultantApprovals.pending, 0);

  return <div className="page-container space-y-6">
    <div><p className="text-sm font-medium text-primary">{t("executiveOverviewPage.executive_overview")}</p><h1 className="text-3xl font-bold">{t("executiveOverviewPage.assigned_project_portfolio")}</h1><p className="mt-1 text-muted-foreground">{t("executiveOverviewPage.subtitle")}</p></div>
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[[t("executiveOverviewPage.assigned_projects"), projects.length], [t("executiveOverviewPage.average_completion"), `${average}%`], [t("executiveOverviewPage.open_critical_issues"), criticalIssues], [t("executiveOverviewPage.pending_consultant_approvals"), pendingApprovals]].map(([label, value]) => <Card key={String(label)} className="p-5"><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 text-3xl font-bold">{value}</p></Card>)}</div>
    <div className="grid gap-4 lg:grid-cols-2">{details.map((item) => <Card key={item.costSummary.projectId} className="p-5"><div className="flex items-start justify-between"><div><h2 className="font-semibold">{item.projectSummary.name}</h2><p className="text-sm text-muted-foreground">{vocabulary.projectHealth(item.projectHealth)}</p></div><p className="text-2xl font-bold">{item.projectSummary.completionPercentage}%</p></div><div className="mt-4 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${item.projectSummary.completionPercentage}%` }} /></div><div className="mt-4 grid grid-cols-3 gap-3 text-sm"><div><p className="text-xs text-muted-foreground">{t("executiveOverviewPage.critical_delays")}</p><p className="font-semibold">{item.delayedTasks.length}</p></div><div><p className="text-xs text-muted-foreground">{t("executiveOverviewPage.critical_issues")}</p><p className="font-semibold">{item.openIssues.filter((issue) => issue.severity === "critical").length}</p></div><div><p className="text-xs text-muted-foreground">{t("executiveOverviewPage.major_changes")}</p><p className="font-semibold">{item.designChanges.length}</p></div></div></Card>)}</div>
  </div>;
};
