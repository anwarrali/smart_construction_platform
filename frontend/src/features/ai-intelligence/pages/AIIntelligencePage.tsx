import { useCallback, useEffect, useMemo, useState } from "react";
import { errorMessage } from "../../../utils/errorMessage";
import { AlertTriangle, Bot, CheckCircle2, ClipboardList, Eye, RefreshCw, ShieldAlert, Sparkles, Target } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useVocabulary } from "../../../utils/vocabulary";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { useRole } from "../../../hooks/useRole";
import api from "../../../services/api";
import type { AIInsight, AIIntelligenceOverview } from "../../../types/aiInsight";
import { labelize, LoadingState } from "../../ifc/components/IFCShared";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import { AIInsightSources } from "../components/AIInsightSources";

const severityVariant=(severity:string)=>severity==="CRITICAL"?"danger":severity==="HIGH"?"danger":severity==="WARNING"?"warning":severity==="ATTENTION"?"info":"neutral";
const selectClass="rounded-md border bg-background px-3 py-2 text-sm";

/* Review states the API accepts, with the labels the §15 review centre uses.
   The stored vocabulary is OPEN / ACKNOWLEDGED / RESOLVED / FALSE_POSITIVE;
   older UI options such as "NEW" matched no stored row and filtered to nothing. */
const REVIEW_STATES:{value:string;label:string}[]=[
  {value:"OPEN",label:"New / Open"},
  {value:"ACKNOWLEDGED",label:"Acknowledged / Under review"},
  {value:"RESOLVED",label:"Resolved"},
  {value:"FALSE_POSITIVE",label:"Dismissed"},
];
const SEVERITIES=["CRITICAL","HIGH","WARNING","ATTENTION","SUGGESTION","INFORMATION","INFO"];

/**
 * Render an AI insight in the reader's language.
 *
 * The engine stores the facts it used (`messageParamsJson`) alongside the
 * English sentence it composed. When a translation exists for the message
 * family we compose the same statement in the active language from those facts;
 * otherwise we show exactly what the engine wrote. The English text is never
 * machine-translated and the meaning is never altered.
 */
const useInsightText = () => {
  const { t } = useTranslation();
  return (item: AIInsight, part: "title" | "description" | "reason" | "recommendedAction") => {
    const fallback = item[part];
    if (!item.messageKey) return fallback;
    return t(`aiInsight.${item.messageKey}.${part}`, {
      ...(item.messageParamsJson || {}),
      defaultValue: fallback,
    });
  };
};

