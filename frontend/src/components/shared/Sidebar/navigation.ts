import type { ElementType } from "react";
import {
  AlertTriangle,
  Boxes,
  BrainCircuit,
  Building2,
  CalendarRange,
  ClipboardCheck,
  FileText,
  Flag,
  FolderKanban,
  GitPullRequestArrow,
  HardHat,
  Images,
  LayoutDashboard,
  ListChecks,
  ListTodo,
  MessageSquare,
  Mic2,
  Network,
  Presentation,
  ShieldCheck,
  SquareCheckBig,
  UserCog,
  Users,
  Workflow,
} from "lucide-react";

import { ROUTES } from "../../../utils/constants";

/**
 * The navigation model, kept apart from the rail that draws it so it can be
 * read — and tested — as data.
 *
 * Every entry names the permission its route is guarded by. Filtering happens
 * here, once, against the person's actual capabilities; nothing below keys on
 * a role name, because the office can define roles this file has never heard
 * of. Hiding an entry is a convenience: the route guard and the API remain the
 * boundary.
 */

export type NavItem = {
  /** Stable identity, used for keys and tests. */
  id: string;
  to: string;
  label: string;
  icon: ElementType;
  permission?: string;
  /** Exact match only (overview pages, whose path prefixes everything). */
  end?: boolean;
  /**
   * Other project modules that belong to this destination. Several routes are
   * tabs of one page (client requests, site visits and activity are views of
   * Coordination), so the entry stays lit on all of them.
   */
  alsoActiveOn?: string[];
  /**
   * A portfolio page that gathers project *work* (tasks, documents, messages,
   * coordination, the client overview). It has something to show only to
   * somebody who works in at least one project — not to an office
   * administrator who only administers them (QA 2026-10-22).
   */
  work?: boolean;
};

export type NavGroup = {
  id: string;
  /** Absent for the leading group, which needs no heading. */
  label?: string;
  items: NavItem[];
};

type Translate = (key: string) => string;
type Can = (permission?: string) => boolean;

/** Where "Dashboard" leads: the landing page this person's capabilities pick. */
export const dashboardRoute = (can: Can, isInternal: boolean): string => {
  if (can("platform.manage_users")) return ROUTES.ADMIN_DASHBOARD;
  if (!isInternal && can("client_portal.view")) return ROUTES.OWNER_DASHBOARD;
  return ROUTES.DASHBOARD;
};

const keep = (can: Can) => (groups: NavGroup[]): NavGroup[] =>
  groups
    .map((group) => ({ ...group, items: group.items.filter((item) => can(item.permission)) }))
    .filter((group) => group.items.length > 0);

/**
 * Portfolio navigation — what a person sees before opening a project.
 *
 * Three dashboards, three collaboration routes and a notifications page used
 * to be separate entries. They are now one entry each: the dashboard is the
 * one this person lands on, Coordination carries actions, requests and visits
 * as tabs, and notifications live behind the bell in the top bar.
 */
export const portfolioNavigation = (
  t: Translate, can: Can, isInternal: boolean, worksInAProject = true,
): NavGroup[] =>
  keep(can)(withoutIdleWork(worksInAProject, [
    {
      id: "work",
      items: [
        { id: "dashboard", to: dashboardRoute(can, isInternal), label: t("nav.dashboard"), icon: LayoutDashboard },
        { id: "projects", to: ROUTES.PROJECTS, label: t("nav.projects"), icon: FolderKanban },
        { id: "tasks", to: ROUTES.TASKS, label: t("nav.tasksAcrossProjects"), icon: SquareCheckBig, permission: "task.view", work: true },
        { id: "coordination", to: ROUTES.MY_ACTIONS, label: t("nav.coordination"), icon: Workflow, alsoActiveOn: [ROUTES.REQUESTS, ROUTES.SCHEDULE], work: true },
        { id: "documents", to: ROUTES.DOCUMENTS, label: t("nav.projectDocuments"), icon: FileText, permission: "document.view", work: true },
        { id: "messages", to: ROUTES.MESSAGES, label: t("nav.messages"), icon: MessageSquare, work: true },
      ],
    },
    {
      id: "administration",
      label: t("nav.administration"),
      items: [
        // An internal administrator may also read the client-facing overview —
        // of the projects they work in: the client portal is project content
        // (QA-06B). An external client already lands on it through "Dashboard".
        ...(isInternal && can("platform.manage_users")
          ? [{ id: "executive", to: ROUTES.OWNER_DASHBOARD, label: t("nav.executiveOverview"), icon: Presentation, permission: "client_portal.view", work: true }]
          : []),
        { id: "people", to: ROUTES.USERS, label: t("nav.peopleAndAccess"), icon: Users, permission: "platform.manage_users" },
        { id: "teams", to: ROUTES.ADMIN_TEAMS, label: t("nav.projectTeams"), icon: Building2, permission: "platform.manage_users" },
        { id: "permissions", to: ROUTES.ADMIN_ACCESS_CONTROL, label: t("nav.accessControl"), icon: ShieldCheck, permission: "platform.manage_permissions" },
        { id: "roles", to: ROUTES.ADMIN_OFFICE_ROLES, label: t("nav.officeRoles"), icon: UserCog, permission: "org.manage_roles" },
      ],
    },
  ]));

