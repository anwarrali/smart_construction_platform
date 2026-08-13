import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Sun, Moon, Bell, FolderKanban } from "lucide-react";
import { Badge } from "../../ui/Badge";
import { NotificationDropdown } from "../NotificationDropdown";
import { LanguageSwitcher } from "../LanguageSwitcher";
import { useAuth } from "../../../hooks/useAuth";
import { useTheme } from "../../../hooks/useTheme";
import { useRole } from "../../../hooks/useRole";
import { useNotificationStore } from "../../../app/store/notification.store";
import { ROUTES } from "../../../utils/constants";
import api from "../../../services/api";
import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";
import { replaceProjectInPath } from "../../../utils/projectRoutes";
import { useLocation } from "react-router-dom";

export const Topbar = () => {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { unreadCount, setUnreadCount } = useNotificationStore();
  const { roleLabel } = useRole();
  const navigate = useNavigate();
  const location = useLocation();
  const [isNotificationOpen, setIsNotificationOpen] = useState(false);
  const workspace = useProjectWorkspace();

  // Fetch real unread count from backend on mount
  const fetchUnreadCount = useCallback(async () => {
    try {
      const { count } = await api.notifications.getUnreadCount();
      setUnreadCount(count);
    } catch {
      // silently fail
    }
  }, [setUnreadCount]);

  useEffect(() => {
    fetchUnreadCount();
  }, [fetchUnreadCount]);

  const initials =
    user?.fullName
      ?.split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2) || "U";

  return (
    <header className="h-16 border-b bg-background flex items-center justify-between px-6">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {workspace.isProjectWorkspace && <>
          <FolderKanban size={17} className="shrink-0 text-primary" />
          <div className="min-w-0"><p className="text-[10px] uppercase tracking-wider text-muted-foreground">{t("common.activeProject")}</p><p className="truncate text-sm font-semibold">{workspace.project?.name || t("common.loadingProject")}</p></div>
          <select aria-label={t("common.switchActiveProject")} value={workspace.projectId} onChange={(event) => {
            navigate(`${replaceProjectInPath(location.pathname, event.target.value)}${location.search}`);
          }} className="ml-2 max-w-56 rounded-md border bg-background px-2 py-1.5 text-xs">
            {workspace.assignedProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </>}
      </div>

      <div className="flex h-full items-center gap-3">
        <LanguageSwitcher />
        <button
          onClick={toggleTheme}
          aria-label={theme === "dark" ? t("common.switchToLight") : t("common.switchToDark")}
          title={theme === "dark" ? t("common.switchToLight") : t("common.switchToDark")}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-foreground/70 hover:bg-muted hover:text-foreground transition-colors cursor-pointer border-none outline-none"
          style={{ background: "none" }}
        >
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </button>

        <div className="relative inline-flex h-9 w-9 shrink-0 items-center justify-center">
          <button
            onClick={() => setIsNotificationOpen(!isNotificationOpen)}
            aria-label={t("common.notifications")}
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-foreground/70 hover:bg-muted hover:text-foreground transition-colors cursor-pointer border-none outline-none"
            style={{ background: "none" }}
          >
            <span className="relative inline-flex">
              <Bell size={18} />
              {unreadCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 bg-red-500 text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center font-semibold">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </span>
          </button>
          <NotificationDropdown
            isOpen={isNotificationOpen}
            onClose={() => setIsNotificationOpen(false)}
          />
        </div>

        <div className="flex items-center gap-2 pl-3 border-l">
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-sm font-medium">
            {initials}
          </div>
          <div className="hidden md:block">
            <p className="text-sm font-medium">{user?.fullName || t("roles.worker")}</p>
            <Badge variant="info" size="sm">
              {roleLabel}
            </Badge>
          </div>
        </div>

        <button
          className="btn-ghost btn-sm"
          onClick={() => {
            logout();
            navigate(ROUTES.HOME);
          }}
        >
          {t("common.logout")}
        </button>
      </div>
    </header>
  );
};
