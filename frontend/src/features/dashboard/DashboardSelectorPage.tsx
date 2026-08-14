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

const EngineerEntry = () => {
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

  if (
    !user
    || user.role !== "engineer"
    || !["main_contractor", "external_consultant"].includes(user.engineerAffiliation || "")
    || user.status !== "active"
  ) {
    return <div className="rounded-xl border bg-card p-6 text-destructive">{t("dashboardSelectorPage.active_engineer_organization_side_is")}</div>;
  }
  if (error) return <div className="rounded-xl border bg-card p-6 text-destructive">{error}</div>;
  if (!projects) return <div className="p-8 text-center text-muted-foreground">{t("dashboardSelectorPage.loading_your_assigned_projects")}</div>;
  if (projects.length === 1) {
    const base = user.engineerAffiliation === "external_consultant" ? "/consultant-engineer/projects" : "/engineer/projects";
    return <Navigate to={`${base}/${projects[0].id}/dashboard`} replace />;
  }
  return <Navigate to={user.engineerAffiliation === "external_consultant" ? "/consultant-engineer/projects" : "/engineer/projects"} replace />;
};

/**
 * DashboardSelectorPage
 * Reads the authenticated user's role and renders the correct role-based dashboard.
 * Engineers → EngineerDashboard
 * Owner → redirect to /owner-dashboard
 * Admin → redirect to /admin
 */
export const DashboardSelectorPage = () => {
  const { role } = useRole();

  if (!role) return <Navigate to="/auth/login" replace />;

  switch (role) {
    case "owner":
      return <Navigate to="/owner-dashboard" replace />;
    case "admin":
      return <Navigate to="/admin" replace />;
    case "project_manager":
      return <ProjectManagerDashboard />;
    case "consultant":
      return <ConsultantDashboard />;
    case "engineer":
      return <EngineerEntry />;
    default:
      return <Navigate to="/projects" replace />;
  }
};
