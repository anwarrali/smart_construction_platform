import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card } from "../../../components/ui/Card";
import { Button } from "../../../components/ui/Button";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { NotificationList } from "../components/NotificationList";
import { useNotifications } from "../../../hooks/useNotifications";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import { useDebounce } from "../../../hooks/useDebounce";

export const NotificationsPage = () => {
  const { t } = useTranslation();
  const { notifications, isLoading, error, pagination, fetchNotifications, markAsRead, markAllAsRead } = useNotifications();
  const workspace = useProjectWorkspace();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [readFilter, setReadFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const debouncedSearch = useDebounce(search);

  useEffect(() => {
    setPage(1);
  }, [workspace.projectId, debouncedSearch, readFilter, typeFilter]);

  useEffect(() => {
    fetchNotifications(page, workspace.projectId, {
      unread: readFilter === "unread" ? true : readFilter === "read" ? false : undefined,
      notificationType: typeFilter || undefined,
      search: debouncedSearch || undefined,
    });
  }, [fetchNotifications, page, workspace.projectId, debouncedSearch, readFilter, typeFilter]);

  const handleMarkAllRead = async () => {
    await markAllAsRead(workspace.projectId);
    await fetchNotifications(page, workspace.projectId, {
      unread: readFilter === "unread" ? true : readFilter === "read" ? false : undefined,
      notificationType: typeFilter || undefined,
      search: debouncedSearch || undefined,
    });
  };

  return (
    <div className="page-container max-w-4xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold">{workspace.project ? "Project Notifications" : "Notification Center"}</h1>
        <p className="text-sm text-muted-foreground">{workspace.project?.name || "Search, filter, and manage real system events."}</p>
      </div>

      <Card className="grid gap-3 p-4 md:grid-cols-[1fr_180px_210px]">
        <Input placeholder={t("notificationsPage.search_notifications")} value={search} onChange={(event) => setSearch(event.target.value)} />
        <Select value={readFilter} onChange={(event) => setReadFilter(event.target.value)} options={[
          { value: "", label: "All notifications" },
          { value: "unread", label: "Unread only" },
          { value: "read", label: "Read only" },
        ]} />
        <Select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} options={[
          { value: "", label: "All event types" },
          { value: "task_assigned", label: "Task assignments" },
          { value: "task_updated", label: "Task and issue updates" },
          { value: "task_overdue", label: "Overdue tasks" },
          { value: "design_change", label: "Design changes" },
          { value: "approval_request", label: "Approvals" },
          { value: "report_ready", label: "Site reports" },
          { value: "message", label: "Messages" },
          { value: "system", label: "Project and document events" },
        ]} />
      </Card>

      <Card>
        {error && <p className="mb-3 rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
        <NotificationList notifications={notifications} isLoading={isLoading} onMarkRead={markAsRead} onMarkAllRead={handleMarkAllRead} />
      </Card>

      {pagination.totalPages > 1 && <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Page {pagination.page} of {pagination.totalPages} · {pagination.total} notifications</p>
        <div className="flex gap-2"><Button variant="outline" size="sm" disabled={page <= 1 || isLoading} onClick={() => setPage((value) => value - 1)}>{t("notificationsPage.previous")}</Button><Button variant="outline" size="sm" disabled={page >= pagination.totalPages || isLoading} onClick={() => setPage((value) => value + 1)}>{t("notificationsPage.next")}</Button></div>
      </div>}
    </div>
  );
};
