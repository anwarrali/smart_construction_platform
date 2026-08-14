import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Activity, AlertTriangle, ArrowLeft, Bell, Boxes, BrainCircuit, Building2,
  CalendarDays, CheckSquare, ClipboardCheck, FileText, FolderKanban, Images,
  LayoutDashboard, ListChecks, MessageSquare, Mic2, Pencil, Settings, ShieldCheck, Users,
} from "lucide-react";

import { useRole } from "../../../hooks/useRole";
import { ROUTES } from "../../../utils/constants";
import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";
import { StructIQMark } from "../../brand/StructIQLogo";

type NavItem = { to:string; label:string; icon:React.ElementType };

/* A titled run of links. The workspace has sixteen modules, which as one flat
   list makes nothing look more important than anything else; grouping them by
   what the person is doing — planning, controlling, working the site, looking
   something up — restores hierarchy without hiding a single destination. */
type NavGroup = { label:string; items:NavItem[] };

/* The active item is marked by a rule on its leading edge — a registration
   mark rather than a filled pill. Direction-aware, so it works in RTL. */
const linkClass = ({ isActive }: { isActive:boolean }) =>
  `nav-link${isActive ? " nav-link-active" : ""}`;

/* Section headings sit on a hairline, the way a drawing index is divided. */
const SectionLabel = ({ children }: { children:React.ReactNode }) => (
  <div className="mb-2 mt-6 flex items-center gap-2.5 px-3 first:mt-1">
    <p className="label-caps whitespace-nowrap text-sidebar-foreground/45">{children}</p>
    <span className="h-px flex-1 bg-sidebar-border" />
  </div>
);

const LinkList = ({ items, onNavigate }: { items:NavItem[]; onNavigate?:()=>void }) => <div className="space-y-0.5">{items.map(({to,label,icon:Icon}) =>
  <NavLink key={`${to}-${label}`} to={to} className={linkClass} end={to.endsWith("/dashboard")} onClick={onNavigate}>
    {({isActive})=><><Icon size={15} strokeWidth={isActive?2.1:1.7} className={isActive?"":"opacity-70"}/><span className="truncate">{label}</span></>}
  </NavLink>)}</div>;

/**
 * The same navigation serves two presentations: a permanent rail on large
 * screens, and an overlay drawer below `lg`. `onNavigate` lets the drawer close
 * itself once the user has chosen a destination — on a phone the menu covering
 * the page it just navigated to is the wrong resting state.
 */