export const AIIntelligencePage=()=>{
  const {t}=useTranslation();const vocabulary=useVocabulary();
  /* Insight categories are stored enum values; show the catalogue label. */
  const insightCategory=(value:string)=>t("aiInsight.category."+String(value).toLowerCase(),{defaultValue:labelize(value)});
  const workspace=useProjectWorkspace();const params=useParams<{projectId?:string}>();const projectId=workspace.projectId||params.projectId;const navigate=useNavigate();const {role}=useRole();
  const [overview,setOverview]=useState<AIIntelligenceOverview>();const [items,setItems]=useState<AIInsight[]>([]);const [loading,setLoading]=useState(true);const [busy,setBusy]=useState("");
  const [filters,setFilters]=useState({status:"",severity:"",category:""});
  const [search,setSearch]=useState("");const [discipline,setDiscipline]=useState("");
  const [searchParams,setSearchParams]=useSearchParams();const focusedInsightId=searchParams.get("insightId");
  const severityOptions=useMemo(()=>SEVERITIES.filter(value=>items.some(item=>item.severity===value)),[items]);
  const categoryOptions=useMemo(()=>Array.from(new Set(items.map(item=>item.category))).sort(),[items]);
  const disciplineOptions=useMemo(()=>Array.from(new Set(items.flatMap(item=>item.affectedJson?.disciplines||[]))).sort(),[items]);
  // Search and discipline are applied client-side; the API filters the rest.
  const visible=useMemo(()=>{
    const needle=search.trim().toLowerCase();
    // A deep link from a notification or activity row opens that one finding.
    if(focusedInsightId){const match=items.filter(item=>item.id===focusedInsightId);if(match.length)return match;}
    return items.filter(item=>
      (!discipline||(item.affectedJson?.disciplines||[]).includes(discipline))
      &&(!needle||[item.title,item.description,item.reason,item.insightType].some(value=>(value||"").toLowerCase().includes(needle))));
  },[items,search,discipline,focusedInsightId]);
  const load=useCallback(async()=>{if(!projectId)return;setLoading(true);try{const [summary,insights]=await Promise.all([api.aiIntelligence.overview(projectId),api.aiIntelligence.insights(projectId,filters)]);setOverview(summary);setItems(insights);}catch(error){toast.error(errorMessage(error,t("errors.intelligenceLoadFailed")));}finally{setLoading(false);}},[filters,projectId]);
  useEffect(()=>{void load();},[load]);
  // Matches the `action` handler below: the specific backend reason (e.g. a
  // 403 from a revoked capability, or "no processed IFC revision") is more
  // useful than one fixed sentence that hides it regardless of cause.
  const run=async()=>{if(!projectId)return;setBusy("run");try{await api.aiIntelligence.run(projectId,overview?.latestRevision?.id);toast.success(t("ai.refreshSucceeded"));await load();}catch(error){toast.error(errorMessage(error,t("errors.intelligenceRunFailed")));}finally{setBusy("");}};
  const insightText=useInsightText();
  const action=async(id:string,operation:()=>Promise<unknown>,message:string)=>{setBusy(id);try{await operation();toast.success(message);await load();}catch(error){toast.error(errorMessage(error,t("errors.reviewActionFailed")));}finally{setBusy("");}};
  const open3D=(item:AIInsight)=>{const ids=item.affectedJson?.elements||[];navigate(`${workspace.path("ifc")}?tab=viewer&elementIds=${encodeURIComponent(ids.join(","))}`);};
  if(!projectId)return <Card>{t("empty.selectProject")}</Card>;
  if(loading&&!overview)return <LoadingState label={t("common.loading")}/>;
  const alignment=overview?.alignment;
  return <div className="page-container space-y-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="flex items-center gap-2 text-sm font-semibold text-primary"><Sparkles size={16}/> {t("ai.subtitle")}</p><h1 className="mt-1 text-2xl font-bold">{t("ai.title")}</h1><p className="mt-1 text-sm text-muted-foreground">{t("ai.intro")}</p></div><Button disabled={busy==="run"} onClick={()=>void run()}><RefreshCw className={busy==="run"?"animate-spin":""} size={16}/> {t("ai.refreshAnalysis")}</Button></div>
    <Card className="border-state-review/30 bg-wash-review/40"><div className="flex gap-3"><ShieldAlert className="text-state-review"/><div><b>{t("ai.reviewRequired")}</b><p className="text-sm text-muted-foreground">{t("ai.reviewRequiredHint")}</p></div></div></Card>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6"><Card><p className="text-xs text-muted-foreground">{t("ai.openInsights")}</p><p className="mt-2 text-3xl font-bold">{overview?.openInsights||0}</p></Card><Card><p className="text-xs text-muted-foreground">{t("ai.critical")}</p><p className="mt-2 text-3xl font-bold text-state-overdue">{overview?.severityCounts.CRITICAL||0}</p></Card><Card><p className="text-xs text-muted-foreground">{t("ai.warnings")}</p><p className="mt-2 text-3xl font-bold text-state-review">{overview?.severityCounts.WARNING||0}</p></Card><Card><p className="text-xs text-muted-foreground">{t("ai.suggestions")}</p><p className="mt-2 text-3xl font-bold">{overview?.severityCounts.SUGGESTION||0}</p></Card><Card className="xl:col-span-2"><p className="text-xs text-muted-foreground">{t("ai.alignment")}</p><div className="mt-2 flex items-end gap-3"><p className="text-3xl font-bold">{alignment?.overall??0}%</p><Badge variant={(alignment?.overall||0)<50?"warning":"success"}>{(alignment?.overall||0)<50?t("ai.alignmentReview"):t("ai.alignmentAligned")}</Badge></div><p className="mt-2 text-xs text-muted-foreground">{t("ai.latestRevision",{revision:overview?.latestRevision?.revisionCode||overview?.latestRevision?.title||t("common.notAvailable")})}</p></Card></div>
    {alignment&&<Card><div className="flex items-center gap-2"><Target/><h2 className="font-semibold">{t("aIIntelligencePage.transparent_alignment_score")}</h2></div><p className="mt-1 text-sm text-muted-foreground">{t("aIIntelligencePage.weighted_structured_metrics_no")}</p><div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-5">{Object.entries(alignment.components).map(([key,value])=><div key={key}><div className="flex justify-between text-xs"><span>{labelize(key)}</span><b>{value}%</b></div><div className="mt-2 h-2 rounded bg-muted"><div className="h-full rounded bg-primary" style={{width:`${Math.min(100,value)}%`}}/></div><p className="mt-1 text-[11px] text-muted-foreground">Weight {alignment.weights[key]}%</p></div>)}</div><details className="mt-4 rounded border p-3 text-sm"><summary className="cursor-pointer font-medium">{t("aIIntelligencePage.calculation_evidence")}</summary><div className="mt-3 grid gap-2 sm:grid-cols-2"><p>IFC disciplines: {Object.entries(alignment.ifcDisciplines).map(([key,value])=>`${labelize(key)} ${value}`).join(" · ")||"None"}</p><p>Task disciplines: {Object.entries(alignment.taskDisciplines).map(([key,value])=>`${labelize(key)} ${value}`).join(" · ")||"None"}</p><p>Linked tasks: {alignment.linkedTaskCount} / {alignment.taskCount}</p><p>Linked issues: {alignment.linkedIssueCount} / {alignment.issueCount}</p></div></details></Card>}
    <Card><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">{t("ai.reviewQueue")}</h2><p className="text-sm text-muted-foreground">{t("ai.reviewQueueHint")}</p></div><div className="flex flex-wrap gap-2">
      <input className={selectClass} placeholder={t("ai.searchFindings")} value={search} onChange={e=>setSearch(e.target.value)} aria-label={t("ai.searchFindings")}/>
      <select className={selectClass} value={filters.status} onChange={e=>setFilters(v=>({...v,status:e.target.value}))} aria-label={t("ai.reviewQueue")}><option value="">{t("ai.allReviewStates")}</option>{REVIEW_STATES.map(v=><option key={v.value} value={v.value}>{t("ai.reviewState."+v.value,{defaultValue:v.label})}</option>)}</select>
      <select className={selectClass} value={filters.severity} onChange={e=>setFilters(v=>({...v,severity:e.target.value}))} aria-label={t("issue.severity")}><option value="">{t("ai.allSeverities")}</option>{severityOptions.map(v=><option key={v} value={v}>{t("ai.severity."+v,{defaultValue:labelize(v)})}</option>)}</select>
      {/* Categories come from the findings themselves; a hard-coded list silently filtered everything out. */}
      <select className={selectClass} value={filters.category} onChange={e=>setFilters(v=>({...v,category:e.target.value}))} aria-label={t("common.category")}><option value="">{t("ai.allCategories")}</option>{categoryOptions.map(v=><option key={v} value={v}>{insightCategory(v)}</option>)}</select>
      {!!disciplineOptions.length&&<select className={selectClass} value={discipline} onChange={e=>setDiscipline(e.target.value)} aria-label={t("common.discipline")}><option value="">{t("ai.allDisciplines")}</option>{disciplineOptions.map(v=><option key={v} value={v}>{vocabulary.discipline(v)}</option>)}</select>}
    </div></div>
    <p className="mt-3 text-xs text-muted-foreground">{t("ai.showingCount",{visible:visible.length,total:items.length})}</p>{focusedInsightId&&<p className="mt-2 text-xs"><b>{t("ai.openedFromLink")}</b> <button className="font-medium text-primary underline" onClick={()=>{const next=new URLSearchParams(searchParams);next.delete("insightId");setSearchParams(next,{replace:true});}}>{t("ai.showAllFindings")}</button></p>}</Card>
    {!visible.length?<Card><div className="py-10 text-center"><Bot className="mx-auto text-muted-foreground"/><p className="mt-3 font-semibold">{t("empty.noInsights")}</p><p className="text-sm text-muted-foreground">{t("ai.reviewQueueHint")}</p></div></Card>:<div className="grid gap-4 xl:grid-cols-2">{visible.map(item=><Card key={item.id} className={item.severity==="CRITICAL"?"border-state-overdue/30":item.severity==="WARNING"?"border-state-review/30":""}><div className="flex items-start justify-between gap-3"><div className="flex gap-3">{item.category==="SUGGESTED_TASK"?<ClipboardList className="mt-1 text-primary"/>:<AlertTriangle className="mt-1 text-state-review"/>}<div><div className="flex flex-wrap gap-2"><Badge variant={severityVariant(item.severity)}>{t("ai.severity."+item.severity,{defaultValue:labelize(item.severity)})}</Badge><Badge>{insightCategory(item.category)}</Badge><Badge variant="info">{t("ai.confidence",{value:Math.round(item.confidence*100)})}</Badge></div><h3 className="mt-3 text-lg font-bold">{insightText(item,"title")}</h3></div></div><Badge variant={["OPEN","NEW"].includes(item.status)?"warning":item.status==="RESOLVED"?"success":"neutral"}>{t("ai.reviewState."+item.status,{defaultValue:REVIEW_STATES.find(state=>state.value===item.status)?.label||labelize(item.status)})}</Badge></div><p className="mt-4 text-sm leading-6">{insightText(item,"description")}</p><div className="mt-4 grid gap-3 sm:grid-cols-2"><div className="rounded-lg bg-muted/40 p-3"><p className="text-xs font-semibold">{t("ai.whyDetected")}</p><p className="mt-1 text-xs text-muted-foreground">{insightText(item,"reason")}</p></div><div className="rounded-lg bg-primary/5 p-3"><p className="text-xs font-semibold">{t("ai.recommendedAction")}</p><p className="mt-1 text-xs text-muted-foreground">{insightText(item,"recommendedAction")}</p></div></div><details className="mt-3 rounded border p-3 text-xs"><summary className="cursor-pointer font-medium">{t("ai.sourceEvidence")}</summary><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap">{JSON.stringify(item.evidenceJson,null,2)}</pre></details><div className="mt-4 flex flex-wrap gap-2">{!!item.affectedJson?.elements?.length&&<Button size="sm" variant="outline" onClick={()=>open3D(item)}><Eye size={15}/> {t("ai.viewIn3D")}</Button>}{["OPEN","NEW"].includes(item.status)&&<Button size="sm" variant="outline" disabled={busy===item.id} onClick={()=>void action(item.id,()=>api.aiIntelligence.review(projectId,item.id,"ACKNOWLEDGED"),"Insight acknowledged for review")}>{t("collaboration.acknowledge")}</Button>}<Button size="sm" variant="outline" disabled={busy===item.id} onClick={()=>void action(item.id,()=>api.aiIntelligence.review(projectId,item.id,"FALSE_POSITIVE"),"Insight dismissed")}>{t("ai.dismiss")}</Button><Button size="sm" variant="outline" disabled={busy===item.id} onClick={()=>void action(item.id,()=>api.aiIntelligence.review(projectId,item.id,"RESOLVED"),"Insight resolved")}><CheckCircle2 size={15}/> {t("ai.resolve")}</Button>{item.category==="SUGGESTED_TASK"&&role==="project_manager"&&!item.appliedEntityId&&<Button size="sm" disabled={busy===item.id} onClick={()=>void action(item.id,()=>api.aiIntelligence.createTask(projectId,item.id),"Task created for review")}>{t("ai.createTask")}</Button>}{item.category!=="SUGGESTED_TASK"&&!item.appliedEntityId&&["project_manager","engineer"].includes(role||"")&&<Button size="sm" disabled={busy===item.id} onClick={()=>void action(item.id,()=>api.aiIntelligence.createIssue(projectId,item.id),"Issue created")}>{t("ai.createIssue")}</Button>}</div></Card>)}</div>}
    {!!visible.length&&<Card><h2 className="font-semibold">{t("ai.sourcesUsed")}</h2><p className="text-sm text-muted-foreground">{t("aIIntelligencePage.open_an_insight_below_to_see_the_current")}</p><div className="mt-3 space-y-2">{visible.map(item=><div key={item.id}><p className="text-xs font-medium">{insightText(item,"title")}</p><AIInsightSources projectId={projectId} insightId={item.id} fallback={item.evidenceJson}/></div>)}</div></Card>}
  </div>;
};
