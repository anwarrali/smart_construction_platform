import { create } from "zustand";
import type { Task, TaskAnalytics, TaskFilters } from "../../types/task";

interface TaskState {
  tasks: Task[];
  selectedTask: Task | null;
  analytics: TaskAnalytics | null;
  filters: TaskFilters;
  totalTasks: number;
  currentPage: number;
  totalPages: number;
  isLoading: boolean;
  isAnalyticsLoading: boolean;

  setTasks: (
    tasks: Task[],
    total: number,
    page: number,
    totalPages: number,
  ) => void;
  setSelectedTask: (task: Task | null) => void;
  setAnalytics: (analytics: TaskAnalytics) => void;
  setFilters: (filters: TaskFilters) => void;
  resetFilters: () => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  removeTask: (id: string) => void;
  updateTaskStatus: (id: string, status: Task["status"]) => void;
  setLoading: (loading: boolean) => void;
  setAnalyticsLoading: (loading: boolean) => void;
}

const defaultFilters: TaskFilters = {
  page: 1,
  limit: 10,
};

export const useTaskStore = create<TaskState>((set) => ({
  tasks: [],
  selectedTask: null,
  analytics: null,
  filters: { ...defaultFilters },
  totalTasks: 0,
  currentPage: 1,
  totalPages: 0,
  isLoading: false,
  isAnalyticsLoading: false,

  setTasks: (tasks, total, page, totalPages) =>
    set({
      tasks,
      totalTasks: total,
      currentPage: page,
      totalPages,
      isLoading: false,
    }),

  setSelectedTask: (task) => set({ selectedTask: task }),

  setAnalytics: (analytics) => set({ analytics, isAnalyticsLoading: false }),

  setFilters: (filters) =>
    set((state) => ({ filters: { ...state.filters, ...filters } })),

  resetFilters: () => set({ filters: { ...defaultFilters } }),

  addTask: (task) =>
    set((state) => ({
      tasks: [task, ...state.tasks],
      totalTasks: state.totalTasks + 1,
    })),

  updateTask: (id, updates) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.id === id ? { ...t, ...updates } : t)),
      selectedTask:
        state.selectedTask?.id === id
          ? { ...state.selectedTask, ...updates }
          : state.selectedTask,
    })),

  removeTask: (id) =>
    set((state) => ({
      tasks: state.tasks.filter((t) => t.id !== id),
      totalTasks: state.totalTasks - 1,
      selectedTask: state.selectedTask?.id === id ? null : state.selectedTask,
    })),

  updateTaskStatus: (id, status) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.id === id ? { ...t, status } : t)),
      selectedTask:
        state.selectedTask?.id === id
          ? { ...state.selectedTask, status }
          : state.selectedTask,
    })),

  setLoading: (loading) => set({ isLoading: loading }),

  setAnalyticsLoading: (loading) => set({ isAnalyticsLoading: loading }),
}));
