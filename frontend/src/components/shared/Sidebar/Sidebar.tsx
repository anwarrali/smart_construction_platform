import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, ChevronDown, PanelLeftClose, PanelLeftOpen, Settings } from "lucide-react";

import { useRole } from "../../../hooks/useRole";
import { ROUTES } from "../../../utils/constants";
import { replaceProjectInPath } from "../../../utils/projectRoutes";
import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";
import { useLayoutStore } from "../../../app/store/layout.store";
import { StructIQMark } from "../../brand/StructIQLogo";
import { isItemActive, portfolioNavigation, projectNavigation, type NavGroup, type NavItem } from "./navigation";

interface SidebarProps {
  className?: string;
  /** Called after a destination is chosen — the mobile drawer closes itself. */
  onNavigate?: () => void;
  /** Icon-only rail. Ignored in the mobile drawer, which always has room. */
  collapsed?: boolean;
}

/* One entry. In the icon rail the label moves to the tooltip and to the
   accessible name, so the destination is never conveyed by the icon alone. */
const NavEntry = ({ item, active, collapsed, onNavigate }: { item: NavItem; active: boolean; collapsed: boolean; onNavigate?: () => void }) => {
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      title={collapsed ? item.label : undefined}
      aria-label={collapsed ? item.label : undefined}
      className={`nav-link${active ? " nav-link-active" : ""}${collapsed ? " justify-center px-0" : ""}`}
    >
      <Icon size={16} strokeWidth={active ? 2 : 1.6} className="shrink-0" aria-hidden />
      {!collapsed && <span className="truncate">{item.label}</span>}
    </Link>
  );
};

/**
 * The navigation rail. It draws the model from `navigation.ts`, already
 * filtered by the person's capabilities; it decides nothing about access.
 *
 * The same component serves a permanent rail from `lg` up — optionally
 * narrowed to icons — and an overlay drawer below it.
 */
