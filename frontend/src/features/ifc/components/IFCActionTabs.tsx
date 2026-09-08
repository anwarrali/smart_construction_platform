import { useEffect, useMemo, useState } from "react";
import { useVocabulary } from "../../../utils/vocabulary";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { AlertTriangle, Ban, Box, Check, EyeOff, GitCompareArrows, RefreshCw, ShieldAlert, ShieldCheck, TicketPlus, WandSparkles } from "lucide-react";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import api from "../../../services/api";
import type { IFCComparison, IFCFinding, IFCInterferenceReport, IFCSuggestion, IFCSummary, IFCVersion } from "../../../types/ifc";
import { EmptyState, ErrorState, labelize, LoadingState } from "./IFCShared";

// Sentinels for the four fixed UI-facing change categories, translated at
// render time via `translateArea` (this function has no `t` in scope — it is
// called from `changeAreas(change).map(...)` in JSX). Identity field names
// (e.g. `GlobalId`) come from the IFC data itself, not from this fixed set,
// so they are only humanized via `labelize`, never translated: they are
// dynamic IFC-standard attribute names, not application copy.
const AREA_LABEL_KEYS: Record<string, string> = {
  __PROPERTIES__: "ifcActions.properties",
  __QUANTITIES__: "ifcActions.quantities",
  __COORDINATES__: "ifcActions.coordinates_spatial_assignment",
  __REPRESENTATION__: "ifcActions.representation",
};
const translateArea = (area: string, t: (key: string) => string) =>
  AREA_LABEL_KEYS[area] ? t(AREA_LABEL_KEYS[area]) : area;

const changeAreas = (change: Record<string, unknown>) => {
  const payload = (change.propertyChanges || {}) as { properties?: Record<string, unknown>; quantities?: Record<string, unknown>; identity?: Record<string, unknown> };
  const areas: string[] = [];
  if (Object.keys(payload.properties || {}).length) areas.push("__PROPERTIES__");
  if (Object.keys(payload.quantities || {}).length) areas.push("__QUANTITIES__");
  Object.keys(payload.identity || {}).forEach((key) => areas.push(labelize(key)));
  if ((change.locationChange as { before?: unknown } | undefined)?.before) areas.push("__COORDINATES__");
  if ((change.geometryChange as { changed?: boolean } | undefined)?.changed) areas.push("__REPRESENTATION__");
  return Array.from(new Set(areas));
};

