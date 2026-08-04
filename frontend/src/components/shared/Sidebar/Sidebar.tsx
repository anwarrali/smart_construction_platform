import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  FolderKanban,
  CheckSquare,
  FileText,
  Bell,
  Users,
  Settings,
  AlertTriangle,
  Pencil,
  ClipboardCheck,
  Crown,
  CalendarRange,
  ArrowLeft,
  Flag,
  MessageSquare,
  Building2,
  Images,
  Mic2,
  Boxes,
  BrainCircuit,
  ListChecks,
  CalendarDays,
} from "lucide-react";
import { useRole } from "../../../hooks/useRole";
import { ROUTES } from "../../../utils/constants";
import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";

/* ─── Nav item types ─── */
interface NavItem {
  to: string;
  label: string;
  icon: React.ElementType;
}

const coreLinks: NavItem[] = [
  { to: ROUTES.DASHBOARD,    label: "Dashboard",    icon: LayoutDashboard },
  { to: ROUTES.PROJECTS,     label: "Projects",     icon: FolderKanban    },
  { to: ROUTES.TASKS,        label: "Tasks",        icon: CheckSquare     },
  { to: ROUTES.DOCUMENTS,    label: "Documents",    icon: FileText        },
  { to: ROUTES.SITE_REPORTS, label: "Site Reports", icon: ClipboardCheck  },
];

const operationsLinks: NavItem[] = [
  { to: ROUTES.ISSUES,         label: "Issues",         icon: AlertTriangle },
  { to: ROUTES.DESIGN_CHANGES, label: "Design Changes", icon: Pencil        },
  { to: ROUTES.TEAM,            label: "Team",           icon: Users          },
];

const adminLinks: NavItem[] = [
  { to: ROUTES.ADMIN_DASHBOARD, label: "Dashboard", icon: LayoutDashboard },
  { to: ROUTES.USERS, label: "Users", icon: Users },
  { to: ROUTES.PROJECTS, label: "Projects", icon: FolderKanban },
  { to: ROUTES.ADMIN_TEAMS, label: "Project Teams", icon: Users },
  { to: ROUTES.SETTINGS, label: "Settings", icon: Settings },
];

const bottomLinks: NavItem[] = [
  { to: ROUTES.MY_ACTIONS, label: "My Actions", icon: ListChecks },
  { to: ROUTES.REQUESTS, label: "Requests", icon: MessageSquare },
  { to: ROUTES.SCHEDULE, label: "Schedule", icon: CalendarDays },
  { to: ROUTES.MESSAGES, label: "Messages", icon: MessageSquare },
  { to: ROUTES.NOTIFICATIONS, label: "Notifications", icon: Bell     },
  { to: ROUTES.SETTINGS,      label: "Settings",      icon: Settings },
];

