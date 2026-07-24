import api from "../../../services/api";

export const siteReportsService = {
  list: async (filters?: { projectId?: string; status?: string; discipline?: string; dateFrom?: string; dateTo?: string; hasAttachments?: boolean }) => {
    return api.siteReports.list(filters);
  },
  getByProject: async (projectId: string) => {
    return api.siteReports.list({ projectId });
  },
};
