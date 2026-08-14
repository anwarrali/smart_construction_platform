import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Bell, LogOut, Menu } from "lucide-react";
import { Badge } from "../../ui/Badge";
import { NotificationDropdown } from "../NotificationDropdown";
import { LanguageSwitcher } from "../LanguageSwitcher";
import { ThemeSwitcher } from "../ThemeSwitcher";
import { useAuth } from "../../../hooks/useAuth";
import { useRole } from "../../../hooks/useRole";
import { useNotificationStore } from "../../../app/store/notification.store";
import { ROUTES } from "../../../utils/constants";
import api from "../../../services/api";
import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";
import { replaceProjectInPath } from "../../../utils/projectRoutes";
import { useLocation } from "react-router-dom";

export const Topbar = ({ onOpenMenu }: { onOpenMenu?: () => void }) => {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
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
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-2 border-b bg-background/85 px-3 backdrop-blur-md sm:gap-4 sm:px-5 md:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {/* The rail is hidden below `lg`, so this is the only way to the
            navigation on a phone or a narrow window. */}
        <button
          type="button"
          onClick={onOpenMenu}
          aria-label={t("nav.openMenu")}
          title={t("nav.openMenu")}
          className="-ms-1 inline-flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-control border-none text-foreground/70 outline-none transition-colors hover:bg-muted hover:text-foreground lg:hidden"
          style={{ background: "none" }}
        >
          <Menu size={20} />
        </button>
        {workspace.isProjectWorkspace && <>
          <span aria-hidden className="h-8 w-[3px] shrink-0 rounded-[1px] bg-accent" />
          <div className="min-w-0">
            <p className="label-caps text-muted-foreground/70">{t("common.activeProject")}</p>
            <p className="truncate text-sm font-semibold tracking-heading">{workspace.project?.name || t("common.loadingProject")}</p>
          </div>
          <select aria-label={t("common.switchActiveProject")} value={workspace.projectId} onChange={(event) => {
            navigate(`${replaceProjectInPath(location.pathname, event.target.value)}${location.search}`);
          }} className="ms-2 hidden max-w-56 rounded-control border bg-card px-2.5 py-1.5 text-xs transition-colors hover:border-border-strong sm:block">
            {workspace.assignedProjects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </>}
      </div>

      <div className="flex h-full shrink-0 items-center gap-1 sm:gap-3">
        <LanguageSwitcher />
        {/* Light / Dark / System — the same control the landing page uses. */}
        <ThemeSwitcher compact />

        <div className="relative inline-flex h-9 w-9 shrink-0 items-center justify-center">
          <button
            onClick={() => setIsNotificationOpen(!isNotificationOpen)}
            aria-label={t("common.notifications")}
            className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-control border-none text-foreground/65 outline-none transition-colors hover:bg-muted hover:text-foreground"
            style={{ background: "none" }}
          >
            <span className="relative inline-flex">
              <Bell size={18} />
              {unreadCount > 0 && (
                <span className="absolute -top-1.5 -end-1.5 flex h-4 min-w-4 items-center justify-center rounded-chip bg-state-overdue px-1 text-[10px] font-semibold text-white">
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

        <div className="flex items-center gap-2.5 border-s ps-2 sm:ps-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-control bg-primary text-xs font-semibold text-primary-foreground">
            {initials}
          </div>
          <div className="hidden md:block">
            <p className="text-sm font-medium">{user?.fullName || t("roles.worker")}</p>
            <Badge variant="neutral" size="sm">
              {roleLabel}
            </Badge>
          </div>
        </div>

        {/* Kept on every screen size — signing out is not optional on a phone.
            Below `sm` it becomes an icon so the bar stops overflowing. */}
        <button
          className="btn-ghost btn-sm hidden sm:inline-flex"
          onClick={() => {
            logout();
            navigate(ROUTES.HOME);
          }}
        >
          {t("common.logout")}
        </button>
        <button
          type="button"
          aria-label={t("common.logout")}
          title={t("common.logout")}
          onClick={() => {
            logout();
            navigate(ROUTES.HOME);
          }}
          className="inline-flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-control border-none text-foreground/65 outline-none transition-colors hover:bg-muted hover:text-foreground sm:hidden"
          style={{ background: "none" }}
        >
          <LogOut size={18} className="rtl-flip" />
        </button>
      </div>
    </header>
  );
};
