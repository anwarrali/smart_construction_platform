import { ChevronRight, Home } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { useProjectWorkspace } from "../../../features/projects/context/ProjectWorkspaceContext";

const labels:Record<string,string> = {
  dashboard:"Overview", tasks:"Tasks", schedule:"Schedule", collaboration:"Collaboration",
  messages:"Messages", requests:"Owner Requests", issues:"Issues", "design-changes":"Design Changes",
  "site-reports":"Site Reports", "site-visits":"Site Visits", documents:"Documents", evidence:"Project Information",
  ifc:"IFC / BIM", "ai-intelligence":"AI Insights", team:"Team", activity:"Activity",
  reviews:"Reviews", history:"Review History", milestones:"Milestones", "voice-reports":"Voice Reports",
};

export const Breadcrumbs = () => {
  const location = useLocation();
  const workspace = useProjectWorkspace();
  if (!workspace.isProjectWorkspace) return null;
  const base = workspace.path("").replace(/\/$/, "");
  const relative = location.pathname.slice(base.length).replace(/^\//, "");
  const segments = relative ? relative.split("/") : [];
  const moduleName = segments[0] || "dashboard";
  return <nav aria-label="Breadcrumb" className="mb-4 flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
    <Link to={workspace.portfolioPath} className="inline-flex items-center gap-1 hover:text-foreground"><Home size={13}/> Projects</Link>
    <ChevronRight size={13}/>
    <Link to={workspace.path("dashboard")} className="max-w-52 truncate hover:text-foreground">{workspace.project?.name||"Project"}</Link>
    <ChevronRight size={13}/>
    <span className="font-medium text-foreground">{labels[moduleName]||moduleName.replaceAll("-"," ")}</span>
    {segments[1]&&<><ChevronRight size={13}/><span className="max-w-32 truncate font-mono">{decodeURIComponent(segments[1]).slice(0,12)}</span></>}
  </nav>;
};