export const Sidebar = ({ className = "", onNavigate }: { className?:string; onNavigate?:()=>void } = {}) => {
  const { t } = useTranslation();
  const { role, isAdmin, isOwner, isProjectManager, isConsultantEngineer } = useRole();
  const workspace = useProjectWorkspace();

  const globalByRole:Record<string,NavItem[]> = {
    admin: [
      {to:ROUTES.ADMIN_DASHBOARD,label:t("nav.platformDashboard"),icon:LayoutDashboard},
      {to:ROUTES.PROJECTS,label:t("project.projects"),icon:FolderKanban},
      {to:ROUTES.USERS,label:t("nav.peopleAndAccess"),icon:Users},
      {to:ROUTES.ADMIN_TEAMS,label:t("nav.projectTeams"),icon:Building2},
      {to:ROUTES.ADMIN_ACCESS_CONTROL,label:t("nav.accessControl"),icon:ShieldCheck},
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

  /* Every destination that existed before is still here, in the same order
     within its group — the grouping adds hierarchy, it does not remove or
     relocate any module. */
  const managerModules:NavGroup[] = [
    { label:t("nav.groupPlan"), items:[
      {to:workspace.path("dashboard"),label:t("nav.projectOverview"),icon:LayoutDashboard},
      {to:workspace.path("tasks"),label:t("nav.tasks"),icon:CheckSquare},
      {to:workspace.path("schedule"),label:t("nav.schedule"),icon:CalendarDays},
    ]},
    { label:t("nav.groupControl"), items:[
      {to:workspace.path("issues"),label:t("nav.issues"),icon:AlertTriangle},
      {to:workspace.path("design-changes"),label:t("nav.designChanges"),icon:Pencil},
      {to:workspace.path("requests"),label:t("nav.ownerRequests"),icon:ClipboardCheck},
    ]},
    { label:t("nav.groupField"), items:[
      {to:workspace.path("site-reports"),label:t("nav.siteReports"),icon:FileText},
      {to:workspace.path("site-visits"),label:t("nav.siteVisits"),icon:CalendarDays},
      {to:workspace.path("evidence"),label:t("nav.projectInformation"),icon:Images},
    ]},
    { label:t("nav.groupReference"), items:[
      {to:workspace.path("documents"),label:t("nav.documents"),icon:FileText},
      {to:workspace.path("ifc"),label:t("nav.ifcBim"),icon:Boxes},
      {to:workspace.path("ai-intelligence"),label:t("nav.aiInsights"),icon:BrainCircuit},
    ]},
    { label:t("nav.groupTeam"), items:[
      {to:workspace.path("collaboration"),label:t("nav.collaboration"),icon:ListChecks},
      {to:workspace.path("messages"),label:t("nav.messages"),icon:MessageSquare},
      {to:workspace.path("team"),label:t("nav.team"),icon:Users},
      {to:workspace.path("activity"),label:t("nav.activity"),icon:Activity},
    ]},
  ];

  const engineerModules:NavGroup[] = [
    { label:t("nav.groupPlan"), items:[
      {to:workspace.path("dashboard"),label:t("nav.projectOverview"),icon:LayoutDashboard},
      ...(isConsultantEngineer?[{to:workspace.path("reviews"),label:t("nav.pendingReviews"),icon:ClipboardCheck}]:[{to:workspace.path("tasks"),label:t("nav.myTasks"),icon:CheckSquare}]),
    ]},
    { label:t("nav.groupControl"), items:[
      {to:workspace.path("issues"),label:t("nav.issues"),icon:AlertTriangle},
      {to:workspace.path("requests"),label:t("nav.ownerRequests"),icon:ClipboardCheck},
    ]},
    { label:t("nav.groupField"), items:[
      {to:workspace.path("site-reports"),label:t("nav.siteReports"),icon:FileText},
      {to:workspace.path("site-visits"),label:t("nav.siteVisits"),icon:CalendarDays},
      {to:workspace.path("evidence"),label:t("nav.projectInformation"),icon:Images},
      ...(!isConsultantEngineer?[{to:workspace.path("voice-reports"),label:t("nav.voiceReports"),icon:Mic2}]:[]),
    ]},
    { label:t("nav.groupReference"), items:[
      {to:workspace.path("documents"),label:t("nav.documents"),icon:FileText},
      {to:workspace.path("ifc"),label:t("nav.ifcBim"),icon:Boxes},
      {to:workspace.path("ai-intelligence"),label:t("nav.aiInsights"),icon:BrainCircuit},
    ]},
    { label:t("nav.groupTeam"), items:[
      {to:workspace.path("collaboration"),label:t("nav.collaboration"),icon:ListChecks},
      {to:workspace.path("messages"),label:t("nav.messages"),icon:MessageSquare},
      {to:workspace.path("activity"),label:t("nav.activity"),icon:Activity},
    ]},
  ];

  const ownerModules:NavGroup[] = [
    { label:t("nav.groupPlan"), items:[
      {to:workspace.path("dashboard"),label:t("nav.projectOverview"),icon:LayoutDashboard},
    ]},
    { label:t("nav.groupControl"), items:[
      {to:workspace.path("requests"),label:t("nav.myRequests"),icon:ClipboardCheck},
      {to:workspace.path("design-changes"),label:t("nav.designChanges"),icon:Pencil},
    ]},
    { label:t("nav.groupField"), items:[
      {to:workspace.path("site-visits"),label:t("nav.siteVisits"),icon:CalendarDays},
      {to:workspace.path("site-reports"),label:t("nav.verifiedReports"),icon:FileText},
      {to:workspace.path("evidence"),label:t("nav.photosAndInformation"),icon:Images},
    ]},
    { label:t("nav.groupReference"), items:[
      {to:workspace.path("documents"),label:t("nav.documents"),icon:FileText},
    ]},
    { label:t("nav.groupTeam"), items:[
      {to:workspace.path("messages"),label:t("nav.messages"),icon:MessageSquare},
      {to:workspace.path("activity"),label:t("nav.activity"),icon:Activity},
    ]},
  ];

  const projectModules = isProjectManager ? managerModules : role === "engineer" ? engineerModules : isOwner ? ownerModules : managerModules;

  return <aside className={`relative flex h-full w-[16.5rem] max-w-[85vw] shrink-0 flex-col overflow-hidden border-e border-sidebar-border bg-sidebar ${className}`}>
    {/* A whisper of sheet grid on the rail, so it reads as drawn rather than filled. */}
    <div aria-hidden className="pointer-events-none absolute inset-0 opacity-[0.55] blueprint-field" />

    <div className="relative flex h-16 items-center gap-2.5 border-b border-sidebar-border px-4">
      {/* The StructIQ mark, reversed out of the navy rail. */}
      <StructIQMark size={28} frameClassName="text-white" />
      <div className="min-w-0">
        <p className="truncate text-[14px] font-semibold leading-none tracking-heading">
          <span className="text-white">Struct</span>
          <span className="text-sidebar-mark">IQ</span>
        </p>
        <p className="mt-1 truncate text-[10px] leading-none text-sidebar-foreground/55">
          {role?t(`roles.${role}`,{defaultValue:role.replaceAll("_"," ")}):""}
        </p>
      </div>
    </div>
    <nav className="relative flex-1 overflow-y-auto px-3 py-3">
      {workspace.isProjectWorkspace ? <>
        {/* Project identity, set out like the title block of a drawing:
            the reference above, the name, then the measured metadata. */}
        <div className="relative rounded-panel border border-sidebar-border bg-sidebar-accent/45 px-3 py-2.5">
          <span aria-hidden className="absolute -top-px start-3 h-[2px] w-7 bg-sidebar-mark" />
          <p className="label-caps text-sidebar-foreground/45">{t("nav.projectWorkspace")}</p>
          <p className="mt-1.5 truncate text-[13px] font-semibold leading-snug text-sidebar-accent-foreground">
            {workspace.project?.name||t("common.loadingProject")}
          </p>
          <div className="mt-2 flex items-center gap-2 border-t border-sidebar-border/70 pt-2 text-[10px] text-sidebar-foreground/55">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-[1px] bg-sidebar-mark" />
              <span>{workspace.project?.status?t(`project.status.${workspace.project.status}`,{defaultValue:workspace.project.status.replaceAll("_"," ")}):t("common.loading")}</span>
            </span>
            <span className="ms-auto text-measured tracking-tight text-sidebar-foreground/40">
              {workspace.projectId?.slice(0,8).toUpperCase()}
            </span>
          </div>
        </div>

        <NavLink to={workspace.portfolioPath} className="nav-link mt-2 text-sidebar-foreground/60" onClick={onNavigate}>
          <ArrowLeft size={15} className="rtl-flip"/><span>{t("nav.allProjects")}</span>
        </NavLink>

        {projectModules.map(group => <div key={group.label}>
          <SectionLabel>{group.label}</SectionLabel>
          <LinkList items={group.items} onNavigate={onNavigate}/>
        </div>)}
      </> : <>
        <SectionLabel>{isAdmin?t("nav.administration"):t("nav.portfolio")}</SectionLabel>
        <LinkList items={globalByRole[role||""]||globalByRole.worker} onNavigate={onNavigate}/>
        <SectionLabel>{t("nav.communication")}</SectionLabel>
        <LinkList items={commonGlobal} onNavigate={onNavigate}/>
      </>}
    </nav>
    <div className="relative border-t border-sidebar-border p-2.5">
      <NavLink to={ROUTES.SETTINGS} className={linkClass} onClick={onNavigate}>
        <Settings size={15} strokeWidth={1.7}/><span>{t("common.profileSettings")}</span>
      </NavLink>
    </div>
  </aside>;
};
