import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../ui/Button";
import { Badge } from "../../ui/Badge";
import { Loader } from "../../ui/Loader";
import { useNotifications } from "../../../hooks/useNotifications";
import { useNotificationStore } from "../../../app/store/notification.store";
import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";
import { ROUTES } from "../../../utils/constants";
import { timeAgo } from "../../../utils/date";

interface NotificationDropdownProps {
  isOpen: boolean;
  onClose: () => void;
}

export const NotificationDropdown = ({
  isOpen,
  onClose,
}: NotificationDropdownProps) => {
  const {
    notifications,
    isLoading,
    fetchNotifications,
    markAsRead,
    markAllAsRead,
  } = useNotifications();
  const { unreadCount } = useNotificationStore();
  const workspace = useProjectWorkspace();
  const navigate = useNavigate();

  useEffect(() => {
    if (isOpen) {
      fetchNotifications(1, workspace.projectId);
    }
  }, [isOpen, fetchNotifications, workspace.projectId]);

  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute right-0 top-full mt-2 w-80 rounded-md border bg-popover shadow-lg z-50">
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-sm">Notifications</h3>
            {unreadCount > 0 && (
              <Badge variant="danger" size="sm">
                {unreadCount} new
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1">
            {unreadCount > 0 && (
              <Button variant="ghost" size="sm" onClick={() => markAllAsRead(workspace.projectId)}>
                Mark all read
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                navigate(ROUTES.NOTIFICATIONS);
                onClose();
              }}
            >
              ⚙️
            </Button>
          </div>
        </div>

        <div className="max-h-80 overflow-y-auto">
          {isLoading ? (
            <div className="py-8">
              <Loader size="sm" />
            </div>
          ) : notifications.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              <p className="text-2xl mb-2">🔔</p>
              <p>No notifications yet</p>
            </div>
          ) : (
            notifications.slice(0, 10).map((notification) => (
              <button
                key={notification.id}
                className={`w-full text-left px-4 py-3 border-b last:border-b-0 transition-colors hover:bg-accent ${
                  !notification.isRead ? "bg-muted/30" : ""
                }`}
                onClick={async () => {
                  await markAsRead(notification.id);
                  if (notification.link) {
                    navigate(notification.link);
                  }
                  onClose();
                }}
              >
                <div className="flex items-start gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {notification.title}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                      {notification.message}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {timeAgo(notification.createdAt)}
                    </p>
                  </div>
                  {!notification.isRead && (
                    <span className="w-2 h-2 rounded-full bg-primary mt-1.5 flex-shrink-0" />
                  )}
                </div>
              </button>
            ))
          )}
        </div>

        {notifications.length > 10 && (
          <div className="border-t p-2">
            <Button
              variant="ghost"
              size="sm"
              fullWidth
              onClick={() => {
                navigate(ROUTES.NOTIFICATIONS);
                onClose();
              }}
            >
              View all notifications
            </Button>
          </div>
        )}
      </div>
    </>
  );
};
