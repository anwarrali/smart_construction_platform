import { Button } from "../../../components/ui/Button";
import { useTranslation } from "react-i18next";
import { Loader } from "../../../components/ui/Loader";
import { timeAgo } from "../../../utils/date";
import { useNavigate } from "react-router-dom";

interface Notification {
  id: string;
  title: string;
  message: string;
  type: string;
  isRead: boolean;
  link?: string;
  createdAt: string;
}

interface NotificationListProps {
  notifications: Notification[];
  isLoading: boolean;
  onMarkRead: (id: string) => void;
  onMarkAllRead: () => void;
}

export const NotificationList = ({
  notifications,
  isLoading,
  onMarkRead,
  onMarkAllRead,
}: NotificationListProps) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  if (isLoading) return <Loader text="Loading notifications..." />;

  const unreadCount = notifications.filter((n) => !n.isRead).length;
  const groups = notifications.reduce<Record<string, Notification[]>>((result, notification) => {
    const date = new Date(notification.createdAt);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);
    const key = date.toDateString() === today.toDateString()
      ? "Today"
      : date.toDateString() === yesterday.toDateString() ? "Yesterday" : date.toLocaleDateString();
    (result[key] ||= []).push(notification);
    return result;
  }, {});

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">{t("notificationList.notifications")}</h3>
        {unreadCount > 0 && (
          <Button variant="ghost" size="sm" onClick={onMarkAllRead}>
            {t("notificationList.mark_all_read")}
          </Button>
        )}
      </div>

      {notifications.length === 0 ? (
        <div className="empty-state py-8">
          <div className="empty-state-icon">🔔</div>
          <p className="empty-state-title">{t("notificationList.no_notifications")}</p>
        </div>
      ) : (
        <div className="space-y-5">
          {Object.entries(groups).map(([date, items]) => <div key={date}>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{date}</p>
            <div className="space-y-1">{items.map((notification) => (
            <button
              key={notification.id}
              className={`w-full text-left p-3 rounded-md transition-colors hover:bg-accent ${
                !notification.isRead ? "bg-muted/30" : ""
              }`}
              onClick={() => { onMarkRead(notification.id); if (notification.link) navigate(notification.link); }}
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
          ))}</div></div>)}
        </div>
      )}
    </div>
  );
};
