import { Button } from "../../../components/ui/Button";
import { useTranslation } from "react-i18next";
import { Loader } from "../../../components/ui/Loader";
import { timeAgo } from "../../../utils/date";
import { formatDate } from "../../../utils/dates";
import { useNavigate } from "react-router-dom";

interface Notification {
  id: string;
  title: string;
  message: string;
  type: string;
  isRead: boolean;
  link?: string;
  createdAt: string;
  priority?: string;
  category?: string;
  requiresAction?: boolean;
  messageKey?: string;
  messageParamsJson?: Record<string, unknown>;
}

/* Only the two loud levels get a visible badge. Marking every ordinary
   notification "Normal" would make the list noisier, not clearer — the point
   of the badge is that something stands out from the ordinary. */
const priorityBadge: Record<string, { className: string; labelKey: string }> = {
  IMPORTANT: { className: "bg-wash-review text-state-review", labelKey: "notificationList.priority.important" },
  CRITICAL: { className: "bg-wash-overdue text-state-overdue", labelKey: "notificationList.priority.critical" },
};

/* A left border keeps the severity readable while scanning, without competing
   with the unread dot. */
const priorityAccent: Record<string, string> = {
  IMPORTANT: "border-s-2 border-state-review",
  CRITICAL: "border-s-2 border-state-overdue",
};

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
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  if (isLoading) return <Loader text="Loading notifications..." />;

  const unreadCount = notifications.filter((n) => !n.isRead).length;
  const groups = notifications.reduce<Record<string, Notification[]>>((result, notification) => {
    const date = new Date(notification.createdAt);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);
    // Group headings follow the selected language, not the browser locale.
    const key = date.toDateString() === today.toDateString()
      ? t("common.today")
      : date.toDateString() === yesterday.toDateString() ? t("common.yesterday") : formatDate(notification.createdAt);
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
              } ${priorityAccent[notification.priority || ""] || ""}`}
              onClick={() => { onMarkRead(notification.id); if (notification.link) navigate(notification.link); }}
            >
              <div className="flex items-start gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium truncate">
                      {/* The server sends a localizable key plus params, with
                          the rendered English kept as the fallback for older
                          rows and any key this build does not yet know. */}
                      {notification.messageKey
                        ? t(`notification.${notification.messageKey}.title`, {
                            ...(notification.messageParamsJson || {}),
                            defaultValue: notification.title,
                          })
                        : notification.title}
                    </p>
                    {priorityBadge[notification.priority || ""] && (
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${priorityBadge[notification.priority!].className}`}>
                        {t(priorityBadge[notification.priority!].labelKey)}
                      </span>
                    )}
                    {notification.category === "REMINDERS" && (
                      <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                        {t("notificationList.reminder")}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {notification.messageKey
                      ? t(`notification.${notification.messageKey}.body`, {
                          ...(notification.messageParamsJson || {}),
                          defaultValue: notification.message,
                        })
                      : notification.message}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {/* `timeAgo` has always accepted a locale; this list just
                        never passed one, so every relative timestamp rendered
                        in English even in Arabic. */}
                    {timeAgo(notification.createdAt, i18n.language?.startsWith("ar") ? "ar" : "en")}
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
