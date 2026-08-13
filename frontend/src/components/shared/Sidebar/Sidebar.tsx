import { NavLink } from "react-router-dom";
import {
  Activity, AlertTriangle, ArrowLeft, Bell, Boxes, BrainCircuit, Building2,
  CalendarDays, CheckSquare, ClipboardCheck, FileText, FolderKanban, Images,
  LayoutDashboard, ListChecks, MessageSquare, Mic2, Pencil, Settings, Users,
} from "lucide-react";

import { useRole } from "../../../hooks/useRole";
import { ROUTES } from "../../../utils/constants";
import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";

type NavItem = { to:string; label:string; icon:React.ElementType };

const linkClass = ({ isActive }: { isActive:boolean }) =>
  `group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive
    ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-sm"
    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"}`;

const SectionLabel = ({ children }: { children:React.ReactNode }) =>
  <p className="mb-1 mt-5 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-sidebar-foreground/35">{children}</p>;

const LinkList = ({ items }: { items:NavItem[] }) => <>{items.map(({to,label,icon:Icon}) =>
  <NavLink key={`${to}-${label}`} to={to} className={linkClass}>
    {({isActive})=><><Icon size={16} className={isActive?"":"opacity-65"}/><span>{label}</span></>}
  </NavLink>)}</>;

