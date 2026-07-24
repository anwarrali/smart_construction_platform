import api from "../../../services/api";
import type {
  CreateProjectRequest,
  UpdateProjectRequest,
  Project,
  ProjectsResponse,
  ProjectFilters,
  ProjectSummary,
  OwnerDashboardData,
} from "../../../types/project";

export const projectsService = {
  list: async (filters?: ProjectFilters): Promise<ProjectsResponse> => {
    return api.projects.list(filters);
  },
  getById: async (id: string): Promise<Project> => {
    return api.projects.getById(id);
  },
  create: async (data: CreateProjectRequest): Promise<Project> => {
    return api.projects.create(data);
  },
  update: async (id: string, data: UpdateProjectRequest): Promise<Project> => {
    return api.projects.update(id, data);
  },
  delete: async (id: string): Promise<void> => {
    return api.projects.delete(id);
  },
  getSummary: async (): Promise<ProjectSummary> => {
    return api.projects.getSummary();
  },
  getMembers: async (id: string) => {
    return api.projects.getMembers(id);
  },
  addMember: async (projectId: string, userId: string, role: string) => {
    return api.projects.addMember(projectId, userId, role);
  },
  removeMember: async (projectId: string, userId: string): Promise<void> => {
    return api.projects.removeMember(projectId, userId);
  },
  getOwnerDashboard: async (id: string): Promise<OwnerDashboardData> => {
    return api.projects.getOwnerDashboard(id);
  },
};
