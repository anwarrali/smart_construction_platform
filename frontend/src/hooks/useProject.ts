import { useCallback } from "react";
import { useProjectStore } from "../app/store/project.store";
import api from "../services/api";
import type {
  CreateProjectRequest,
  UpdateProjectRequest,
  ProjectFilters,
} from "../types/project";

export const useProjects = () => {
  const store = useProjectStore();

  const fetchProjects = useCallback(
    async (filters?: ProjectFilters) => {
      store.setLoading(true);
      if (filters) store.setFilters(filters);
      const mergedFilters = { ...store.filters, ...filters };
      const response = await api.projects.list(mergedFilters);
      store.setProjects(
        response.data,
        response.total,
        response.page,
        response.totalPages,
      );
    },
    [store],
  );

  const fetchProjectById = useCallback(
    async (id: string) => {
      const project = await api.projects.getById(id);
      store.setSelectedProject(project);
      return project;
    },
    [store],
  );

  const createProject = useCallback(
    async (data: CreateProjectRequest) => {
      const project = await api.projects.create(data);
      store.addProject(project);
      return project;
    },
    [store],
  );

  const updateProject = useCallback(
    async (id: string, data: UpdateProjectRequest) => {
      const project = await api.projects.update(id, data);
      store.updateProject(id, project);
      return project;
    },
    [store],
  );

  const deleteProject = useCallback(
    async (id: string) => {
      await api.projects.delete(id);
      store.removeProject(id);
    },
    [store],
  );

  const fetchSummary = useCallback(async () => {
    store.setSummaryLoading(true);
    const summary = await api.projects.getSummary();
    store.setSummary(summary);
  }, [store]);

  return {
    ...store,
    fetchProjects,
    fetchProjectById,
    createProject,
    updateProject,
    deleteProject,
    fetchSummary,
  };
};
