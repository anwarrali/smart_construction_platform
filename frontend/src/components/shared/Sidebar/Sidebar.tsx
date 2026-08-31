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

type NavItem = { to:string; label:string; icon:React.ElementType; permission?:string };

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
  const { isAdmin, permissionsReady, hasCapability, orgRoleLabel } = useRole();
  const workspace = useProjectWorkspace();

  /* Show a link until we positively know the capability is revoked. Before the
     permission list has arrived, hiding would make navigation flicker away and
     back; the pages and endpoints behind each link remain the real boundary
     either way. */
  const can = (code?: string) => !code || !permissionsReady || hasCapability(code);

  /* ── Portfolio navigation ──
     One list, filtered by capability. It used to be four lists keyed on role
     name, which is the shape a configurable role model cannot have: an office
     that creates "Resident Engineer" has no entry in such a table and would
     get whichever list happened to be the fallback. */
  const globalNav: NavItem[] = [
    {to:ROUTES.ADMIN_DASHBOARD,label:t("nav.platformDashboard"),icon:LayoutDashboard,permission:"platform.manage_users"},
    {to:ROUTES.DASHBOARD,label:t("nav.portfolioDashboard"),icon:LayoutDashboard},
    {to:ROUTES.OWNER_DASHBOARD,label:t("nav.ownerDashboard"),icon:LayoutDashboard,permission:"client_portal.view"},
    {to:ROUTES.MY_ACTIONS,label:t("nav.myActions"),icon:ListChecks},
    {to:ROUTES.PROJECTS,label:t("nav.myProjects"),icon:FolderKanban},
    {to:ROUTES.SCHEDULE,label:t("nav.mySchedule"),icon:CalendarDays},
    {to:ROUTES.TASKS,label:t("nav.tasksAcrossProjects"),icon:CheckSquare,permission:"task.view"},
    {to:ROUTES.REQUESTS,label:t("nav.ownerRequests"),icon:ClipboardCheck},
    {to:ROUTES.DOCUMENTS,label:t("nav.projectDocuments"),icon:FileText,permission:"document.view"},
    {to:ROUTES.USERS,label:t("nav.peopleAndAccess"),icon:Users,permission:"platform.manage_users"},
    {to:ROUTES.ADMIN_TEAMS,label:t("nav.projectTeams"),icon:Building2,permission:"platform.manage_users"},
    {to:ROUTES.ADMIN_ACCESS_CONTROL,label:t("nav.accessControl"),icon:ShieldCheck,permission:"platform.manage_permissions"},
    {to:ROUTES.ADMIN_OFFICE_ROLES,label:t("nav.officeRoles"),icon:ShieldCheck,permission:"org.manage_roles"},
  ].filter((item) => can(item.permission));

  const commonGlobal:NavItem[] = [
    {to:ROUTES.MESSAGES,label:t("nav.messages"),icon:MessageSquare},
    {to:ROUTES.NOTIFICATIONS,label:t("common.notifications"),icon:Bell},
  ];

  /* ── Project workspace navigation ──
     One table for every participant, each entry naming the permission its
     route is guarded by. What used to be three tables — manager, engineer,
     owner — differed only in which of these entries they listed, so the
     difference is now expressed once, as data the office controls. */
  const projectModules:NavGroup[] = ([
    { label:t("nav.groupPlan"), items:[
      {to:workspace.path("dashboard"),label:t("nav.projectOverview"),icon:LayoutDashboard,permission:"task.view"},
      {to:workspace.path("my-work"),label:t("nav.myTasks"),icon:CheckSquare,permission:"task.view"},
      {to:workspace.path("tasks"),label:t("nav.tasks"),icon:CheckSquare,permission:"task.view"},
      {to:workspace.path("review-queue"),label:t("nav.pendingReviews"),icon:ClipboardCheck,permission:"task.review"},
      {to:workspace.path("schedule"),label:t("nav.schedule"),icon:CalendarDays,permission:"schedule.view"},
    ]},
    { label:t("nav.groupControl"), items:[
      {to:workspace.path("issues"),label:t("nav.issues"),icon:AlertTriangle,permission:"issue.view"},
      {to:workspace.path("design-changes"),label:t("nav.designChanges"),icon:Pencil,permission:"design_change.view"},
      {to:workspace.path("requests"),label:t("nav.ownerRequests"),icon:ClipboardCheck,permission:"task.view"},
    ]},
    { label:t("nav.groupField"), items:[
      {to:workspace.path("voice-assistant"),label:t("nav.voiceAssistant"),icon:Mic2,permission:"task.view"},
      {to:workspace.path("voice-reports"),label:t("nav.voiceReports"),icon:Mic2,permission:"field_evidence.verify"},
      {to:workspace.path("site-reports"),label:t("nav.siteReports"),icon:FileText,permission:"site_report.view"},
      {to:workspace.path("site-visits"),label:t("nav.siteVisits"),icon:CalendarDays,permission:"task.view"},
      {to:workspace.path("evidence"),label:t("nav.projectInformation"),icon:Images,permission:"task.view"},
    ]},
    { label:t("nav.groupReference"), items:[
      {to:workspace.path("documents"),label:t("nav.documents"),icon:FileText,permission:"document.view"},
      {to:workspace.path("ifc"),label:t("nav.ifcBim"),icon:Boxes,permission:"ifc.view"},
      {to:workspace.path("ai-intelligence"),label:t("nav.aiInsights"),icon:BrainCircuit,permission:"ai.view_insights"},
    ]},
    { label:t("nav.groupTeam"), items:[
      {to:workspace.path("collaboration"),label:t("nav.collaboration"),icon:ListChecks,permission:"task.view"},
      {to:workspace.path("messages"),label:t("nav.messages"),icon:MessageSquare,permission:"task.view"},
      {to:workspace.path("team"),label:t("nav.team"),icon:Users,permission:"project.manage_members"},
      {to:workspace.path("parties"),label:t("nav.projectParties"),icon:Building2,permission:"project.manage_parties"},
      {to:workspace.path("activity"),label:t("nav.activity"),icon:Activity,permission:"task.view"},
    ]},
  ] as NavGroup[])
    .map((group) => ({ ...group, items: group.items.filter((item) => can(item.permission)) }))
    .filter((group) => group.items.length > 0);

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
          {orgRoleLabel}
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
        <LinkList items={globalNav} onNavigate={onNavigate}/>
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
