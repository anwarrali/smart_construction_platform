import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { errorMessage } from "../../../utils/errorMessage";
import { useLocation } from "react-router-dom";
import api from "../../../services/api";
import { useRole } from "../../../hooks/useRole";
import type { Project } from "../../../types/project";
import { portfolioProjectsPath, projectModulePath } from "../../../utils/projectRoutes";

interface ProjectWorkspaceValue {
  projectId?: string;
  project: Project | null;
  assignedProjects: Project[];
  isProjectWorkspace: boolean;
  isLoading: boolean;
  error: string;
  path: (module: string) => string;
  portfolioPath: string;
}

const ProjectWorkspaceContext = createContext<ProjectWorkspaceValue | null>(null);

export const ProjectWorkspaceProvider = ({ children }: { children: React.ReactNode }) => {
  const location = useLocation();
  const { role, isConsultantEngineer } = useRole();
  const managerMatch = location.pathname.match(/^\/project-manager\/projects\/([^/]+)(?:\/|$)/);
  const engineerMatch = location.pathname.match(/^\/engineer\/projects\/([^/]+)(?:\/|$)/);
  const consultantMatch = location.pathname.match(/^\/consultant-engineer\/projects\/([^/]+)(?:\/|$)/);
  const genericMatch = location.pathname.match(/^\/projects\/([^/]+)(?:\/|$)/);
  const preferred = role === "engineer" ? (isConsultantEngineer ? consultantMatch : engineerMatch)
    : role === "project_manager" ? managerMatch : genericMatch;
  // A project workspace must survive landing on a prefix that does not belong to the
  // current role (deep links, notification URLs, links authored for another role).
  // Without the fallback the sidebar silently drops back to portfolio mode.
  const match = preferred || managerMatch || engineerMatch || consultantMatch || genericMatch;
  const projectId = match?.[1] ? decodeURIComponent(match[1]) : undefined;
  const supportsProjectWorkspace = ["admin", "owner", "project_manager", "engineer", "consultant"].includes(role || "");
  const isProjectWorkspace = supportsProjectWorkspace && Boolean(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [assignedProjects, setAssignedProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!supportsProjectWorkspace) {
      setProject(null);
      setAssignedProjects([]);
      setError("");
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError("");
    Promise.all([
      api.projects.list({ limit: 100 }),
      projectId ? api.projects.getById(projectId) : Promise.resolve(null),
    ]).then(([response, activeProject]) => {
      if (cancelled) return;
      const projects = response.data || [];
      setAssignedProjects(projects);
      setProject(activeProject);
      if (projectId && !projects.some((item) => item.id === projectId)) {
        setError(role === "engineer"
          ? `This project is not assigned to your ${isConsultantEngineer ? "Consultant" : "Main Contractor"} Engineer account.`
          : "This project is not assigned to your Project Manager account.");
        setProject(null);
      }
    }).catch((err: any) => {
      if (cancelled) return;
      setProject(null);
      setError(errorMessage(err, "Unable to load the selected project workspace."));
    }).finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, role, supportsProjectWorkspace, isConsultantEngineer]);

  const value = useMemo<ProjectWorkspaceValue>(() => ({
    projectId,
    project,
    assignedProjects,
    isProjectWorkspace,
    isLoading,
    error,
    path: (module: string) => {
      return projectId
        ? projectModulePath(projectId, module, role, isConsultantEngineer ? "external_consultant" : undefined)
        : portfolioProjectsPath(role, isConsultantEngineer ? "external_consultant" : undefined);
    },
    portfolioPath: portfolioProjectsPath(role, isConsultantEngineer ? "external_consultant" : undefined),
  }), [projectId, project, assignedProjects, isProjectWorkspace, isLoading, error, isConsultantEngineer, role]);

  return <ProjectWorkspaceContext.Provider value={value}>{children}</ProjectWorkspaceContext.Provider>;
};

export const useProjectWorkspace = () => {
  const context = useContext(ProjectWorkspaceContext);
  if (!context) throw new Error("useProjectWorkspace must be used inside ProjectWorkspaceProvider");
  return context;
};
