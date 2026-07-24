import api from "../../../services/api";

export const notificationsService = {
  list: async (page: number = 1) => {
    return api.notifications.list(page);
  },

  markRead: async (id: string) => {
    return api.notifications.markRead(id);
  },

  markAllRead: async () => {
    return api.notifications.markAllRead();
  },

  getUnreadCount: async () => {
    return api.notifications.getUnreadCount();
  },
};
