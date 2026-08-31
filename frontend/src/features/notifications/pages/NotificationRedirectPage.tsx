/**
 * Resolves /notifications/:id into the page that notification is about.
 *
 * This route exists because a push notification can only carry an id. The
 * service worker cannot know that a task belongs under /engineer/projects/…
 * for one user and /project-manager/projects/… for another — role-aware
 * routing lives in the React app, so the notification lands here first and is
 * redirected once the app knows who is signed in.
 *
 * It reuses `projectEntityPath`, the same mapping the notification list uses,
 * so arriving from a push and clicking the same notification in the bell reach
 * an identical destination.
 */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import api from "../../../services/api";
import { Loader } from "../../../components/ui/Loader";
import { useRole } from "../../../hooks/useRole";
import { useNotificationStore } from "../../../app/store/notification.store";
import { projectEntityPath, projectModulePath } from "../../../utils/projectRoutes";
import { ROUTES } from "../../../utils/constants";

export const NotificationRedirectPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { hasCapability } = useRole();
  const markAsRead = useNotificationStore((state) => state.markAsRead);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!id) {
      navigate(ROUTES.NOTIFICATIONS, { replace: true });
      return;
    }

    let cancelled = false;

    void (async () => {
      try {
        const notification = await api.notifications.getById(id);
        if (cancelled) return;

        // Opening a notification is reading it. Best-effort: a failure here
        // must not stop the navigation the user actually asked for.
        void api.notifications.markRead(id).then(() => markAsRead(id)).catch(() => {});

        const projectId = notification.projectId;
        const entityType =
          notification.relatedEntityType || (notification.taskId ? "TASK" : undefined);
        const entityId = notification.relatedEntityId || notification.taskId;

        // `replace`, so the browser Back button returns to wherever the user
        // was rather than bouncing through this resolver again.
        if (!projectId) {
          navigate(notification.actionUrl || ROUTES.NOTIFICATIONS, { replace: true });
        } else if (entityType) {
          navigate(projectEntityPath(projectId, entityType, entityId || "", hasCapability), {
            replace: true,
          });
        } else {
          navigate(projectModulePath(projectId, "activity", hasCapability), { replace: true });
        }
      } catch {
        // A notification that no longer exists, or belongs to somebody else,
        // is not an error worth a page of its own — the notification centre is
        // a truthful destination either way.
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id, navigate, hasCapability, markAsRead]);

  useEffect(() => {
    if (!failed) return;
    const timer = window.setTimeout(() => navigate(ROUTES.NOTIFICATIONS, { replace: true }), 1200);
    return () => window.clearTimeout(timer);
  }, [failed, navigate]);

  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <Loader size="sm" />
      <p className="text-sm text-muted-foreground">
        {failed
          ? t("notificationRedirect.not_found")
          : t("notificationRedirect.opening")}
      </p>
    </div>
  );
};
