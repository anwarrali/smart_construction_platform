import { ChevronRight } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";
import { ROUTES } from "../../../utils/constants";

/** Route segment -> translation key for the module it opens. */
const MODULE_KEYS: Record<string, string> = {
  dashboard: "nav.projectOverview", "my-work": "nav.myTasks", tasks: "nav.tasks", schedule: "nav.schedule",
  collaboration: "nav.coordination", messages: "nav.messages", requests: "nav.ownerRequests",
  issues: "nav.issues", "design-changes": "nav.designChanges", "site-reports": "nav.siteReports",
  "site-visits": "nav.siteVisits", documents: "nav.documents", evidence: "nav.projectInformation",
  ifc: "nav.ifcBim", "ai-intelligence": "nav.aiInsights", agents: "nav.agents", team: "nav.team",
  parties: "nav.projectParties", activity: "nav.activity", notifications: "common.notifications",
  "review-queue": "nav.pendingReviews", reviews: "nav.pendingReviews", history: "nav.pendingReviews",
  milestones: "nav.milestones", "voice-reports": "nav.voiceReports", "voice-assistant": "nav.voiceAssistant",
};

/** Portfolio pages, by exact path. Anything unlisted shows no trail. */
const PORTFOLIO_KEYS: Record<string, string> = {
  [ROUTES.DASHBOARD]: "nav.dashboard",
  [ROUTES.ADMIN_DASHBOARD]: "nav.dashboard",
  [ROUTES.OWNER_DASHBOARD]: "nav.executiveOverview",
  [ROUTES.EXECUTIVE_OVERVIEW]: "nav.executiveOverview",
  [ROUTES.PROJECTS]: "nav.projects",
  [ROUTES.TASKS]: "nav.tasksAcrossProjects",
  [ROUTES.MY_ACTIONS]: "nav.coordination",
  [ROUTES.REQUESTS]: "nav.coordination",
  [ROUTES.SCHEDULE]: "nav.coordination",
  [ROUTES.DOCUMENTS]: "nav.projectDocuments",
  [ROUTES.MESSAGES]: "nav.messages",
  [ROUTES.NOTIFICATIONS]: "common.notifications",
  [ROUTES.USERS]: "nav.peopleAndAccess",
  [ROUTES.ADMIN_TEAMS]: "nav.projectTeams",
  [ROUTES.ADMIN_ACCESS_CONTROL]: "nav.accessControl",
  [ROUTES.ADMIN_OFFICE_ROLES]: "nav.officeRoles",
  [ROUTES.SETTINGS]: "common.profileSettings",
  [ROUTES.SITE_REPORTS]: "nav.siteReports",
  [ROUTES.ISSUES]: "nav.issues",
  [ROUTES.DESIGN_CHANGES]: "nav.designChanges",
};

const Separator = () => <ChevronRight size={12} aria-hidden className="shrink-0 text-muted-foreground/60 rtl-flip" />;

/**
 * Where you are, set in the top bar: portfolio › project › module › record.
 * The last crumb is the current page and is not a link.
 */
export const Breadcrumbs = ({ className = "" }: { className?: string }) => {
  const { t } = useTranslation();
  const location = useLocation();
  const workspace = useProjectWorkspace();
  const trailClass = `flex min-w-0 items-center gap-1.5 text-[13px] text-muted-foreground ${className}`;

  if (!workspace.isProjectWorkspace) {
    const clean = location.pathname.replace(/\/+$/, "") || "/";
    const key = PORTFOLIO_KEYS[clean];
    if (!key) return null;
    return (
      <nav aria-label={t("nav.breadcrumb")} className={trailClass}>
        <span aria-current="page" className="truncate font-semibold text-foreground">{t(key)}</span>
      </nav>
    );
  }

  /*
   * The module is found by locating the project id in the path, not by slicing
   * off a base computed from `path("")`: that helper resolves an empty module to
   * the `dashboard` fallback, so length arithmetic against it ate module names.
   * Splitting on the id also survives the retired `/project-manager/projects/…`
   * prefixes, which this provider sees before the redirect lands.
   */
  const parts = location.pathname.split("/").filter(Boolean).map(decodeURIComponent);
  const projectAt = workspace.projectId ? parts.indexOf(workspace.projectId) : -1;
  const segments = projectAt >= 0 ? parts.slice(projectAt + 1) : [];
  const moduleName = segments[0] || "dashboard";
  const moduleKey = MODULE_KEYS[moduleName];
  const moduleLabel = moduleKey ? t(moduleKey) : moduleName.replaceAll("-", " ");
  return (
    <nav aria-label={t("nav.breadcrumb")} className={trailClass}>
      <Link to={workspace.portfolioPath} className="hidden shrink-0 hover:text-foreground md:inline">{t("project.projects")}</Link>
      <span className="hidden md:inline-flex"><Separator /></span>
      <Link to={workspace.path("dashboard")} className="min-w-0 max-w-[14rem] truncate hover:text-foreground">
        {workspace.project?.name || t("project.project")}
      </Link>
      <Separator />
      {segments[1] ? (
        <>
          <Link to={workspace.path(moduleName)} className="shrink-0 hover:text-foreground">{moduleLabel}</Link>
          <Separator />
          <span aria-current="page" className="max-w-32 truncate font-mono text-xs text-foreground force-ltr">
            {decodeURIComponent(segments[1]).slice(0, 12)}
          </span>
        </>
      ) : (
        <span aria-current="page" className="truncate font-semibold text-foreground">{moduleLabel}</span>
      )}
    </nav>
  );
};
