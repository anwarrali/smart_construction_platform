import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import api from "../../../services/api";
import { useRole } from "../../../hooks/useRole";
import type { Project } from "../../../types/project";

interface ProjectWorkspaceValue {
  projectId?: string;
  project: Project | null;
  assignedProjects: Project[];
  isProjectWorkspace: boolean;
  isLoading: boolean;
  error: string;
  path: (module: string) => string;
}

const ProjectWorkspaceContext = createContext<ProjectWorkspaceValue | null>(null);

export const ProjectWorkspaceProvider = ({ children }: { children: React.ReactNode }) => {
  const location = useLocation();
  const { role, isConsultantEngineer } = useRole();
  const managerMatch = location.pathname.match(/^\/project-manager\/projects\/([^/]+)(?:\/|$)/);
  const engineerMatch = location.pathname.match(/^\/engineer\/projects\/([^/]+)(?:\/|$)/);
  const consultantMatch = location.pathname.match(/^\/consultant-engineer\/projects\/([^/]+)(?:\/|$)/);
  const match = role === "engineer" ? (isConsultantEngineer ? consultantMatch : engineerMatch) : managerMatch;
  const projectId = match?.[1] ? decodeURIComponent(match[1]) : undefined;
  const supportsProjectWorkspace = role === "project_manager" || role === "engineer";
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
      setError(err?.response?.data?.detail || "Unable to load the selected project workspace.");
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
      const base = role === "engineer"
        ? (isConsultantEngineer ? "/consultant-engineer/projects" : "/engineer/projects")
        : "/project-manager/projects";
      return projectId ? `${base}/${projectId}/${module.replace(/^\//, "")}` : base;
    },
  }), [projectId, project, assignedProjects, isProjectWorkspace, isLoading, error, isConsultantEngineer]);

  return <ProjectWorkspaceContext.Provider value={value}>{children}</ProjectWorkspaceContext.Provider>;
};

export const useProjectWorkspace = () => {
  const context = useContext(ProjectWorkspaceContext);
  if (!context) throw new Error("useProjectWorkspace must be used inside ProjectWorkspaceProvider");
  return context;
};