export const CompareTab = ({ projectId, versions, currentVersionId }: { projectId: string; versions: IFCVersion[]; currentVersionId: string }) => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const [baseId, setBaseId] = useState(""); const [targetId, setTargetId] = useState(currentVersionId);
  const [comparisons, setComparisons] = useState<IFCComparison[]>([]); const [changes, setChanges] = useState<Array<Record<string, unknown>>>([]);
  const [changeType, setChangeType] = useState(""); const [severity, setSeverity] = useState(""); const [discipline, setDiscipline] = useState(""); const [storey, setStorey] = useState(""); const [ifcClass, setIfcClass] = useState("");
  const [selectedComparison, setSelectedComparison] = useState(""); const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [reload, setReload] = useState(0);
  useEffect(() => setTargetId(currentVersionId), [currentVersionId]);
  useEffect(() => { setLoading(true); setError(""); void api.ifc.comparisons(projectId).then(setComparisons).catch((reason) => { console.error("[IFC Intelligence:Compare] loading failed", reason); setError(t("ifcActions.revision_comparisons_could_not_be_loaded")); }).finally(() => setLoading(false)); }, [projectId, reload, t]);
  useEffect(() => { if (!selectedComparison) { setChanges([]); return; } void api.ifc.comparisonChanges(projectId, selectedComparison).then(setChanges).catch((reason) => console.error("[IFC Intelligence:Compare] changes failed", reason)); }, [projectId, selectedComparison]);
  const run = async () => { if (!baseId || !targetId) return; setBusy(true); try { const item = await api.ifc.compare(projectId, baseId, targetId); setComparisons(await api.ifc.comparisons(projectId)); setSelectedComparison(item.id); toast.success(t("ifcActions.revision_comparison_completed")); } catch (reason) { toast.error(errorMessage(reason)); } finally { setBusy(false); } };
  const visibleChanges = useMemo(() => changes.filter((item) => (!changeType || item.changeType === changeType) && (!severity || item.severity === severity) && (!discipline || item.discipline === discipline) && (!storey || item.storey === storey) && (!ifcClass || item.ifcClass === ifcClass)), [changeType, changes, discipline, ifcClass, severity, storey]);
  const confidenceLabel = (level?: string) => level === "LOW" ? t("ifcActions.confidence_low") : level === "HIGH" ? t("ifcActions.confidence_high") : t("ifcActions.confidence_pending");
  if (versions.length < 2) return <EmptyState title={t("ifcActions.upload_another_model_revision_to_enable")} description={t("ifcActions.comparison_requires_two_revisions")}/>;
  if (loading) return <LoadingState label={t("ifcActions.loading_revision_comparisons")}/>;
  if (error) return <ErrorState message={error} onRetry={() => setReload((value) => value + 1)}/>;
  return <div className="space-y-4"><Card><h2 className="flex items-center gap-2 font-semibold"><GitCompareArrows size={18}/> {t("ifcActions.compare_revisions")}</h2><p className="mt-1 text-sm text-muted-foreground">{t("ifcActions.stable_globalids_are_used")}</p><div className="mt-4 flex flex-wrap gap-3"><select aria-label={t("ifcActions.base_revision")} className="rounded-md border bg-background px-3 py-2 text-sm" value={baseId} onChange={(event) => setBaseId(event.target.value)}><option value="">{t("ifcActions.base_revision")}</option>{versions.filter((item) => item.id !== targetId).map((item) => <option key={item.id} value={item.id}>v{item.versionNumber} · {item.revisionCode || item.title}</option>)}</select><select aria-label={t("ifcActions.comparison_revision")} className="rounded-md border bg-background px-3 py-2 text-sm" value={targetId} onChange={(event) => setTargetId(event.target.value)}><option value="">{t("ifcActions.comparison_revision")}</option>{versions.filter((item) => item.id !== baseId).map((item) => <option key={item.id} value={item.id}>v{item.versionNumber} · {item.revisionCode || item.title}</option>)}</select><Button disabled={!baseId || !targetId || busy} isLoading={busy} onClick={() => void run()}>{t("ifcActions.compare_revisions")}</Button></div></Card>
    {!comparisons.length ? <EmptyState title={t("ifcActions.no_comparisons_have_been_run")} description={t("ifcActions.select_a_base_and_comparison")}/> : comparisons.map((item) => <Card key={item.id} className={selectedComparison === item.id ? "border-primary" : ""} onClick={() => setSelectedComparison(item.id)}><div className="flex flex-wrap items-start justify-between gap-3"><div><b>{versions.find((version) => version.id === item.baseVersionId)?.revisionCode || t("ifcActions.base")} → {versions.find((version) => version.id === item.targetVersionId)?.revisionCode || t("ifcActions.comparison")}</b><p className="text-xs text-muted-foreground">{item.summaryJson.confidenceMessage}</p></div><div className="flex gap-2"><Badge variant={item.summaryJson.comparisonConfidence === "LOW" ? "warning" : "success"}>{t("ifcActions.confidence_suffix", { level: confidenceLabel(item.summaryJson.comparisonConfidence) })}</Badge><Badge>{vocabulary.term(item.status)}</Badge></div></div>{item.summaryJson.comparisonConfidence === "LOW" && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{t("ifcActions.unstable_identifiers_warning", { count: item.summaryJson.unstableIdentifierCount || 0 })}</p>}<div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">{Object.entries(item.summaryJson.counts || {}).map(([key, value]) => <div key={key} className="rounded bg-muted/40 p-3"><p className="text-xs">{labelize(key)}</p><b>{value}</b></div>)}</div>{selectedComparison === item.id && !!changes.length && <div className="mt-4"><div className="mb-3 grid gap-2 md:grid-cols-5"><select className="rounded-md border bg-background px-2 py-2 text-sm" value={changeType} onChange={(event) => setChangeType(event.target.value)}><option value="">{t("ifcActions.all_change_types")}</option>{Array.from(new Set(changes.map((change) => String(change.changeType)))).map((value) => <option key={value}>{value}</option>)}</select><select className="rounded-md border bg-background px-2 py-2 text-sm" value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="">{t("ifcActions.all_severities")}</option>{Array.from(new Set(changes.map((change) => String(change.severity)))).map((value) => <option key={value}>{value}</option>)}</select><select className="rounded-md border bg-background px-2 py-2 text-sm" value={discipline} onChange={(event) => setDiscipline(event.target.value)}><option value="">{t("ifcActions.all_disciplines")}</option>{Array.from(new Set(changes.map((change) => String(change.discipline || "UNCLASSIFIED")))).map((value) => <option key={value}>{value}</option>)}</select><select className="rounded-md border bg-background px-2 py-2 text-sm" value={storey} onChange={(event) => setStorey(event.target.value)}><option value="">{t("ifcActions.all_storeys")}</option>{Array.from(new Set(changes.map((change) => String(change.storey || "Not assigned")))).map((value) => <option key={value}>{value}</option>)}</select><select className="rounded-md border bg-background px-2 py-2 text-sm" value={ifcClass} onChange={(event) => setIfcClass(event.target.value)}><option value="">{t("ifcActions.all_ifc_classes")}</option>{Array.from(new Set(changes.map((change) => String(change.ifcClass || "Unknown")))).map((value) => <option key={value}>{value}</option>)}</select></div><div className="overflow-auto"><table className="w-full min-w-[1050px] text-sm"><thead><tr className="border-b text-left"><th className="p-2">{t("ifcActions.element")}</th><th className="p-2">{t("ifcActions.ifc_class")}</th><th className="p-2">{t("ifcActions.change_type")}</th><th className="p-2">{t("ifcActions.changed_data")}</th><th className="p-2">{t("ifcActions.discipline")}</th><th className="p-2">{t("ifcActions.storey")}</th><th className="p-2">{t("ifcActions.severity")}</th><th className="p-2">{t("ifcActions.match_confidence")}</th></tr></thead><tbody>{visibleChanges.slice(0, 100).map((change, index) => <tr key={String(change.id || index)} className="border-b"><td className="p-2">{String(change.elementName || change.globalId || "Unknown element")}</td><td className="p-2">{String(change.ifcClass || "Unknown")}</td><td className="p-2">{labelize(String(change.changeType || "MODIFIED"))}</td><td className="p-2"><div className="flex max-w-72 flex-wrap gap-1">{changeAreas(change).map((area) => <Badge key={area} size="sm" variant="info">{translateArea(area, t)}</Badge>)}{!changeAreas(change).length && <span className="text-muted-foreground">{t("ifcActions.element_added_or_removed")}</span>}</div></td><td className="p-2">{labelize(String(change.discipline || "UNCLASSIFIED"))}</td><td className="p-2">{String(change.storey || "Not assigned")}</td><td className="p-2"><Badge>{String(change.severity || "LOW")}</Badge></td><td className="p-2">{Math.round(Number(change.matchConfidence || 0) * 100)}%</td></tr>)}</tbody></table></div></div>}</Card>)}</div>;
};

const severityVariant = (severity: string) => severity === "CRITICAL" || severity === "HIGH" ? "danger" : severity === "MEDIUM" ? "warning" : severity === "INFORMATION" ? "info" : "neutral";
/**
 * The extra panel a geometry-derived finding needs.
 *
 * A model-quality finding is a statement about the file; this is a statement
 * about two physical elements, so it has to name both, show the measured
 * overlap, and say plainly that a bounding-box overlap is a candidate rather
 * than a confirmed clash. Presenting it with the same certainty as "materials
 * are missing" would be the exact false-confidence the rule is built to avoid.
 */
const InterferenceDetail = ({ item }: { item: IFCFinding }) => {
  const { t } = useTranslation();
  const pair = item.elementPair;
  if (!pair?.structural || !pair.service) return null;
  const party = (value: NonNullable<IFCFinding["elementPair"]>["structural"]) => (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{value?.discipline ? labelize(value.discipline) : t("ifcActions.discipline")}</p>
      <b className="block text-sm">{value?.name}</b>
      <p className="font-mono text-xs text-muted-foreground">{value?.entityType} · {value?.globalId}</p>
    </div>
  );
  return <div className="mt-4 space-y-3">
    <div className="grid gap-3 md:grid-cols-2">{party(pair.structural)}{party(pair.service)}</div>
    <div className="flex flex-wrap gap-4 text-sm">
      {pair.penetrationMetres != null && <span><span className="text-muted-foreground">{t("ifcActions.overlap_depth")}:</span> <b>{pair.penetrationMetres} m</b></span>}
      {item.storey && <span><span className="text-muted-foreground">{t("ifcActions.location")}:</span> <b>{item.storey}</b></span>}
    </div>
    {item.verification && <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{t("ifcActions.candidate_not_confirmed")} {item.verification}</p>}
  </div>;
};

/**
 * The four decisions the server accepts on a finding, as the card offers them.
 *
 * `CREATE_ISSUE` is not a review status — it is a separate route that opens an
 * issue and then sets the finding to `ISSUE_CREATED` itself — but it belongs in
 * the same list because it is the fourth thing a reviewer can do with a card,
 * and it shares the one-action-at-a-time guard with the other three.
 */
type FindingAction = "ACKNOWLEDGED" | "IGNORED" | "FALSE_POSITIVE" | "CREATE_ISSUE";

/**
 * Element ids a finding can hand the 3D viewer.
 *
 * `affectedElementIds` carries database element ids, not IFC GlobalIds:
 * `list_findings` builds them from `evidence.elementIds`, which both the
 * metadata-quality rules and the interference rule write as `str(element.id)`.
 * That matters because the viewer matches `focus.elementIds` against the `id`
 * field of its ExpressID→element mapping, which is the same database id.
 * Suggestions carry `relatedGlobalIds` instead, and are deliberately not
 * routed through here.
 */
//: Findings per page. The server caps a page at 200; 50 keeps the review
//: queue readable while leaving the pager rarely needed on a tidy model.
const FINDINGS_PAGE_SIZE = 50;

const focusableElementIds = (item: IFCFinding) => item.affectedElementIds.filter(Boolean);

/**
 * What the interference rule actually did on this revision.
 *
 * The rule is scrupulous about the difference between "checked and found
 * nothing" and "could not check", and records the second as
 * `analysed: false` with a `skippedReason`. The workspace used to discard that
 * distinction at the last hop: both arrived at the same "No model quality
 * findings" card, so a revision whose geometry was never tessellated read as a
 * clean bill of health. That is precisely the false confidence the engine is
 * built to avoid, reintroduced in the interface.
 *
 * `NOT_RECORDED` is a third state and not a synonym for skipped: when
 * coordination checks are off, or a revision predates the rule, nothing is
 * written to the summary at all, so there is no reason to report.
 */
type AnalysisOutcome = "ANALYSED" | "SKIPPED" | "NOT_RECORDED";

const analysisOutcome = (summary?: IFCSummary): { outcome: AnalysisOutcome; report: IFCInterferenceReport } => {
  const report = summary?.interference;
  if (!report || report.analysed === undefined) return { outcome: "NOT_RECORDED", report: report || {} };
  return { outcome: report.analysed ? "ANALYSED" : "SKIPPED", report };
};

/**
 * The stated reason, in the reader's language.
 *
 * Written as literal `t()` calls rather than a lookup table so the catalogue
 * coverage tests can see every key. An unrecognized reason still renders —
 * carrying the raw code — because a reason the client does not know about is
 * still a reason the model was not checked.
 */
const SkippedReason = ({ reason }: { reason?: string | null }) => {
  const { t } = useTranslation();
  if (reason === "UNKNOWN_LENGTH_UNIT") return <>{t("ifcActions.analysis_skipped_unknown_length_unit")}</>;
  if (reason === "NO_ELEMENT_GEOMETRY_AVAILABLE") return <>{t("ifcActions.analysis_skipped_no_element_geometry")}</>;
  if (reason === "NO_STRUCTURAL_AND_SERVICE_PAIR_AVAILABLE") return <>{t("ifcActions.analysis_skipped_no_structural_service_pair")}</>;
  if (reason === "DISABLED_OR_MISSING_VERSION") return <>{t("ifcActions.analysis_skipped_checks_disabled")}</>;
  if (reason) return <>{t("ifcActions.analysis_skipped_unspecified", { reason: labelize(reason) })}</>;
  return <>{t("ifcActions.analysis_skipped_no_reason_given")}</>;
};

/**
 * The banner above the findings list, saying what was and was not checked.
 *
 * Always rendered, in all three states. A confirmation that the rule ran is
 * what makes an empty list trustworthy, and printing it only in the bad cases
 * would leave the reader unable to tell a checked model from an unchecked one
 * without knowing this component's rules.
 */
const AnalysisStateBanner = ({ outcome, report }: { outcome: AnalysisOutcome; report: IFCInterferenceReport }) => {
  const { t } = useTranslation();
  if (outcome === "ANALYSED") {
    return <Card className="border-emerald-200 bg-emerald-50/60">
      <div className="flex gap-3">
        <ShieldCheck className="mt-0.5 shrink-0 text-emerald-600" size={18}/>
        <div>
          <h3 className="font-semibold">{t("ifcActions.analysis_completed")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t("ifcActions.analysis_completed_detail", {
            structural: report.structuralElements ?? 0, service: report.serviceElements ?? 0,
          })}</p>
          {!!report.truncated && <p className="mt-2 text-sm text-amber-900">{t("ifcActions.analysis_result_truncated")}</p>}
        </div>
      </div>
    </Card>;
  }
  const skipped = outcome === "SKIPPED";
  return <Card className={skipped ? "border-amber-300 bg-amber-50" : "border-slate-300 bg-muted/40"}>
    <div className="flex gap-3">
      <ShieldAlert className={`mt-0.5 shrink-0 ${skipped ? "text-amber-600" : "text-muted-foreground"}`} size={18}/>
      <div>
        <h3 className="font-semibold">{skipped ? t("ifcActions.analysis_could_not_run") : t("ifcActions.analysis_not_recorded")}</h3>
        <p className="mt-1 text-sm">
          {skipped ? <SkippedReason reason={report.skippedReason}/> : t("ifcActions.analysis_not_recorded_detail")}
        </p>
        {/* Said plainly, because it is the whole point of the banner: an empty
            list below this is not a clean result. */}
        <p className="mt-2 text-sm font-medium">{t("ifcActions.absence_is_not_a_clean_result")}</p>
        <p className="mt-2 text-xs text-muted-foreground">{t("ifcActions.metadata_checks_still_ran")}</p>
      </div>
    </div>
  </Card>;
};

export const FindingsTab = ({ projectId, versionId, summary, canReview, canCreateIssue, onViewElements, onFocus3D }: { projectId: string; versionId: string; summary?: IFCSummary; canReview: boolean; canCreateIssue: boolean; onViewElements: (ids: string[]) => void; onFocus3D?: (elementIds: string[]) => void }) => {
  const vocabulary = useVocabulary();
  const { t } = useTranslation();
  const [items, setItems] = useState<IFCFinding[]>([]); const [total, setTotal] = useState(0); const [page, setPage] = useState(1); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [reload, setReload] = useState(0); const [severity, setSeverity] = useState(""); const [discipline, setDiscipline] = useState("");
  /* `${findingId}:${action}` for as long as one call is in flight. Keyed rather
     than a plain boolean so only the pressed button shows a spinner, while
     every action stays disabled meanwhile: a second "Create issue" click would
     hit 409 against the status the first click has already set. */
  const [busy, setBusy] = useState("");
  /* Severity and discipline are sent to the server rather than applied here:
     once the list is paged, filtering in the browser would filter the current
     page only and quietly hide matches sitting on the next one. */
  useEffect(() => { setLoading(true); setError(""); void api.ifc.findings(projectId, { versionId, severity: severity || undefined, discipline: discipline || undefined, page, pageSize: FINDINGS_PAGE_SIZE }).then((response) => { setItems(response.items); setTotal(response.total); }).catch((reason) => { console.error("[IFC Intelligence:Findings] loading failed", reason); setError(t("ifcActions.model_quality_findings_could_not_be_loaded")); }).finally(() => setLoading(false)); }, [discipline, page, projectId, reload, severity, t, versionId]);
  /* A filter change re-queries from the first page; staying on page 4 of the
     previous result would land on an empty page for no visible reason. The
     two selects reset it in their own handlers below; `versionId` is a prop,
     so it is adjusted during render — React's documented way to derive state
     from a changed prop, and it avoids the extra pass an effect would add. */
  const [lastVersionId, setLastVersionId] = useState(versionId);
  if (versionId !== lastVersionId) { setLastVersionId(versionId); setPage(1); }
  const visible = items;
  const totalPages = Math.max(1, Math.ceil(total / FINDINGS_PAGE_SIZE));
  const disciplines = Array.from(new Set(items.flatMap((item) => item.disciplines))).sort();
  const { outcome, report } = analysisOutcome(summary);

  /* The reviewed card is replaced in place rather than the list re-fetched, so
     the severity and discipline filters above keep their values and the page
     keeps its scroll position. The server tells us the status it stored; the
     action we asked for is the fallback, because the review routes return the
     ORM row rather than the camelCase shape the list endpoint assembles. */
  const applyStatus = (id: string, status: string) => setItems((values) => values.map((item) => item.id === id ? { ...item, status } : item));

  const act = async (item: IFCFinding, action: FindingAction) => {
    if (busy) return;
    setBusy(`${item.id}:${action}`);
    try {
      if (action === "CREATE_ISSUE") {
        const issue = await api.ifc.createIssueFromFinding(projectId, item.id);
        applyStatus(item.id, "ISSUE_CREATED");
        toast.success(t("ifcActions.issue_created_from_finding", { title: issue.title }));
      } else {
        const result = action === "IGNORED"
          ? await api.ifc.ignoreFinding(projectId, item.id)
          : action === "FALSE_POSITIVE"
            ? await api.ifc.markFindingFalsePositive(projectId, item.id)
            : await api.ifc.reviewFinding(projectId, item.id, "ACKNOWLEDGED");
        applyStatus(item.id, result?.status || action);
        toast.success(action === "IGNORED" ? t("ifcActions.finding_ignored") : action === "FALSE_POSITIVE" ? t("ifcActions.finding_marked_false_positive") : t("ifcActions.finding_acknowledged"));
      }
    } catch (reason) {
      // One failed card must not empty the list: nothing is removed here and
      // the finding keeps the status it had, so the rest stays reviewable.
      console.error("[IFC Intelligence:Findings] review action failed", reason);
      toast.error(errorMessage(reason, t("ifcActions.finding_action_failed")));
    } finally { setBusy(""); }
  };

  /* The filters and the analysis banner stay mounted while a reload runs.
     Returning a bare loading card here used to be harmless when filtering
     happened in the browser; now that a filter change re-queries, it would
     unmount the very select the reader just used, on every change. */
  if (error) return <ErrorState message={error} onRetry={() => setReload((value) => value + 1)}/>;
  return <div className="space-y-4"><Card><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">{t("ifcActions.model_quality_findings")}</h2><p className="text-sm text-muted-foreground">{t("ifcActions.normalized_and_deduplicated_by_ifc_rule")}</p></div><div className="flex gap-2"><select aria-label={t("ifcActions.finding_severity")} className="rounded-md border bg-background px-3 py-2 text-sm" value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }}><option value="">{t("ifcActions.all_severities")}</option>{["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATION"].map((value) => <option key={value}>{value}</option>)}</select><select aria-label={t("ifcActions.finding_discipline")} className="rounded-md border bg-background px-3 py-2 text-sm" value={discipline} onChange={(event) => { setDiscipline(event.target.value); setPage(1); }}><option value="">{t("ifcActions.all_disciplines")}</option>{disciplines.map((value) => <option key={value}>{value}</option>)}</select></div></div></Card><AnalysisStateBanner outcome={outcome} report={report}/>{loading ? <LoadingState label={t("ifcActions.loading_model_quality_findings")}/> : !visible.length ? (
    /* "No findings" is only a reassuring statement when the rule actually ran.
       When it did not, the banner above has already explained why, and this
       must not talk over it with a clean bill of health. */
    outcome === "ANALYSED"
      ? <EmptyState title={t("ifcActions.no_model_quality_findings")} description={t("ifcActions.no_findings_match_the_current")}/>
      : <EmptyState title={t("ifcActions.no_findings_recorded")} description={t("ifcActions.no_findings_recorded_detail")}/>
  ) : visible.map((item) => {
    const elementIds = focusableElementIds(item);
    const pending = item.status === "PENDING";
    const actionKey = (action: FindingAction) => `${item.id}:${action}`;
    return <Card key={item.id}><div className="flex flex-wrap items-start justify-between gap-3"><div className="max-w-3xl"><h3 className="flex items-center gap-2 font-semibold"><AlertTriangle size={17}/>{item.title}</h3><p className="mt-2 text-sm text-muted-foreground">{item.description}</p></div><div className="flex flex-wrap gap-2"><Badge variant={severityVariant(item.severity)}>{vocabulary.severity(item.severity)}</Badge>{item.confidence != null && item.confidence < 1 && <Badge variant="info">{t("ai.confidence", { value: Math.round(item.confidence * 100) })}</Badge>}</div></div><div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-4"><div><p className="text-xs text-muted-foreground">{t("ifcActions.affected_elements")}</p><b>{item.affectedElementCount}</b></div><div><p className="text-xs text-muted-foreground">{t("ifcActions.discipline")}</p><b>{item.discipline}</b></div><div><p className="text-xs text-muted-foreground">{t("ifcActions.ifc_rule_or_reason")}</p><b>{item.ifcRule}</b></div><div><p className="text-xs text-muted-foreground">{t("ifcActions.status")}</p><b>{labelize(item.status)}</b></div></div><div className="mt-4 grid gap-3 md:grid-cols-2"><div className="rounded-lg bg-muted/40 p-3"><p className="text-xs font-semibold">{t("ifcActions.why_it_matters")}</p><p className="mt-1 text-sm">{item.whyItMatters}</p></div><div className="rounded-lg bg-muted/40 p-3"><p className="text-xs font-semibold">{t("ifcActions.recommended_action")}</p><p className="mt-1 text-sm">{item.recommendedAction}</p></div></div><InterferenceDetail item={item}/>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => onViewElements(item.affectedElementIds)}>{t("ifcActions.view_affected_elements")}</Button>
        {!!elementIds.length && onFocus3D && <Button variant="outline" size="sm" onClick={() => onFocus3D(elementIds)}><Box size={15}/> {t("ifcActions.show_in_3d")}</Button>}
        {pending && canReview && <>
          <Button size="sm" disabled={!!busy} isLoading={busy === actionKey("ACKNOWLEDGED")} onClick={() => void act(item, "ACKNOWLEDGED")}><Check size={15}/> {t("ifcActions.acknowledge_finding")}</Button>
          <Button variant="outline" size="sm" disabled={!!busy} isLoading={busy === actionKey("IGNORED")} onClick={() => void act(item, "IGNORED")}><EyeOff size={15}/> {t("ifcActions.ignore_finding")}</Button>
          <Button variant="outline" size="sm" disabled={!!busy} isLoading={busy === actionKey("FALSE_POSITIVE")} onClick={() => void act(item, "FALSE_POSITIVE")}><Ban size={15}/> {t("ifcActions.mark_false_positive")}</Button>
          {canCreateIssue && <Button variant="outline" size="sm" disabled={!!busy} isLoading={busy === actionKey("CREATE_ISSUE")} onClick={() => void act(item, "CREATE_ISSUE")}><TicketPlus size={15}/> {t("ifcActions.create_issue_from_finding")}</Button>}
        </>}
      </div>
      {/* A finding the model never located — an aggregate about the file
          itself, or one whose elements were not extracted — has nothing for
          the viewer to focus, so it says so rather than offering a dead button. */}
      {!elementIds.length && <p className="mt-2 text-xs text-muted-foreground">{t("ifcActions.finding_has_no_model_element")}</p>}
    </Card>;
  })}
  {totalPages > 1 && <div className="flex flex-wrap items-center justify-between gap-3">
    <p className="text-sm text-muted-foreground">{t("ifcActions.findings_page_summary", { page, totalPages, total })}</p>
    <div className="flex gap-2">
      <Button variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => setPage((value) => value - 1)}>{t("common.previous")}</Button>
      <Button variant="outline" size="sm" disabled={page >= totalPages || loading} onClick={() => setPage((value) => value + 1)}>{t("common.next")}</Button>
    </div>
  </div>}</div>;
};

