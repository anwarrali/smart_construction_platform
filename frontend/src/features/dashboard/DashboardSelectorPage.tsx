import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../utils/errorMessage";
import { Navigate } from "react-router-dom";
import { useRole } from "../../hooks/useRole";
import { ProjectManagerDashboard } from "./project-manager/pages/ProjectManagerDashboard";
import { ConsultantDashboard } from "./consultant/pages/ConsultantDashboard";
import { useAuthStore } from "../../app/store/auth.store";
import api from "../../services/api";
import type { Project } from "../../types/project";

/** Somebody whose work is the tasks they hold: straight into it. */
const WorkEntry = () => {
  const { t } = useTranslation();
  const user = useAuthStore((state) => state.user);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.projects.list({ limit: 100 }).then((response) => {
      if (!cancelled) setProjects(response.data || []);
    }).catch((err: any) => {
      if (!cancelled) setError(errorMessage(err, "Unable to load assigned projects."));
    });
    return () => { cancelled = true; };
  }, []);

  if (!user || user.status !== "active") {
    return <div className="rounded-xl border bg-card p-6 text-destructive">{t("dashboardSelectorPage.account_not_active")}</div>;
  }
  if (error) return <div className="rounded-xl border bg-card p-6 text-destructive">{error}</div>;
  if (!projects) return <div className="p-8 text-center text-muted-foreground">{t("dashboardSelectorPage.loading_your_assigned_projects")}</div>;
  if (projects.length === 1) return <Navigate to={`/projects/${projects[0].id}/my-work`} replace />;
  return <Navigate to="/projects" replace />;
};

/**
 * Where a sign-in lands, chosen by what the person may do.
 *
 * Each destination is guarded by the same capability that picks it here, so
 * the landing page is always one the person can open — whatever the office
 * called their role.
 */
export const DashboardSelectorPage = () => {
  const { t } = useTranslation();
  const user = useAuthStore((state) => state.user);
  const { hasCapability, permissionsReady, isInternal } = useRole();

  if (!user) return <Navigate to="/auth/login" replace />;
  if (!permissionsReady) {
    return <div className="p-8 text-center text-muted-foreground">{t("common.loading")}</div>;
  }
  if (hasCapability("platform.manage_users")) return <Navigate to="/admin" replace />;
  if (hasCapability("project.manage_members") || hasCapability("platform.create_project")) {
    return <ProjectManagerDashboard />;
  }
  if (!isInternal && hasCapability("client_portal.view")) return <Navigate to="/owner-dashboard" replace />;
  if (hasCapability("task.review")) return <ConsultantDashboard />;
  if (hasCapability("task.view")) return <WorkEntry />;
  return <Navigate to="/projects" replace />;
};