export const Sidebar = ({ className = "", onNavigate, collapsed = false }: SidebarProps) => {
  const { t } = useTranslation();
  const { permissionsReady, hasCapability, orgRoleLabel, isInternal } = useRole();
  const workspace = useProjectWorkspace();
  const location = useLocation();
  const navigate = useNavigate();
  const { foldedGroups, toggleGroup, toggleRail } = useLayoutStore();

  /* Show a link until we positively know the capability is revoked. Before the
     permission list has arrived, hiding would make navigation flicker away and
     back; the pages and endpoints behind each link remain the real boundary
     either way. */
  const can = (code?: string) => !code || !permissionsReady || hasCapability(code);

  const groups: NavGroup[] = workspace.isProjectWorkspace
    ? projectNavigation(t, can, workspace.path)
    : portfolioNavigation(t, can, isInternal, workspace.worksInAProject);

  const active = (item: NavItem) => isItemActive(item, location.pathname, workspace.projectId);

  return (
    <aside
      className={`flex h-full shrink-0 flex-col overflow-hidden border-e border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-150 ${collapsed ? "w-rail-collapsed" : "w-rail max-w-[85vw]"} ${className}`}
      aria-label={t("nav.menu")}
    >
      {/* Identity strip — the same height as the top bar, so the two read as
          one frame around the working sheet. */}
      <div className={`flex h-bar shrink-0 items-center border-b border-sidebar-border ${collapsed ? "justify-center" : "gap-2.5 px-3.5"}`}>
        <StructIQMark size={22} frameClassName="text-white" />
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-semibold leading-none">
              <span className="text-white">Struct</span>
              <span className="text-brand-accent">IQ</span>
            </p>
            <p className="mt-1 truncate text-[10px] leading-none text-sidebar-foreground/60">{orgRoleLabel}</p>
          </div>
        )}
      </div>

      {workspace.isProjectWorkspace && !collapsed && (
        /* The project title block: which job this is, its state, and the
           switch to another one. Switching keeps you in the same module. */
        <div className="shrink-0 border-b border-sidebar-border px-3.5 py-3">
          <div className="flex items-center justify-between">
            <p className="label-caps text-[10px] text-sidebar-foreground/50">{t("nav.projectWorkspace")}</p>
            <span className="text-measured text-[10px] text-sidebar-foreground/45">
              {workspace.projectId?.slice(0, 8).toUpperCase()}
            </span>
          </div>
          <label className="sr-only" htmlFor="rail-project-switch">{t("common.switchActiveProject")}</label>
          <div className="relative mt-1.5">
            <select
              id="rail-project-switch"
              value={workspace.projectId}
              onChange={(event) => {
                navigate(`${replaceProjectInPath(location.pathname, event.target.value)}${location.search}`);
                onNavigate?.();
              }}
              className="h-8 w-full cursor-pointer appearance-none truncate border border-sidebar-border bg-sidebar-accent pe-7 ps-2.5 text-[13px] font-semibold text-sidebar-accent-foreground outline-none hover:border-sidebar-foreground/40 focus-visible:border-sidebar-mark"
            >
              {/* Until the list arrives, the current project is still named. */}
              {!workspace.assignedProjects.some((p) => p.id === workspace.projectId) && (
                <option value={workspace.projectId}>{workspace.project?.name || t("common.loadingProject")}</option>
              )}
              {workspace.assignedProjects.map((project) => (
                <option key={project.id} value={project.id}>{project.name}</option>
              ))}
            </select>
            <ChevronDown size={14} aria-hidden className="pointer-events-none absolute end-2 top-1/2 -translate-y-1/2 text-sidebar-foreground/60" />
          </div>
          <div className="mt-2 flex items-center gap-1.5 text-[11px] text-sidebar-foreground/65">
            <span aria-hidden className="h-1.5 w-1.5 bg-sidebar-mark" />
            <span className="truncate">
              {workspace.project?.status
                ? t(`project.status.${workspace.project.status}`, { defaultValue: workspace.project.status.replaceAll("_", " ") })
                : t("common.loading")}
            </span>
            <Link to={workspace.portfolioPath} onClick={onNavigate} className="ms-auto inline-flex items-center gap-1 text-sidebar-foreground/70 hover:text-white">
              <ArrowLeft size={12} className="rtl-flip" aria-hidden />
              {t("nav.allProjects")}
            </Link>
          </div>
        </div>
      )}

      {workspace.isProjectWorkspace && collapsed && (
        <div className="shrink-0 border-b border-sidebar-border py-1.5">
          <NavEntry
            item={{ id: "portfolio", to: workspace.portfolioPath, label: t("nav.allProjects"), icon: ArrowLeft }}
            active={false}
            collapsed
            onNavigate={onNavigate}
          />
        </div>
      )}

      <nav className="flex-1 overflow-y-auto py-2" aria-label={workspace.isProjectWorkspace ? t("nav.projectWorkspace") : t("nav.portfolio")}>
        {groups.map((group, index) => {
          const hasActive = group.items.some(active);
          // A folded group still opens while you are inside it — the current
          // location is never hidden from you.
          const folded = Boolean(group.label) && foldedGroups.includes(group.id) && !hasActive;
          return (
            <div key={group.id} className={index > 0 ? "mt-1.5" : ""}>
              {group.label && (collapsed
                ? <div aria-hidden className="mx-3 my-1.5 h-px bg-sidebar-border" />
                : (
                  <button
                    type="button"
                    onClick={() => toggleGroup(group.id)}
                    aria-expanded={!folded}
                    className="flex h-7 w-full cursor-pointer items-center gap-2 border-none bg-transparent px-3.5 text-start text-sidebar-foreground/50 hover:text-sidebar-foreground"
                  >
                    <span className="label-caps flex-1 truncate text-[10px]">{group.label}</span>
                    <ChevronDown size={12} aria-hidden className={`transition-transform ${folded ? "-rotate-90 rtl:rotate-90" : ""}`} />
                  </button>
                ))}
              {!folded && (
                <div>
                  {group.items.map((item) => (
                    <NavEntry key={item.id} item={item} active={active(item)} collapsed={collapsed} onNavigate={onNavigate} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className="shrink-0 border-t border-sidebar-border py-1.5">
        <NavEntry
          item={{ id: "settings", to: ROUTES.SETTINGS, label: t("common.profileSettings"), icon: Settings }}
          active={location.pathname === ROUTES.SETTINGS || location.pathname.startsWith(`${ROUTES.SETTINGS}/`)}
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
        {/* Narrowing the rail is a desktop affordance; the drawer has no use for it. */}
        {!onNavigate && (
          <button
            type="button"
            onClick={toggleRail}
            title={collapsed ? t("nav.expandRail") : t("nav.collapseRail")}
            aria-label={collapsed ? t("nav.expandRail") : t("nav.collapseRail")}
            className={`nav-link w-full cursor-pointer border-none bg-transparent text-sidebar-foreground/60 ${collapsed ? "justify-center px-0" : ""}`}
          >
            {collapsed
              ? <PanelLeftOpen size={16} strokeWidth={1.6} className="rtl-flip" aria-hidden />
              : <PanelLeftClose size={16} strokeWidth={1.6} className="rtl-flip" aria-hidden />}
            {!collapsed && <span className="truncate">{t("nav.collapseRail")}</span>}
          </button>
        )}
      </div>
    </aside>
  );
};
