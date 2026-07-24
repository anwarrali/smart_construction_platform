import api from "../../../services/api";

export const issuesService = {
  list: async (filters?: { projectId?: string; taskId?: string; status?: string; discipline?: string; dateFrom?: string; dateTo?: string; hasAttachments?: boolean }) => {
    const data = await api.issues.list(filters);
    return { data, total: data.length, page: 1, limit: data.length, totalPages: data.length ? 1 : 0 };
  },

  getByProject: async (projectId: string) => {
    const data = await api.issues.list({ projectId });
    return { data };
  },
  create: async (data: { projectId: string; taskId?: string; title: string; description?: string; severity: string; category?: string }) => api.issues.create(data),
  update: async (id: string, data: Record<string, unknown>) => api.issues.update(id, data),
};
