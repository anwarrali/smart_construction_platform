import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { Bell, ChevronDown, LogOut, Menu, Mic, Settings } from "lucide-react";
import { NotificationDropdown } from "../NotificationDropdown";
import { LanguageSwitcher } from "../LanguageSwitcher";
import { ThemeSwitcher } from "../ThemeSwitcher";
import { Breadcrumbs } from "../Breadcrumbs/Breadcrumbs";
import { useAuth } from "../../../hooks/useAuth";
import { useRole } from "../../../hooks/useRole";
import { useNotificationStore } from "../../../app/store/notification.store";
import { useRealtimeRefresh } from "../../../hooks/useRealtimeRefresh";
import { ROUTES } from "../../../utils/constants";
import api from "../../../services/api";
import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";

/* A square tool button for the bar. One definition, so every tool in the bar
   has the same footprint, hover and focus. */
const toolClass =
  "relative inline-flex h-bar w-10 shrink-0 cursor-pointer items-center justify-center border-none bg-transparent text-foreground/65 outline-none transition-colors hover:bg-muted hover:text-foreground";

/**
 * The top bar: where you are on the left, the tools that apply here on the
 * right. Project-only tools appear only inside a project, and only when the
 * person's capabilities allow the page behind them.
 */
export const Topbar = ({ onOpenMenu }: { onOpenMenu?: () => void }) => {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { unreadCount, setUnreadCount } = useNotificationStore();
  const { roleLabel, hasCapability, permissionsReady } = useRole();
  const navigate = useNavigate();
  const [isNotificationOpen, setIsNotificationOpen] = useState(false);
  const [isAccountOpen, setIsAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);
  const workspace = useProjectWorkspace();

  const fetchUnreadCount = useCallback(async () => {
    try {
      const { count } = await api.notifications.getUnreadCount();
      setUnreadCount(count);
    } catch {
      // The badge is a hint; a failed count leaves the last known one.
    }
  }, [setUnreadCount]);

  useEffect(() => {
    fetchUnreadCount();
  }, [fetchUnreadCount]);

  // CREATED when somebody else acts, UPDATED when this user reads a
  // notification in another tab and the badge must drop here too.
  useRealtimeRefresh(
    ["NOTIFICATION_CREATED", "NOTIFICATION_UPDATED"],
    fetchUnreadCount,
  );

  // The account menu closes on an outside click or Escape, like any menu.
  useEffect(() => {
    if (!isAccountOpen) return;
    const onPointer = (event: MouseEvent) => {
      if (!accountRef.current?.contains(event.target as Node)) setIsAccountOpen(false);
    };
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setIsAccountOpen(false); };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [isAccountOpen]);

  const signOut = () => {
    logout();
    navigate(ROUTES.HOME);
  };

  const initials =
    user?.fullName
      ?.split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2) || "U";

  // Same rule as the voice assistant's route guard.
  const showVoice = workspace.isProjectWorkspace && permissionsReady && hasCapability("task.view");

  return (
    <header className="sticky top-0 z-30 flex h-bar shrink-0 items-center justify-between border-b bg-card">
      <div className="flex min-w-0 flex-1 items-center gap-2 ps-1 lg:ps-5">
        {/* The rail is hidden below `lg`; this is the way to it there. */}
        <button
          type="button"
          onClick={onOpenMenu}
          aria-label={t("nav.openMenu")}
          title={t("nav.openMenu")}
          className={`${toolClass} lg:hidden`}
        >
          <Menu size={18} />
        </button>
        <Breadcrumbs />
      </div>

      <div className="flex h-full shrink-0 items-center">
        {showVoice && (
          <Link
            to={workspace.path("voice-assistant")}
            aria-label={t("nav.voiceAssistant")}
            title={t("nav.voiceAssistant")}
            className={toolClass}
          >
            <Mic size={17} />
          </Link>
        )}

        <div className="relative">
          <button
            type="button"
            onClick={() => setIsNotificationOpen(!isNotificationOpen)}
            aria-label={unreadCount > 0 ? `${t("common.notifications")} (${unreadCount})` : t("common.notifications")}
            aria-expanded={isNotificationOpen}
            className={toolClass}
          >
            <Bell size={17} />
            {unreadCount > 0 && (
              <span className="absolute end-1.5 top-2 flex h-4 min-w-4 items-center justify-center bg-state-overdue px-1 text-[10px] font-semibold leading-none text-white">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>
          <NotificationDropdown
            isOpen={isNotificationOpen}
            onClose={() => setIsNotificationOpen(false)}
          />
        </div>

        <span aria-hidden className="mx-1 hidden h-5 w-px bg-border sm:block" />
        <LanguageSwitcher className="hidden sm:inline-flex" />
        <ThemeSwitcher compact />
        <span aria-hidden className="mx-1 h-5 w-px bg-border" />

        <div ref={accountRef} className="relative h-full">
          <button
            type="button"
            onClick={() => setIsAccountOpen((open) => !open)}
            aria-haspopup="menu"
            aria-expanded={isAccountOpen}
            aria-label={t("nav.userMenu")}
            className="flex h-full cursor-pointer items-center gap-2.5 border-none bg-transparent pe-3 ps-2 text-start outline-none transition-colors hover:bg-muted lg:pe-5"
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center bg-sidebar text-[11px] font-semibold text-white">
              {initials}
            </span>
            <span className="hidden min-w-0 md:block">
              <span className="block max-w-[11rem] truncate text-[13px] font-medium leading-tight">{user?.fullName || t("common.account")}</span>
              <span className="block max-w-[11rem] truncate text-[11px] leading-tight text-muted-foreground">{roleLabel}</span>
            </span>
            <ChevronDown size={14} className="hidden text-muted-foreground md:block" aria-hidden />
          </button>
          {isAccountOpen && (
            <div role="menu" className="dropdown-content absolute end-0 top-full mt-px w-64">
              <div className="border-b px-3 pb-2.5 pt-2">
                <p className="truncate text-[13px] font-semibold">{user?.fullName || t("common.account")}</p>
                {user?.email && <p className="truncate text-xs text-muted-foreground force-ltr">{user.email}</p>}
                <p className="mt-1 text-[11px] text-muted-foreground">{roleLabel}</p>
              </div>
              <Link role="menuitem" to={ROUTES.SETTINGS} onClick={() => setIsAccountOpen(false)} className="dropdown-item text-foreground">
                <Settings size={14} aria-hidden /> {t("common.profileSettings")}
              </Link>
              <LanguageSwitcher className="dropdown-item h-auto justify-start sm:hidden" />
              <button role="menuitem" type="button" onClick={signOut} className="dropdown-item border-none bg-transparent text-destructive">
                <LogOut size={14} className="rtl-flip" aria-hidden /> {t("common.logout")}
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