export const Sidebar = () => {
  const { role, isAdmin, isOwner, isProjectManager, isConsultantEngineer } = useRole();
  const workspace = useProjectWorkspace();

  const globalByRole:Record<string,NavItem[]> = {
    admin: [
      {to:ROUTES.ADMIN_DASHBOARD,label:"Platform Dashboard",icon:LayoutDashboard},
      {to:ROUTES.PROJECTS,label:"Projects",icon:FolderKanban},
      {to:ROUTES.USERS,label:"People & Access",icon:Users},
      {to:ROUTES.ADMIN_TEAMS,label:"Project Teams",icon:Building2},
    ],
    project_manager: [
      {to:ROUTES.DASHBOARD,label:"Portfolio Dashboard",icon:LayoutDashboard},
      {to:ROUTES.MY_ACTIONS,label:"My Actions",icon:ListChecks},
      {to:ROUTES.PM_PROJECTS,label:"My Projects",icon:FolderKanban},
      {to:ROUTES.SCHEDULE,label:"Cross-project Schedule",icon:CalendarDays},
      {to:ROUTES.TASKS,label:"Tasks Across Projects",icon:CheckSquare},
      {to:ROUTES.REQUESTS,label:"Owner Requests",icon:ClipboardCheck},
    ],
    engineer: [
      {to:ROUTES.DASHBOARD,label:isConsultantEngineer?"Supervision Dashboard":"My Dashboard",icon:LayoutDashboard},
      {to:ROUTES.MY_ACTIONS,label:"My Actions",icon:ListChecks},
      {to:isConsultantEngineer?ROUTES.CONSULTANT_PROJECTS:ROUTES.ENGINEER_PROJECTS,label:"Assigned Projects",icon:FolderKanban},
      {to:ROUTES.SCHEDULE,label:"My Schedule",icon:CalendarDays},
    ],
    owner: [
      {to:ROUTES.OWNER_DASHBOARD,label:"Owner Dashboard",icon:LayoutDashboard},
      {to:ROUTES.PROJECTS,label:"My Projects",icon:FolderKanban},
      {to:ROUTES.REQUESTS,label:"My Requests",icon:ClipboardCheck},
      {to:ROUTES.SCHEDULE,label:"Upcoming Visits",icon:CalendarDays},
      {to:ROUTES.DOCUMENTS,label:"Project Documents",icon:FileText},
    ],
    worker: [
      {to:ROUTES.DASHBOARD,label:"My Dashboard",icon:LayoutDashboard},
    ],
  };

  const commonGlobal:NavItem[] = [
    {to:ROUTES.MESSAGES,label:"Messages",icon:MessageSquare},
    {to:ROUTES.NOTIFICATIONS,label:"Notifications",icon:Bell},
  ];

  const managerModules:NavItem[] = [
    {to:workspace.path("dashboard"),label:"Project Overview",icon:LayoutDashboard},
    {to:workspace.path("tasks"),label:"Tasks",icon:CheckSquare},
    {to:workspace.path("schedule"),label:"Schedule / Gantt",icon:CalendarDays},
    {to:workspace.path("collaboration"),label:"Collaboration",icon:ListChecks},
    {to:workspace.path("messages"),label:"Messages",icon:MessageSquare},
    {to:workspace.path("requests"),label:"Owner Requests",icon:ClipboardCheck},
    {to:workspace.path("issues"),label:"Issues",icon:AlertTriangle},
    {to:workspace.path("design-changes"),label:"Design Changes",icon:Pencil},
    {to:workspace.path("site-reports"),label:"Site Reports",icon:FileText},
    {to:workspace.path("site-visits"),label:"Site Visits",icon:CalendarDays},
    {to:workspace.path("documents"),label:"Documents",icon:FileText},
    {to:workspace.path("evidence"),label:"Project Information",icon:Images},
    {to:workspace.path("ifc"),label:"IFC / BIM",icon:Boxes},
    {to:workspace.path("ai-intelligence"),label:"AI Insights",icon:BrainCircuit},
    {to:workspace.path("team"),label:"Team",icon:Users},
    {to:workspace.path("activity"),label:"Activity",icon:Activity},
  ];

  const engineerModules:NavItem[] = [
    {to:workspace.path("dashboard"),label:"Project Overview",icon:LayoutDashboard},
    ...(isConsultantEngineer?[{to:workspace.path("reviews"),label:"Pending Reviews",icon:ClipboardCheck}]:[{to:workspace.path("tasks"),label:"My Tasks",icon:CheckSquare}]),
    {to:workspace.path("collaboration"),label:"Collaboration",icon:ListChecks},
    {to:workspace.path("messages"),label:"Messages",icon:MessageSquare},
    {to:workspace.path("requests"),label:"Requests",icon:ClipboardCheck},
    {to:workspace.path("issues"),label:"Issues",icon:AlertTriangle},
    {to:workspace.path("site-reports"),label:"Site Reports",icon:FileText},
    {to:workspace.path("site-visits"),label:"Site Visits",icon:CalendarDays},
    {to:workspace.path("documents"),label:"Documents",icon:FileText},
    {to:workspace.path("evidence"),label:"Project Information",icon:Images},
    {to:workspace.path("ifc"),label:"IFC / BIM",icon:Boxes},
    {to:workspace.path("ai-intelligence"),label:"AI Insights",icon:BrainCircuit},
    ...(!isConsultantEngineer?[{to:workspace.path("voice-reports"),label:"Voice Reports",icon:Mic2}]:[]),
    {to:workspace.path("activity"),label:"Activity",icon:Activity},
  ];

  const ownerModules:NavItem[] = [
    {to:workspace.path("dashboard"),label:"Project Overview",icon:LayoutDashboard},
    {to:workspace.path("requests"),label:"My Requests",icon:ClipboardCheck},
    {to:workspace.path("site-visits"),label:"Site Visits",icon:CalendarDays},
    {to:workspace.path("site-reports"),label:"Verified Reports",icon:FileText},
    {to:workspace.path("documents"),label:"Documents",icon:FileText},
    {to:workspace.path("evidence"),label:"Photos & Information",icon:Images},
    {to:workspace.path("design-changes"),label:"Design Changes",icon:Pencil},
    {to:workspace.path("messages"),label:"Messages",icon:MessageSquare},
    {to:workspace.path("activity"),label:"Activity",icon:Activity},
  ];

  const projectModules = isProjectManager ? managerModules : role === "engineer" ? engineerModules : isOwner ? ownerModules : managerModules;

  return <aside className="flex h-screen w-64 shrink-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar">
    <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-5">
      <div className="grid h-8 w-8 place-items-center rounded-md bg-accent text-sm font-black text-white">CP</div>
      <div><p className="text-sm font-bold text-sidebar-accent-foreground">ConstroPlatform</p><p className="text-[10px] capitalize text-sidebar-foreground/45">{role?.replaceAll("_"," ")}</p></div>
    </div>
    <nav className="flex-1 overflow-y-auto px-3 py-4">
      {workspace.isProjectWorkspace ? <>
        <div className="rounded-xl border border-sidebar-border bg-sidebar-accent/35 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">Project workspace</p>
          <p className="mt-1 truncate text-sm font-bold text-sidebar-accent-foreground">{workspace.project?.name||"Loading project…"}</p>
          <div className="mt-2 flex items-center gap-2 text-[11px] text-sidebar-foreground/55"><span className="h-2 w-2 rounded-full bg-emerald-500"/><span className="capitalize">{workspace.project?.status?.replaceAll("_"," ")||"Loading"}</span><span>·</span><span className="truncate">{workspace.projectId?.slice(0,8)}</span></div>
        </div>
        <NavLink to={workspace.portfolioPath} className={`${linkClass({isActive:false})} mt-2`}><ArrowLeft size={16}/><span>All Projects</span></NavLink>
        <SectionLabel>Project workspace</SectionLabel>
        <LinkList items={projectModules}/>
      </> : <>
        <SectionLabel>{isAdmin?"Administration":"Portfolio"}</SectionLabel>
        <LinkList items={globalByRole[role||""]||globalByRole.worker}/>
        <SectionLabel>Communication</SectionLabel>
        <LinkList items={commonGlobal}/>
      </>}
    </nav>
    <div className="border-t border-sidebar-border p-3"><NavLink to={ROUTES.SETTINGS} className={linkClass}><Settings size={16}/><span>Profile & Settings</span></NavLink></div>
  </aside>;
};
