import { ChevronRight, Home } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";

/** Route segment -> translation key for the module it opens. */
const MODULE_KEYS: Record<string, string> = {
  dashboard: "nav.projectOverview", tasks: "nav.tasks", schedule: "nav.schedule",
  collaboration: "nav.collaboration", messages: "nav.messages", requests: "nav.ownerRequests",
  issues: "nav.issues", "design-changes": "nav.designChanges", "site-reports": "nav.siteReports",
  "site-visits": "nav.siteVisits", documents: "nav.documents", evidence: "nav.projectInformation",
  ifc: "nav.ifcBim", "ai-intelligence": "nav.aiInsights", team: "nav.team", activity: "nav.activity",
  reviews: "nav.pendingReviews", history: "nav.pendingReviews", milestones: "task.milestone",
  "voice-reports": "nav.voiceReports", "voice-assistant": "nav.voiceAssistant",
};

export const Breadcrumbs = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const workspace = useProjectWorkspace();
  if (!workspace.isProjectWorkspace) return null;
  /*
   * The module is found by locating the project id in the path, not by
   * slicing off a base computed from `path("")`.
   *
   * `path("")` cannot return a bare base and is not meant to: every link it
   * builds has to land on a real page, so an empty module resolves to the
   * `dashboard` fallback. That made `base` ten characters too long, and the
   * slice ate the module name — `/site-visits` displayed as "ts", while every
   * module whose name is shorter than "/dashboard" sliced away to nothing and
   * fell through to `"dashboard"`, so the Tasks page announced itself as
   * Project overview.
   *
   * Splitting on the id has no arithmetic to get wrong, and it also survives
   * the retired `/project-manager/projects/:id/…` prefixes: this provider runs
   * once on the pre-redirect pathname, where a fixed base would not match at
   * all.
   */
  const parts = location.pathname.split("/").filter(Boolean).map(decodeURIComponent);
  const projectAt = workspace.projectId ? parts.indexOf(workspace.projectId) : -1;
  const segments = projectAt >= 0 ? parts.slice(projectAt + 1) : [];
  const moduleName = segments[0] || "dashboard";
  const moduleKey = MODULE_KEYS[moduleName];
  return <nav aria-label={t("nav.projectWorkspace")} className="mb-4 flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
    <Link to={workspace.portfolioPath} className="inline-flex items-center gap-1 hover:text-foreground"><Home size={13}/> {t("project.projects")}</Link>
    {/* The separator points along the reading direction. */}
    <ChevronRight size={13} className="rtl-flip"/>
    <Link to={workspace.path("dashboard")} className="max-w-52 truncate hover:text-foreground">{workspace.project?.name||t("project.project")}</Link>
    <ChevronRight size={13} className="rtl-flip"/>
    <span className="font-medium text-foreground">{moduleKey ? t(moduleKey) : moduleName.replaceAll("-", " ")}</span>
    {segments[1]&&<><ChevronRight size={13} className="rtl-flip"/><span className="max-w-32 truncate font-mono force-ltr">{decodeURIComponent(segments[1]).slice(0,12)}</span></>}
  </nav>;
};
