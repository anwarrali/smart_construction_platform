import api from "../../../services/api";
import type {
  CreateTaskRequest,
  UpdateTaskRequest,
  Task,
  TasksResponse,
  TaskFilters,
  TaskAnalytics,
} from "../../../types/task";

export const tasksService = {
  list: async (filters?: TaskFilters): Promise<TasksResponse> => {
    return api.tasks.list(filters);
  },
  getById: async (id: string): Promise<Task> => {
    return api.tasks.getById(id);
  },
  getByProject: async (
    projectId: string,
    filters?: TaskFilters,
  ): Promise<TasksResponse> => {
    return api.tasks.getByProject(projectId, filters);
  },
  getMyTasks: async (filters?: TaskFilters): Promise<TasksResponse> => {
    return api.tasks.getMyTasks(filters);
  },
  create: async (data: CreateTaskRequest): Promise<Task> => {
    return api.tasks.create(data);
  },
  update: async (id: string, data: UpdateTaskRequest): Promise<Task> => {
    return api.tasks.update(id, data);
  },
  delete: async (id: string): Promise<void> => {
    return api.tasks.delete(id);
  },
  getAnalytics: async (projectId: string): Promise<TaskAnalytics> => {
    return api.tasks.getAnalytics(projectId);
  },
};
