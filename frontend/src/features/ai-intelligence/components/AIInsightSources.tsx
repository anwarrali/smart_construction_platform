import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Link2, ShieldAlert } from "lucide-react";

import { Badge } from "../../../components/ui/Badge";
import api from "../../../services/api";
import { useTranslation } from "react-i18next";
import { useRole } from "../../../hooks/useRole";
import type { AIInsightSource } from "../../../types/aiInsight";
import { projectEntityPath } from "../../../utils/projectRoutes";
import { labelize } from "../../ifc/components/IFCShared";

export const AIInsightSources = ({ projectId, insightId, fallback }: { projectId:string; insightId:string; fallback:Record<string,unknown> }) => {
  const { t } = useTranslation();
  const { role, isConsultantEngineer } = useRole();
  const affiliation = isConsultantEngineer ? ("external_consultant" as const) : undefined;
  const [sources,setSources]=useState<AIInsightSource[]>();
  const [failed,setFailed]=useState(false);
  useEffect(()=>{let active=true;void api.aiIntelligence.sources(projectId,insightId).then(value=>{if(active)setSources(value);}).catch(()=>{if(active)setFailed(true);});return()=>{active=false;};},[insightId,projectId]);
  return <details className="mt-3 rounded border p-3 text-xs">
    <summary className="cursor-pointer font-medium">{t("ai.sourcesUsed")}</summary>
    {!sources&&!failed?<p className="mt-2 text-muted-foreground">{t("common.loading")}</p>:sources?.length?<div className="mt-3 space-y-2">{sources.map(source=>{
      // Every source opens the record inside this project's workspace; the old
      // portfolio-level paths (/issues/:id, /design-changes/:id) are not routes.
      const path=projectEntityPath(projectId,source.sourceType,source.sourceId,role,affiliation);
      return <div key={source.id} className="flex items-center justify-between gap-3 rounded bg-muted/40 p-2"><div className="flex min-w-0 items-center gap-2">{source.isValid?<Link2 size={14}/>:<ShieldAlert size={14} className="text-amber-600"/>}<div className="min-w-0"><p className="truncate font-medium">{source.sourceLabel||`${labelize(source.sourceType)} ${source.sourceId}`}</p><p className="text-muted-foreground">{labelize(source.sourceState)}{source.invalidationReason?` · ${source.invalidationReason}`:""}</p></div></div><div className="flex items-center gap-2"><Badge variant={source.isValid?"success":"warning"}>{source.isValid?t("ai.current"):t("ai.outdated")}</Badge><Link className="text-primary" to={path} aria-label={t("common.openRecord")}><ExternalLink size={14}/></Link></div></div>;})}</div>:<div className="mt-2"><p className="text-muted-foreground">{t("empty.noData")}</p><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap">{JSON.stringify(fallback,null,2)}</pre></div>}
  </details>;
};
