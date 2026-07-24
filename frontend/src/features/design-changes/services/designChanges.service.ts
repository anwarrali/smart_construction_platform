import api from "../../../services/api";

export const designChangesService = {
  getByProject: async (projectId?: string, filters?: { status?: string; discipline?: string; dateFrom?: string; dateTo?: string; hasAttachments?: boolean }) => {
    const data = await api.designChanges.list({ projectId, ...filters });
    return { data };
  },
  create: async (data: Record<string, unknown>) => api.designChanges.create(data),
};
