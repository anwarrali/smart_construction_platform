import { useCallback, useState } from "react";
import { useNotificationStore } from "../app/store/notification.store";
import api from "../services/api";
import { useRole } from "./useRole";

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
          const projectRoot = role === "project_manager" && notification.projectId
            ? `/project-manager/projects/${notification.projectId}`
            : role === "engineer" && notification.projectId
              ? `${isConsultantEngineer ? "/consultant-engineer/projects" : "/engineer/projects"}/${notification.projectId}`
              : undefined;
          const link = entityType === "MESSAGE" ? undefined
            : projectRoot && entityType === "TASK" && entityId ? `${projectRoot}/tasks/${entityId}`
            : projectRoot && entityType === "PROJECT" ? `${projectRoot}/dashboard`
            : projectRoot && entityType === "DESIGN_CHANGE" ? `${projectRoot}/design-changes${entityId ? `?changeId=${entityId}` : ""}`
            : projectRoot && entityType === "ISSUE" ? `${projectRoot}/issues${entityId ? `?issueId=${entityId}` : ""}`
            : projectRoot && entityType === "SITE_REPORT" ? `${projectRoot}/site-reports${entityId ? `?reportId=${entityId}` : ""}`
            : projectRoot && entityType === "DOCUMENT" ? `${projectRoot}/documents${entityId ? `?documentId=${entityId}` : ""}`
            : projectRoot && entityType === "MILESTONE" ? `${projectRoot}/milestones`
            : role === "owner" && entityType === "DOCUMENT" ? `/documents${entityId ? `?documentId=${entityId}` : ""}`
            : role === "owner" && entityType === "DESIGN_CHANGE" ? `/design-changes${entityId ? `?changeId=${entityId}` : ""}`
            : role === "owner" && entityType === "SITE_REPORT" ? `/site-reports${entityId ? `?reportId=${entityId}` : ""}`
            : role === "owner" ? "/owner-dashboard"
            : entityType === "TASK" && entityId ? `/tasks/${entityId}`
            : entityType === "PROJECT" && entityId ? `/projects/${entityId}`
            : entityType === "DESIGN_CHANGE" ? `/design-changes${entityId ? `?changeId=${entityId}` : ""}`
            : entityType === "ISSUE" ? `/issues${entityId ? `?issueId=${entityId}` : ""}`
            : entityType === "SITE_REPORT" ? `/site-reports${entityId ? `?reportId=${entityId}` : ""}`
            : entityType === "DOCUMENT" ? `/documents${entityId ? `?documentId=${entityId}` : ""}`
            : notification.taskId ? `/tasks/${notification.taskId}`
            : notification.projectId ? `/projects/${notification.projectId}` : undefined;
          return { ...notification, link };
        });
        setNotifications(items);
        setPagination({ page: data.page || page, total: data.total || 0, totalPages: data.totalPages || 0 });
      } catch (err: any) {
        setError(err?.response?.data?.detail || "Unable to load notifications.");
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