// `t` is threaded in explicitly (rather than called with `useTranslation` here)
// because this runs outside a component, as a plain `.map()` callback in
// `SuggestionsTab.load`. The fallbacks only surface when the backend sends a
// suggestion missing that field, so they are genuine UI copy, not IFC data.
const safeSuggestion = (value: unknown, t: (key: string) => string): IFCSuggestion | null => { if (!value || typeof value !== "object") return null; const item = value as Partial<IFCSuggestion>; if (!item.id || !item.versionId) return null; return { id: item.id, versionId: item.versionId, suggestionType: item.suggestionType || "REVIEW", payloadJson: item.payloadJson && typeof item.payloadJson === "object" ? item.payloadJson : {}, title: item.title || t("ifcActions.suggestion_default_title"), discipline: item.discipline || "UNCLASSIFIED", priority: item.priority || "MEDIUM", reason: item.reason || t("ifcActions.no_reason_was_supplied"), affectedElementCount: Number(item.affectedElementCount || 0), expectedBenefit: item.expectedBenefit || t("ifcActions.review_may_improve_model"), recommendedAction: item.recommendedAction || t("ifcActions.review_the_available_ifc_evidence"), sourceFinding: item.sourceFinding || t("ifcActions.ifc_model_analysis"), confidence: Number(item.confidence || 0), status: item.status || "PENDING", aiInferred: Boolean(item.aiInferred), createdAt: item.createdAt || "" }; };
export const SuggestionsTab = ({ projectId, versionId, canReview, canApply, onViewElements }: { projectId: string; versionId: string; canReview: boolean; canApply: boolean; onViewElements: (ids: string[]) => void }) => {
  const vocabulary = useVocabulary();
  const { t } = useTranslation();
  const [items, setItems] = useState<IFCSuggestion[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [reload, setReload] = useState(0); const [busyId, setBusyId] = useState("");
  const load = () => { setLoading(true); setError(""); void api.ifc.suggestions(projectId, versionId).then((values) => setItems(values.map((value) => safeSuggestion(value, t)).filter((item): item is IFCSuggestion => Boolean(item)))).catch((reason) => { console.error("[IFC Intelligence:Suggestions] loading failed", reason); setError(t("ifcActions.suggestions_could_not_be_loaded")); }).finally(() => setLoading(false)); };
  useEffect(load, [projectId, reload, versionId]);
  const review = async (item: IFCSuggestion, status: "ACCEPTED" | "REJECTED") => { setBusyId(item.id); try { await api.ifc.reviewSuggestion(projectId, item.id, status); toast.success(t(status === "ACCEPTED" ? "ifcActions.suggestion_accepted" : "ifcActions.suggestion_rejected")); setReload((value) => value + 1); } catch (reason) { console.error("[IFC Intelligence:Suggestions] review failed", reason); toast.error(errorMessage(reason)); } finally { setBusyId(""); } };
  if (loading) return <LoadingState label={t("ifcActions.loading_improvement_suggestions")}/>; if (error) return <ErrorState message={error} onRetry={() => setReload((value) => value + 1)}/>;
  return <div className="space-y-4"><Card className="border-amber-200"><div className="flex gap-3"><WandSparkles className="text-amber-600"/><div><h2 className="font-semibold">{t("ifcActions.improvement_suggestions")}</h2><p className="text-sm text-muted-foreground">{t("ifcActions.ai_review_note")}</p></div><Button className="ml-auto" variant="ghost" size="sm" onClick={() => setReload((value) => value + 1)}><RefreshCw size={15}/> {t("common.refresh")}</Button></div></Card>{!items.length ? <EmptyState title={t("ifcActions.no_improvement_suggestions_were")} description={t("ifcActions.the_model_analysis_remains")}/> : items.map((item) => <Card key={item.id}><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">{item.title}</h3><p className="mt-1 text-sm text-muted-foreground">{item.reason}</p></div><div className="flex gap-2"><Badge>{vocabulary.priority(item.priority)}</Badge><Badge variant="info">{t("ai.confidence", { value: Math.round(item.confidence * 100) })}</Badge></div></div><div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-4"><div><p className="text-xs text-muted-foreground">{t("ifcActions.discipline")}</p><b>{vocabulary.discipline(item.discipline)}</b></div><div><p className="text-xs text-muted-foreground">{t("ifcActions.affected_elements")}</p><b>{item.affectedElementCount}</b></div><div><p className="text-xs text-muted-foreground">{t("ifcActions.expected_benefit")}</p><p className="text-sm">{item.expectedBenefit}</p></div><div><p className="text-xs text-muted-foreground">{t("ifcActions.source_finding")}</p><p className="text-sm">{item.sourceFinding}</p></div></div><div className="mt-4 rounded-lg bg-muted/40 p-3"><p className="text-xs font-semibold">{t("ifcActions.recommended_action")}</p><p className="mt-1 text-sm">{item.recommendedAction}</p></div><div className="mt-4 flex flex-wrap gap-2">{!!item.affectedElementCount && <Button size="sm" variant="outline" onClick={() => onViewElements(Array.isArray(item.payloadJson.relatedGlobalIds) ? item.payloadJson.relatedGlobalIds.map(String) : [])}>{t("ifcActions.view_affected_elements")}</Button>}{item.status === "PENDING" && canReview && <Button size="sm" variant="outline" disabled={busyId === item.id} onClick={() => void review(item, "REJECTED")}>{t("ifcActions.reject")}</Button>}{item.status === "PENDING" && canApply && item.suggestionType !== "CREATE_MILESTONE" && <Button size="sm" disabled={busyId === item.id} onClick={() => void review(item, "ACCEPTED")}>{t("ifcActions.review_and_create")}</Button>}</div></Card>)}</div>;
};