/* ─── NavLink class factory ─── */
const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150 group
   ${isActive
     ? "bg-sidebar-accent text-sidebar-accent-foreground"
     : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
   }`;

/* ─── Section label ─── */
const SectionLabel = ({ children }: { children: React.ReactNode }) => (
  <p className="px-3 mt-5 mb-1 text-[10px] font-semibold uppercase tracking-widest text-sidebar-foreground/30 select-none">
    {children}
  </p>
);

export const Sidebar = () => {
  const { isAdmin, isOwner, role, isConsultantEngineer } = useRole();
  const workspace = useProjectWorkspace();
  const projectLinks: NavItem[] = workspace.projectId ? [
    { to: workspace.path("dashboard"), label: "Project Dashboard", icon: LayoutDashboard },
    { to: workspace.path("tasks"), label: "Tasks", icon: CheckSquare },
    { to: workspace.path("documents"), label: "Documents", icon: FileText },
    { to: workspace.path("ifc"), label: "IFC Intelligence", icon: Boxes },
    { to: workspace.path("ai-intelligence"), label: "AI Intelligence", icon: BrainCircuit },
    { to: workspace.path("evidence"), label: "Evidence Photos", icon: Images },
    { to: workspace.path("site-reports"), label: "Site Reports", icon: ClipboardCheck },
    { to: workspace.path("issues"), label: "Issues", icon: AlertTriangle },
    { to: workspace.path("design-changes"), label: "Design Changes", icon: Pencil },
    { to: workspace.path("team"), label: "Team", icon: Users },
    { to: workspace.path("schedule"), label: "Schedule / Gantt", icon: CalendarRange },
    { to: workspace.path("milestones"), label: "Milestones", icon: Flag },
    { to: workspace.path("messages"), label: "Messages", icon: MessageSquare },
    { to: ROUTES.MY_ACTIONS, label: "My Actions", icon: ListChecks },
  ] : [];
  const engineerProjectLinks: NavItem[] = workspace.projectId ? [
    { to: workspace.path("dashboard"), label: "Dashboard", icon: LayoutDashboard },
    { to: workspace.path("tasks"), label: "My Tasks", icon: CheckSquare },
    { to: workspace.path("site-reports"), label: "Site Reports", icon: ClipboardCheck },
    { to: workspace.path("issues"), label: "Issues", icon: AlertTriangle },
    { to: workspace.path("documents"), label: "Documents", icon: FileText },
    { to: workspace.path("ifc"), label: "IFC Intelligence", icon: Boxes },
    { to: workspace.path("ai-intelligence"), label: "AI Intelligence", icon: BrainCircuit },
    { to: workspace.path("evidence"), label: "Evidence Photos", icon: Images },
    { to: workspace.path("voice-reports"), label: "Voice Reports", icon: Mic2 },
    { to: workspace.path("notifications"), label: "Notifications", icon: Bell },
    { to: ROUTES.MY_ACTIONS, label: "My Actions", icon: ListChecks },
    { to: ROUTES.SCHEDULE, label: "Schedule", icon: CalendarDays },
  ] : [];
  const consultantProjectLinks: NavItem[] = workspace.projectId ? [
    { to: workspace.path("dashboard"), label: "Dashboard", icon: LayoutDashboard },
    { to: workspace.path("reviews"), label: "Pending Reviews", icon: ClipboardCheck },
    { to: workspace.path("history"), label: "Review History", icon: CalendarRange },
    { to: workspace.path("documents"), label: "Documents", icon: FileText },
    { to: workspace.path("ifc"), label: "IFC Intelligence", icon: Boxes },
    { to: workspace.path("ai-intelligence"), label: "AI Intelligence", icon: BrainCircuit },
    { to: workspace.path("evidence"), label: "Evidence Photos", icon: Images },
    { to: workspace.path("site-reports"), label: "Site Reports", icon: CheckSquare },
    { to: workspace.path("issues"), label: "Issues", icon: AlertTriangle },
    { to: workspace.path("design-changes"), label: "Design Changes", icon: Pencil },
    { to: workspace.path("notifications"), label: "Notifications", icon: Bell },
  ] : [];
  const visibleCoreLinks = coreLinks.filter(({ to }) => {
    if (isOwner) return ([ROUTES.DOCUMENTS, ROUTES.SITE_REPORTS] as string[]).includes(to);
    if (role === "consultant") return ([ROUTES.DASHBOARD, ROUTES.PROJECTS, ROUTES.TASKS, ROUTES.DOCUMENTS] as string[]).includes(to);
    if (role === "engineer") return ([ROUTES.DASHBOARD, ROUTES.PROJECTS, ROUTES.TASKS, ROUTES.DOCUMENTS, ROUTES.SITE_REPORTS] as string[]).includes(to);
    return true;
  });
  const routedCoreLinks = visibleCoreLinks.map((item) =>
    role === "project_manager" && item.to === ROUTES.PROJECTS
      ? { ...item, to: ROUTES.PM_PROJECTS }
      : item,
  );
  const visibleOperationsLinks = operationsLinks.filter(({ to }) => {
    if (isOwner) return ([ROUTES.DESIGN_CHANGES] as string[]).includes(to);
    if (role === "consultant") return ([ROUTES.ISSUES, ROUTES.DESIGN_CHANGES] as string[]).includes(to);
    if (role !== "project_manager" && to === ROUTES.TEAM) return false;
    if (role === "engineer") return ([ROUTES.ISSUES, ROUTES.SITE_REPORTS] as string[]).includes(to);
    return true;
  });
  const visibleBottomLinks = bottomLinks.filter(({ to }) => {
    if (role === "worker") return ([ROUTES.MESSAGES, ROUTES.NOTIFICATIONS, ROUTES.SETTINGS] as string[]).includes(to);
    return true;
  });

  return (
    <aside className="w-64 flex flex-col h-screen bg-sidebar border-r border-sidebar-border overflow-hidden shrink-0">
      {/* ── Logomark ── */}
      <div className="h-16 flex items-center px-5 border-b border-sidebar-border gap-3">
        <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center shrink-0">
          <span className="text-white text-sm font-black">C</span>
        </div>
        <div className="leading-none">
          <span className="text-sm font-bold text-sidebar-accent-foreground">ConstroPlatform</span>
          {role && (
            <p className="text-[10px] text-sidebar-foreground/40 mt-0.5 capitalize">
              {role.replace(/_/g, " ")}
            </p>
          )}
        </div>
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5 scrollbar-thin">
        {isAdmin ? (
          <>
            <SectionLabel>System</SectionLabel>
            {adminLinks.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} className={linkClass}>
                {({ isActive }) => (
                  <>
                    <Icon size={15} className={isActive ? "" : "opacity-60 group-hover:opacity-100"} />
                    <span>{label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </>
        ) : role === "project_manager" ? (
          workspace.isProjectWorkspace ? <>
            <div className="mx-3 mb-3 rounded-lg border border-sidebar-border bg-sidebar-accent/40 p-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">Current Project</p>
              <p className="mt-1 truncate text-sm font-semibold text-sidebar-accent-foreground">{workspace.project?.name || (workspace.isLoading ? "Loading…" : "Project workspace")}</p>
            </div>
            <NavLink to={ROUTES.PM_PROJECTS} className={linkClass}><ArrowLeft size={15} /><span>Back to Projects</span></NavLink>
            <SectionLabel>Project Workspace</SectionLabel>
            {projectLinks.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} className={linkClass}>
              {({ isActive }) => <><Icon size={15} className={isActive ? "" : "opacity-60 group-hover:opacity-100"} /><span>{label}</span></>}
            </NavLink>)}
          </> : <>
            <SectionLabel>Portfolio</SectionLabel>
            <NavLink to={ROUTES.DASHBOARD} className={linkClass}><LayoutDashboard size={15} /><span>Overall Dashboard</span></NavLink>
            <NavLink to={ROUTES.PM_PROJECTS} className={linkClass}><FolderKanban size={15} /><span>Projects</span></NavLink>
          </>
        ) : role === "engineer" ? (
          workspace.isProjectWorkspace ? <>
            <div className="mx-3 mb-3 rounded-lg border border-sidebar-border bg-sidebar-accent/40 p-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">Current Project</p>
              <p className="mt-1 truncate text-sm font-semibold text-sidebar-accent-foreground">{workspace.project?.name || (workspace.isLoading ? "Loading…" : "Project workspace")}</p>
            </div>
            <NavLink to={isConsultantEngineer ? ROUTES.CONSULTANT_PROJECTS : ROUTES.ENGINEER_PROJECTS} className={linkClass}><ArrowLeft size={15} /><span>Back to My Projects</span></NavLink>
            <SectionLabel>{isConsultantEngineer ? "Supervision Workspace" : "Execution Workspace"}</SectionLabel>
            {(isConsultantEngineer ? consultantProjectLinks : engineerProjectLinks).map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} className={linkClass}>
              {({ isActive }) => <><Icon size={15} className={isActive ? "" : "opacity-60 group-hover:opacity-100"} /><span>{label}</span></>}
            </NavLink>)}
          </> : <>
            <SectionLabel>{isConsultantEngineer ? "Supervision" : "Execution"}</SectionLabel>
            <NavLink to={isConsultantEngineer ? ROUTES.CONSULTANT_PROJECTS : ROUTES.ENGINEER_PROJECTS} className={linkClass}><FolderKanban size={15} /><span>My Projects</span></NavLink>
          </>
        ) : (
          <>
        {/* Owner shortcut */}
        {isOwner && (
          <>
            <SectionLabel>Executive</SectionLabel>
            <NavLink to={ROUTES.OWNER_DASHBOARD} className={linkClass}>
              {({ isActive }) => (
                <>
                  <Crown size={15} className={isActive ? "" : "opacity-60 group-hover:opacity-100"} />
                  <span>Project Dashboard</span>
                </>
              )}
            </NavLink>
            <NavLink to={ROUTES.EXECUTIVE_OVERVIEW} className={linkClass}>
              {({ isActive }) => (
                <>
                  <Building2 size={15} className={isActive ? "" : "opacity-60 group-hover:opacity-100"} />
                  <span>Executive Overview</span>
                </>
              )}
            </NavLink>
          </>
        )}

        <SectionLabel>Core</SectionLabel>
        {routedCoreLinks.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className={linkClass}>
            {({ isActive }) => (
              <>
                <Icon size={15} className={isActive ? "" : "opacity-60 group-hover:opacity-100"} />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}

        <SectionLabel>Operations</SectionLabel>
        {visibleOperationsLinks.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className={linkClass}>
            {({ isActive }) => (
              <>
                <Icon size={15} className={isActive ? "" : "opacity-60 group-hover:opacity-100"} />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}

          </>
        )}
      </nav>

      {/* ── Bottom links ── */}
      {!isAdmin && role !== "engineer" && <div className="px-3 py-3 border-t border-sidebar-border space-y-0.5">
        {visibleBottomLinks.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={role === "project_manager" && workspace.projectId && to === ROUTES.NOTIFICATIONS ? workspace.path("notifications") : role === "project_manager" && workspace.projectId && to === ROUTES.MESSAGES ? workspace.path("messages") : to} className={linkClass}>
            {({ isActive }) => (
              <>
                <Icon size={15} className={isActive ? "" : "opacity-60 group-hover:opacity-100"} />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>}
      {!isAdmin && role === "engineer" && <div className="px-3 py-3 border-t border-sidebar-border space-y-0.5">
        <NavLink to={ROUTES.SETTINGS} className={linkClass}><Settings size={15} /><span>Profile</span></NavLink>
      </div>}
    </aside>
  );
};
