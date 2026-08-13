import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const { role, isAdmin, isOwner, isProjectManager, isConsultantEngineer } = useRole();
  const workspace = useProjectWorkspace();

  const globalByRole:Record<string,NavItem[]> = {
    admin: [
      {to:ROUTES.ADMIN_DASHBOARD,label:t("nav.platformDashboard"),icon:LayoutDashboard},
      {to:ROUTES.PROJECTS,label:t("project.projects"),icon:FolderKanban},
      {to:ROUTES.USERS,label:t("nav.peopleAndAccess"),icon:Users},
      {to:ROUTES.ADMIN_TEAMS,label:t("nav.projectTeams"),icon:Building2},
    ],
    project_manager: [
      {to:ROUTES.DASHBOARD,label:t("nav.portfolioDashboard"),icon:LayoutDashboard},
      {to:ROUTES.MY_ACTIONS,label:t("nav.myActions"),icon:ListChecks},
      {to:ROUTES.PM_PROJECTS,label:t("nav.myProjects"),icon:FolderKanban},
      {to:ROUTES.SCHEDULE,label:t("nav.crossProjectSchedule"),icon:CalendarDays},
      {to:ROUTES.TASKS,label:t("nav.tasksAcrossProjects"),icon:CheckSquare},
      {to:ROUTES.REQUESTS,label:t("nav.ownerRequests"),icon:ClipboardCheck},
    ],
    engineer: [
      {to:ROUTES.DASHBOARD,label:isConsultantEngineer?"Supervision Dashboard":"My Dashboard",icon:LayoutDashboard},
      {to:ROUTES.MY_ACTIONS,label:t("nav.myActions"),icon:ListChecks},
      {to:isConsultantEngineer?ROUTES.CONSULTANT_PROJECTS:ROUTES.ENGINEER_PROJECTS,label:t("nav.assignedProjects"),icon:FolderKanban},
      {to:ROUTES.SCHEDULE,label:t("nav.mySchedule"),icon:CalendarDays},
    ],
    owner: [
      {to:ROUTES.OWNER_DASHBOARD,label:t("nav.ownerDashboard"),icon:LayoutDashboard},
      {to:ROUTES.PROJECTS,label:t("nav.myProjects"),icon:FolderKanban},
      {to:ROUTES.REQUESTS,label:t("nav.myRequests"),icon:ClipboardCheck},
      {to:ROUTES.SCHEDULE,label:t("nav.upcomingVisits"),icon:CalendarDays},
      {to:ROUTES.DOCUMENTS,label:t("nav.projectDocuments"),icon:FileText},
    ],
    worker: [
      {to:ROUTES.DASHBOARD,label:t("nav.myDashboard"),icon:LayoutDashboard},
    ],
  };

  const commonGlobal:NavItem[] = [
    {to:ROUTES.MESSAGES,label:t("nav.messages"),icon:MessageSquare},
    {to:ROUTES.NOTIFICATIONS,label:t("common.notifications"),icon:Bell},
  ];

  const managerModules:NavItem[] = [
    {to:workspace.path("dashboard"),label:t("nav.projectOverview"),icon:LayoutDashboard},
    {to:workspace.path("tasks"),label:t("nav.tasks"),icon:CheckSquare},
    {to:workspace.path("schedule"),label:t("nav.schedule"),icon:CalendarDays},
    {to:workspace.path("collaboration"),label:t("nav.collaboration"),icon:ListChecks},
    {to:workspace.path("messages"),label:t("nav.messages"),icon:MessageSquare},
    {to:workspace.path("requests"),label:t("nav.ownerRequests"),icon:ClipboardCheck},
    {to:workspace.path("issues"),label:t("nav.issues"),icon:AlertTriangle},
    {to:workspace.path("design-changes"),label:t("nav.designChanges"),icon:Pencil},
    {to:workspace.path("site-reports"),label:t("nav.siteReports"),icon:FileText},
    {to:workspace.path("site-visits"),label:t("nav.siteVisits"),icon:CalendarDays},
    {to:workspace.path("documents"),label:t("nav.documents"),icon:FileText},
    {to:workspace.path("evidence"),label:t("nav.projectInformation"),icon:Images},
    {to:workspace.path("ifc"),label:t("nav.ifcBim"),icon:Boxes},
    {to:workspace.path("ai-intelligence"),label:t("nav.aiInsights"),icon:BrainCircuit},
    {to:workspace.path("team"),label:t("nav.team"),icon:Users},
    {to:workspace.path("activity"),label:t("nav.activity"),icon:Activity},
  ];

  const engineerModules:NavItem[] = [
    {to:workspace.path("dashboard"),label:t("nav.projectOverview"),icon:LayoutDashboard},
    ...(isConsultantEngineer?[{to:workspace.path("reviews"),label:t("nav.pendingReviews"),icon:ClipboardCheck}]:[{to:workspace.path("tasks"),label:t("nav.myTasks"),icon:CheckSquare}]),
    {to:workspace.path("collaboration"),label:t("nav.collaboration"),icon:ListChecks},
    {to:workspace.path("messages"),label:t("nav.messages"),icon:MessageSquare},
    {to:workspace.path("requests"),label:t("nav.ownerRequests"),icon:ClipboardCheck},
    {to:workspace.path("issues"),label:t("nav.issues"),icon:AlertTriangle},
    {to:workspace.path("site-reports"),label:t("nav.siteReports"),icon:FileText},
    {to:workspace.path("site-visits"),label:t("nav.siteVisits"),icon:CalendarDays},
    {to:workspace.path("documents"),label:t("nav.documents"),icon:FileText},
    {to:workspace.path("evidence"),label:t("nav.projectInformation"),icon:Images},
    {to:workspace.path("ifc"),label:t("nav.ifcBim"),icon:Boxes},
    {to:workspace.path("ai-intelligence"),label:t("nav.aiInsights"),icon:BrainCircuit},
    ...(!isConsultantEngineer?[{to:workspace.path("voice-reports"),label:t("nav.voiceReports"),icon:Mic2}]:[]),
    {to:workspace.path("activity"),label:t("nav.activity"),icon:Activity},
  ];

  const ownerModules:NavItem[] = [
    {to:workspace.path("dashboard"),label:t("nav.projectOverview"),icon:LayoutDashboard},
    {to:workspace.path("requests"),label:t("nav.myRequests"),icon:ClipboardCheck},
    {to:workspace.path("site-visits"),label:t("nav.siteVisits"),icon:CalendarDays},
    {to:workspace.path("site-reports"),label:t("nav.verifiedReports"),icon:FileText},
    {to:workspace.path("documents"),label:t("nav.documents"),icon:FileText},
    {to:workspace.path("evidence"),label:t("nav.photosAndInformation"),icon:Images},
    {to:workspace.path("design-changes"),label:t("nav.designChanges"),icon:Pencil},
    {to:workspace.path("messages"),label:t("nav.messages"),icon:MessageSquare},
    {to:workspace.path("activity"),label:t("nav.activity"),icon:Activity},
  ];

  const projectModules = isProjectManager ? managerModules : role === "engineer" ? engineerModules : isOwner ? ownerModules : managerModules;

  return <aside className="flex h-screen w-64 shrink-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar">
    <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-5">
      <div className="grid h-8 w-8 place-items-center rounded-md bg-accent text-sm font-black text-white">CP</div>
      <div><p className="text-sm font-bold text-sidebar-accent-foreground">ConstroPlatform</p><p className="text-[10px] capitalize text-sidebar-foreground/45">{role?t(`roles.${role}`,{defaultValue:role.replaceAll("_"," ")}):""}</p></div>
    </div>
    <nav className="flex-1 overflow-y-auto px-3 py-4">
      {workspace.isProjectWorkspace ? <>
        <div className="rounded-xl border border-sidebar-border bg-sidebar-accent/35 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">{t("nav.projectWorkspace")}</p>
          <p className="mt-1 truncate text-sm font-bold text-sidebar-accent-foreground">{workspace.project?.name||t("common.loadingProject")}</p>
          <div className="mt-2 flex items-center gap-2 text-[11px] text-sidebar-foreground/55"><span className="h-2 w-2 rounded-full bg-emerald-500"/><span className="capitalize">{workspace.project?.status?t(`project.status.${workspace.project.status}`,{defaultValue:workspace.project.status.replaceAll("_"," ")}):t("common.loading")}</span><span>·</span><span className="truncate">{workspace.projectId?.slice(0,8)}</span></div>
        </div>
        <NavLink to={workspace.portfolioPath} className={`${linkClass({isActive:false})} mt-2`}><ArrowLeft size={16} className="rtl-flip"/><span>{t("nav.allProjects")}</span></NavLink>
        <SectionLabel>{t("nav.projectWorkspace")}</SectionLabel>
        <LinkList items={projectModules}/>
      </> : <>
        <SectionLabel>{isAdmin?t("nav.administration"):t("nav.portfolio")}</SectionLabel>
        <LinkList items={globalByRole[role||""]||globalByRole.worker}/>
        <SectionLabel>{t("nav.communication")}</SectionLabel>
        <LinkList items={commonGlobal}/>
      </>}
    </nav>
    <div className="border-t border-sidebar-border p-3"><NavLink to={ROUTES.SETTINGS} className={linkClass}><Settings size={16}/><span>{t("common.profileSettings")}</span></NavLink></div>
  </aside>;
};