/** Drops portfolio work pages for somebody who works in no project. */
const withoutIdleWork = (worksInAProject: boolean, groups: NavGroup[]): NavGroup[] =>
  worksInAProject
    ? groups
    : groups.map((group) => ({ ...group, items: group.items.filter((item) => !item.work) }));

/**
 * Project navigation, grouped by the kind of work rather than by page.
 *
 * Coordination absorbs four entries that all opened the same page on a
 * different tab, and the voice assistant moved to the top bar where it can be
 * reached from any module. Nothing was removed: every route still exists and
 * every deep link still lands where it did.
 */
export const projectNavigation = (t: Translate, can: Can, path: (module: string) => string): NavGroup[] =>
  keep(can)([
    {
      id: "overview",
      items: [
        // Project-wide metrics — the endpoint behind it requires `task.view_all`.
        { id: "overview", to: path("dashboard"), label: t("nav.projectOverview"), icon: LayoutDashboard, permission: "task.view_all", end: true },
        { id: "my-work", to: path("my-work"), label: t("nav.myTasks"), icon: ListTodo, permission: "task.view" },
      ],
    },
    {
      id: "work",
      label: t("nav.groupWork"),
      items: [
        { id: "tasks", to: path("tasks"), label: t("nav.tasks"), icon: SquareCheckBig, permission: "task.view" },
        // Same route and guard as the schedule's milestone link (schedule.view),
        // now reachable directly instead of only through the timeline.
        { id: "milestones", to: path("milestones"), label: t("nav.milestones"), icon: Flag, permission: "schedule.view" },
        { id: "reviews", to: path("review-queue"), label: t("nav.pendingReviews"), icon: ClipboardCheck, permission: "task.review", alsoActiveOn: ["reviews", "history"] },
        { id: "schedule", to: path("schedule"), label: t("nav.schedule"), icon: CalendarRange, permission: "schedule.view" },
      ],
    },
    {
      id: "control",
      label: t("nav.groupControl"),
      items: [
        { id: "issues", to: path("issues"), label: t("nav.issues"), icon: AlertTriangle, permission: "issue.view" },
        { id: "design-changes", to: path("design-changes"), label: t("nav.designChanges"), icon: GitPullRequestArrow, permission: "design_change.view" },
      ],
    },
    {
      id: "site",
      label: t("nav.groupSite"),
      items: [
        { id: "site-reports", to: path("site-reports"), label: t("nav.siteReports"), icon: HardHat, permission: "site_report.view" },
        { id: "voice-reports", to: path("voice-reports"), label: t("nav.voiceReports"), icon: Mic2, permission: "field_evidence.verify" },
        { id: "evidence", to: path("evidence"), label: t("nav.projectInformation"), icon: Images, permission: "task.view" },
      ],
    },
    {
      id: "documents",
      label: t("nav.groupDocuments"),
      items: [
        { id: "documents", to: path("documents"), label: t("nav.documents"), icon: FileText, permission: "document.view" },
        { id: "ifc", to: path("ifc"), label: t("nav.ifcBim"), icon: Boxes, permission: "ifc.view" },
      ],
    },
    {
      id: "analysis",
      label: t("nav.groupAnalysis"),
      items: [
        { id: "ai-intelligence", to: path("ai-intelligence"), label: t("nav.aiInsights"), icon: BrainCircuit, permission: "ai.view_insights" },
        { id: "agents", to: path("agents"), label: t("nav.agents"), icon: Network, permission: "agents.view" },
      ],
    },
    {
      id: "team",
      label: t("nav.groupTeam"),
      items: [
        { id: "coordination", to: path("collaboration"), label: t("nav.coordination"), icon: ListChecks, permission: "task.view", alsoActiveOn: ["requests", "site-visits", "activity"] },
        { id: "messages", to: path("messages"), label: t("nav.messages"), icon: MessageSquare, permission: "task.view" },
        { id: "team", to: path("team"), label: t("nav.team"), icon: Users, permission: "project.manage_members" },
        { id: "parties", to: path("parties"), label: t("nav.projectParties"), icon: Building2, permission: "project.manage_parties" },
      ],
    },
  ]);

/**
 * Whether an entry is the current destination, including the tab routes it
 * owns. `alsoActiveOn` holds either a project module segment (`requests`) or a
 * full portfolio path (`/requests`).
 */
export const isItemActive = (item: NavItem, pathname: string, projectId?: string): boolean => {
  const clean = pathname.replace(/\/+$/, "") || "/";
  if (item.end ? clean === item.to : clean === item.to || clean.startsWith(`${item.to}/`)) return true;
  if (!item.alsoActiveOn) return false;
  const parts = clean.split("/").filter(Boolean);
  const moduleName = projectId ? parts[parts.indexOf(projectId) + 1] : undefined;
  return item.alsoActiveOn.some((entry) =>
    entry.startsWith("/") ? clean === entry || clean.startsWith(`${entry}/`) : entry === moduleName,
  );
};
