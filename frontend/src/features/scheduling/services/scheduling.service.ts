import api from "../../../services/api";

export const schedulingService = {
  getGanttData: async (projectId: string) => {
    return api.scheduling.getGanttData(projectId);
  },

  getCriticalPath: async (projectId: string) => {
    return api.scheduling.getCriticalPath(projectId);
  },

  getDelayAnalysis: async (projectId: string) => {
    return api.scheduling.getDelayAnalysis(projectId);
  },
};
