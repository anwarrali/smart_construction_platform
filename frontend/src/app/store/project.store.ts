import { create } from "zustand";
import type {
  Project,
  ProjectSummary,
  ProjectFilters,
} from "../../types/project";

interface ProjectState {
  projects: Project[];
  selectedProject: Project | null;
  summary: ProjectSummary | null;
  filters: ProjectFilters;
  totalProjects: number;
  currentPage: number;
  totalPages: number;
  isLoading: boolean;
  isSummaryLoading: boolean;

  setProjects: (
    projects: Project[],
    total: number,
    page: number,
    totalPages: number,
  ) => void;
  setSelectedProject: (project: Project | null) => void;
  setSummary: (summary: ProjectSummary) => void;
  setFilters: (filters: ProjectFilters) => void;
  resetFilters: () => void;
  addProject: (project: Project) => void;
  updateProject: (id: string, updates: Partial<Project>) => void;
  removeProject: (id: string) => void;
  setLoading: (loading: boolean) => void;
  setSummaryLoading: (loading: boolean) => void;
}

const defaultFilters: ProjectFilters = {
  page: 1,
  limit: 10,
};

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  selectedProject: null,
  summary: null,
  filters: { ...defaultFilters },
  totalProjects: 0,
  currentPage: 1,
  totalPages: 0,
  isLoading: false,
  isSummaryLoading: false,

  setProjects: (projects, total, page, totalPages) =>
    set({
      projects,
      totalProjects: total,
      currentPage: page,
      totalPages,
      isLoading: false,
    }),

  setSelectedProject: (project) => set({ selectedProject: project }),

  setSummary: (summary) => set({ summary, isSummaryLoading: false }),

  setFilters: (filters) =>
    set((state) => ({ filters: { ...state.filters, ...filters } })),

  resetFilters: () => set({ filters: { ...defaultFilters } }),

  addProject: (project) =>
    set((state) => ({
      projects: [project, ...state.projects],
      totalProjects: state.totalProjects + 1,
    })),

  updateProject: (id, updates) =>
    set((state) => ({
      projects: state.projects.map((p) =>
        p.id === id ? { ...p, ...updates } : p,
      ),
      selectedProject:
        state.selectedProject?.id === id
          ? { ...state.selectedProject, ...updates }
          : state.selectedProject,
    })),

  removeProject: (id) =>
    set((state) => ({
      projects: state.projects.filter((p) => p.id !== id),
      totalProjects: state.totalProjects - 1,
      selectedProject:
        state.selectedProject?.id === id ? null : state.selectedProject,
    })),

  setLoading: (loading) => set({ isLoading: loading }),

  setSummaryLoading: (loading) => set({ isSummaryLoading: loading }),
}));
