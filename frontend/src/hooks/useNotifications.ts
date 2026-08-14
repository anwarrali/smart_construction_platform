import { useCallback, useState } from "react";
import { errorMessage } from "../utils/errorMessage";
import { useNotificationStore } from "../app/store/notification.store";
import api from "../services/api";
import { useRole } from "./useRole";
import { projectEntityPath, projectModulePath } from "../utils/projectRoutes";

export const useNotifications = () => {
  const { role, isConsultantEngineer } = useRole();
  const [error, setError] = useState("");
  const [pagination, setPagination] = useState({ page: 1, total: 0, totalPages: 0 });
  const store = useNotificationStore();
  const { setLoading, setNotifications, setUnreadCount, markAsRead: markReadInStore, markAllAsRead: markAllReadInStore } = store;

  const fetchNotifications = useCallback(
    async (page: number = 1, projectId?: string, filters?: { unread?: boolean; notificationType?: string; search?: string }) => {
      setLoading(true);
      setError("");
      try {
        const data = await api.notifications.list(page, 20, projectId, filters);
        const items = (data.items || data.data || []).map((notification: any) => {
          const entityType = notification.relatedEntityType;
          const entityId = notification.relatedEntityId;
          const affiliation = isConsultantEngineer ? "external_consultant" as const : undefined;
          const projectId = notification.projectId;
          const effectiveType = entityType || (notification.taskId ? "TASK" : undefined);
          const effectiveId = entityId || notification.taskId;
          // Project-scoped notifications must always resolve inside the project
          // workspace; only a notification with no project at all may fall back
          // to a server-provided action URL.
          const link = projectId
            ? effectiveType
              ? projectEntityPath(projectId, effectiveType, effectiveId || "", role, affiliation)
              : projectModulePath(projectId, "activity", role, affiliation)
            : notification.actionUrl || undefined;
          return { ...notification, link };
        });
        setNotifications(items);
        setPagination({ page: data.page || page, total: data.total || 0, totalPages: data.totalPages || 0 });
      } catch (err: any) {
        setError(errorMessage(err, "Unable to load notifications."));
        setLoading(false);
      }
    },
    [role, isConsultantEngineer, setLoading, setNotifications],
  );

  const fetchUnreadCount = useCallback(async () => {
    try {
      const { count } = await api.notifications.getUnreadCount();
      setUnreadCount(count);
    } catch (error) {
      // ignore
    }
  }, [setUnreadCount]);

  const markAsRead = useCallback(
    async (id: string) => {
      try {
        await api.notifications.markRead(id);
        markReadInStore(id);
      } catch (error) {
        // ignore
      }
    },
    [markReadInStore],
  );

  const markAllAsRead = useCallback(async (projectId?: string) => {
    try {
      await api.notifications.markAllRead(projectId);
      markAllReadInStore();
    } catch (error) {
      // ignore
    }
  }, [markAllReadInStore]);

  return {
    ...store,
    error,
    pagination,
    fetchNotifications,
    fetchUnreadCount,
    markAsRead,
    markAllAsRead,
  };
};
