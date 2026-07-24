import { useCallback } from "react";
import { useTaskStore } from "../app/store/task.store";
import api from "../services/api";
import type {
  CreateTaskRequest,
  UpdateTaskRequest,
  TaskFilters,
} from "../types/task";

export const useTasks = () => {
  const store = useTaskStore();

  const fetchTasks = useCallback(
    async (filters?: TaskFilters) => {
      store.setLoading(true);
      if (filters) store.setFilters(filters);
      const mergedFilters = { ...store.filters, ...filters };
      const response = await api.tasks.list(mergedFilters);
      store.setTasks(
        response.data,
        response.total,
        response.page,
        response.totalPages,
      );
    },
    [store],
  );

  const fetchTaskById = useCallback(
    async (id: string) => {
      const task = await api.tasks.getById(id);
      store.setSelectedTask(task);
      return task;
    },
    [store],
  );

  const fetchMyTasks = useCallback(
    async (filters?: TaskFilters) => {
      store.setLoading(true);
      const mergedFilters = { ...store.filters, ...filters };
      const response = await api.tasks.getMyTasks(mergedFilters);
      store.setTasks(
        response.data,
        response.total,
        response.page,
        response.totalPages,
      );
    },
    [store],
  );

  const createTask = useCallback(
    async (data: CreateTaskRequest) => {
      const task = await api.tasks.create(data);
      store.addTask(task);
      return task;
    },
    [store],
  );

  const updateTask = useCallback(
    async (id: string, data: UpdateTaskRequest) => {
      const task = await api.tasks.update(id, data);
      store.updateTask(id, task);
      return task;
    },
    [store],
  );

  const deleteTask = useCallback(
    async (id: string) => {
      await api.tasks.delete(id);
      store.removeTask(id);
    },
    [store],
  );

  const fetchAnalytics = useCallback(
    async (projectId: string) => {
      store.setAnalyticsLoading(true);
      const analytics = await api.tasks.getAnalytics(projectId);
      store.setAnalytics(analytics);
    },
    [store],
  );

  return {
    ...store,
    fetchTasks,
    fetchTaskById,
    fetchMyTasks,
    createTask,
    updateTask,
    deleteTask,
    fetchAnalytics,
  };
};
