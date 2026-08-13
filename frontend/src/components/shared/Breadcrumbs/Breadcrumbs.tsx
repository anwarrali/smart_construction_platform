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
  "voice-reports": "nav.voiceReports",
};

export const Breadcrumbs = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const workspace = useProjectWorkspace();
  if (!workspace.isProjectWorkspace) return null;
  const base = workspace.path("").replace(/\/$/, "");
  const relative = location.pathname.slice(base.length).replace(/^\//, "");
  const segments = relative ? relative.split("/") : [];
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
