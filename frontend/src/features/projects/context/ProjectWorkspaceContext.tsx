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

/**
 * The workspace prefixes this provider recognises.
 *
 * `/projects/:id/…` is the only one anything produces now. The other three are
 * retired, and they are still matched because this provider sits *above* the
 * route that redirects them and therefore runs once on the pre-redirect
 * pathname. Without them the sidebar would flash back to portfolio mode on
 * every deep link that arrived from a notification sent before the collapse.
 */
const WORKSPACE_PATTERNS = [
  /^\/projects\/([^/]+)(?:\/|$)/,
  /^\/project-manager\/projects\/([^/]+)(?:\/|$)/,
  /^\/engineer\/projects\/([^/]+)(?:\/|$)/,
  /^\/consultant-engineer\/projects\/([^/]+)(?:\/|$)/,
];

export const ProjectWorkspaceProvider = ({ children }: { children: React.ReactNode }) => {
  const location = useLocation();
  const { hasCapability } = useRole();
  /* One address, so one match — no preference order keyed on who is asking.
     The retired version chose a pattern by role and then fell back through the
     others, which was three rules for something the product only ever had one
     of, and which could not have answered for a role an office invented. */
  const projectId = useMemo(() => {
    for (const pattern of WORKSPACE_PATTERNS) {
      const match = location.pathname.match(pattern);
      if (match?.[1]) return decodeURIComponent(match[1]);
    }
    return undefined;
  }, [location.pathname]);

  const isProjectWorkspace = Boolean(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [assignedProjects, setAssignedProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
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
        /* One message, because there is one reason: this project is not one of
           yours. The retired version named the reader's role in the sentence
           ("your Main Contractor Engineer account"), which a configurable role
           model cannot do — and which told them nothing they did not know. */
        setError("This project is not assigned to your account.");
        setProject(null);
      }
    }).catch((err: any) => {
      if (cancelled) return;
      setProject(null);
      setError(errorMessage(err, "Unable to load the selected project workspace."));
    }).finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [projectId]);

  const value = useMemo<ProjectWorkspaceValue>(() => ({
    projectId,
    project,
    assignedProjects,
    isProjectWorkspace,
    isLoading,
    error,
    path: (module: string) => (
      projectId
        ? projectModulePath(projectId, module, hasCapability)
        : portfolioProjectsPath()
    ),
    portfolioPath: portfolioProjectsPath(),
  }), [projectId, project, assignedProjects, isProjectWorkspace, isLoading, error, hasCapability]);

  return <ProjectWorkspaceContext.Provider value={value}>{children}</ProjectWorkspaceContext.Provider>;
};

export const useProjectWorkspace = () => {
  const context = useContext(ProjectWorkspaceContext);
  if (!context) throw new Error("useProjectWorkspace must be used inside ProjectWorkspaceProvider");
  return context;
};
