import { useCallback, useEffect, useMemo, useState } from "react";
import { errorMessage } from "../../../utils/errorMessage";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CalendarDays, CheckCircle2, Clock3, ExternalLink, MessageSquareWarning, Plus, RefreshCw, Sparkles, Users } from "lucide-react";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { useAuth } from "../../../hooks/useAuth";
import { useRole } from "../../../hooks/useRole";
import axios from "../../../services/axios";
import api from "../../../services/api";
import type { Project } from "../../../types/project";
import { projectEntityPath, projectModulePath } from "../../../utils/projectRoutes";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";

type Tab = "actions" | "requests" | "schedule" | "activity";
type OwnerRequest = { id: string; projectId: string; createdById: string; assignedToId?: string; title: string; description: string; category: string; discipline?: string; priority: string; status: string; room?: string; floor?: string; dueAt?: string; acknowledgedAt?: string; respondedAt?: string; responseText?: string; clarificationText?: string; convertedDesignChangeId?: string; createdAt: string; updatedAt: string };
type SiteVisit = { id: string; projectId: string; engineerId: string; title: string; scheduledStart: string; scheduledEnd: string; visitType: string; location?: string; notes?: string; status: string; participantIds: string[]; completedAt?: string };
type Activity = { id: string; occurredAt: string; action: string; entityType: string; entityId?: string; details: Record<string, unknown> };
type MessageAccountability = { messageId: string; status: string; reminderCount: number };
type ActionCenter = { generatedAt: string; counts: Record<string, number>; ownerRequests: OwnerRequest[]; messageAccountability: MessageAccountability[]; upcomingSiteVisits: SiteVisit[]; notifications: { id: string; title: string; message: string }[] };
type Member = { userId: string; fullName?: string; roleOnProject?: string; isActive?: boolean; user?: { id: string; fullName: string; role?: string; status?: string } };
/** A clashing visit, described well enough to judge without loading it. */
type VisitConflict = { id: string; title: string; projectId: string; projectName?: string; scheduledStart: string; scheduledEnd: string; visitType: string; status: string };

const humanize = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (x) => x.toUpperCase());
const dateTime = (value: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
const statusTone = (status: string) => status === "COMPLETED" || status === "ACCEPTED" ? "success" : status === "REJECTED" || status === "CANCELLED" ? "danger" : status === "NEEDS_CLARIFICATION" ? "warning" : "info";
// Every failure shape (string, validation array, structured object) is
// normalised centrally so a failed request can never crash the render.
const errorText = (error: unknown, fallback: string) => errorMessage(error, fallback);

/** Owner-request lifecycle rendered as a visible timeline (§18). */
const REQUEST_STAGES = ["SUBMITTED", "ASSIGNED", "UNDER_REVIEW", "NEEDS_CLARIFICATION", "ACCEPTED", "CONVERTED_TO_DESIGN_CHANGE", "COMPLETED"] as const;

const RequestTimeline = ({ request }: { request: OwnerRequest }) => {
  const { t } = useTranslation();
  const reached = (stage: string) => {
    if (stage === "SUBMITTED") return true;
    if (stage === "ASSIGNED") return Boolean(request.assignedToId);
    if (stage === "UNDER_REVIEW") return Boolean(request.acknowledgedAt) || REQUEST_STAGES.indexOf(request.status as any) >= 2;
    if (stage === "NEEDS_CLARIFICATION") return Boolean(request.clarificationText) || request.status === "NEEDS_CLARIFICATION";
    if (stage === "ACCEPTED") return Boolean(request.respondedAt) || ["ACCEPTED", "CONVERTED_TO_DESIGN_CHANGE", "COMPLETED"].includes(request.status);
    if (stage === "CONVERTED_TO_DESIGN_CHANGE") return Boolean(request.convertedDesignChangeId);
    return request.status === "COMPLETED";
  };
  const timeFor = (stage: string) =>
    stage === "SUBMITTED" ? request.createdAt
      : stage === "UNDER_REVIEW" ? request.acknowledgedAt
        : stage === "ACCEPTED" ? request.respondedAt
          : undefined;
  return (
    <ol className="mt-4 space-y-0">
      {REQUEST_STAGES.filter((stage) => stage !== "NEEDS_CLARIFICATION" || reached("NEEDS_CLARIFICATION")).map((stage) => {
        const done = reached(stage);
        const at = timeFor(stage);
        return (
          <li key={stage} className="flex gap-3 pb-4 last:pb-0">
            <div className="flex flex-col items-center">
              <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${done ? "bg-primary" : "bg-border"}`} />
              <span className="mt-1 w-px flex-1 bg-border last:hidden" />
            </div>
            <div className="-mt-0.5">
              <p className={`text-sm font-medium ${done ? "" : "text-muted-foreground"}`}>{t("ownerRequest.status." + stage, { defaultValue: humanize(stage) })}</p>
              {at && <p className="text-xs text-muted-foreground">{dateTime(at)}</p>}
              
            </div>
          </li>
        );
      })}
      {request.status === "REJECTED" && (
        <li className="flex gap-3"><span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-state-overdue" /><p className="-mt-0.5 text-sm font-medium">{t("ownerRequest.status.REJECTED")}</p></li>
      )}
    </ol>
  );
};

export const CollaborationPage = ({ initialTab = "actions" }: { initialTab?: Tab }) => {
  const { t } = useTranslation();
  const workspace = useProjectWorkspace();
  const { user } = useAuth();
  const { role, isProjectManager, isAdmin, isConsultantEngineer } = useRole();
  const affiliation = isConsultantEngineer ? ("external_consultant" as const) : undefined;
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<Tab>(initialTab);
  const [projects, setProjects] = useState<Project[]>(workspace.assignedProjects);
  const [projectId, setProjectId] = useState(workspace.projectId || "");
  const [requests, setRequests] = useState<OwnerRequest[]>([]);
  const [visits, setVisits] = useState<SiteVisit[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [actions, setActions] = useState<ActionCenter | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [requestOpen, setRequestOpen] = useState(false);
  const [visitOpen, setVisitOpen] = useState(false);
  const [requestForm, setRequestForm] = useState({ title: "", description: "", category: "GENERAL_REQUEST", discipline: "", priority: "NORMAL", floor: "", room: "" });
  const [visitForm, setVisitForm] = useState({ title: "", start: "", end: "", visitType: "ROUTINE_INSPECTION", location: "", engineerId: "", participantIds: [] as string[] });
  const [visitConflicts, setVisitConflicts] = useState<VisitConflict[]>([]);
  const [visitError, setVisitError] = useState("");
  const [requestStatus, setRequestStatus] = useState("");
  const [responseDraft, setResponseDraft] = useState("");
  const [clarificationDraft, setClarificationDraft] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [calendarView, setCalendarView] = useState<"upcoming" | "past" | "all">("upcoming");

  // Deep links from notifications, dashboards and AI insight sources.
  const focusedRequestId = searchParams.get("requestId");
  const focusedVisitId = searchParams.get("visitId");
  useEffect(() => {
    if (focusedRequestId) setTab("requests");
    else if (focusedVisitId) setTab("schedule");
  }, [focusedRequestId, focusedVisitId]);

  useEffect(() => {
    if (workspace.projectId) setProjectId(workspace.projectId);
    if (workspace.assignedProjects.length) setProjects(workspace.assignedProjects);
    if (!workspace.projectId && !workspace.assignedProjects.length) {
      api.projects.list({ limit: 100 }).then((response) => {
        setProjects(response.data || []);
        setProjectId((value) => value || response.data?.[0]?.id || "");
      }).catch(() => setProjects([]));
    }
  }, [workspace.projectId, workspace.assignedProjects]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const query = projectId ? `?project_id=${projectId}` : "";
      const [requestResult, visitResult, actionResult] = await Promise.all([
        axios.get<OwnerRequest[]>(`/owner-requests${query}`),
        axios.get<SiteVisit[]>(`/site-visits${query}`),
        axios.get<ActionCenter>(`/my-action-center${query}`),
      ]);
      setRequests(requestResult.data); setVisits(visitResult.data); setActions(actionResult.data);
      if (projectId) {
        setActivity((await axios.get<Activity[]>(`/projects/${projectId}/activity`)).data);
        api.projects.getMembers(projectId).then((data) => setMembers(data as unknown as Member[])).catch(() => setMembers([]));
      } else { setActivity([]); setMembers([]); }
    } catch (error: any) {
      toast.error(errorText(error, t("errors.collaborationLoadFailed")));
    } finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const memberName = useCallback((id?: string) => {
    if (!id) return "Unassigned";
    const found = members.find((item) => (item.user?.id || item.userId) === id);
    return found?.user?.fullName || found?.fullName || `${id.slice(0, 8)}…`;
  }, [members]);

  /* The API accepts a participant only when the membership is active *and* the
     user account is active. Offering the rest produced a form that looked
     complete and then failed with "All participants must belong to this
     project" on submit. */
  const selectableMembers = useMemo(
    () => members.filter((item) => item.isActive !== false && (item.user?.status ?? "active") === "active"),
    [members],
  );

  const filteredRequests = useMemo(() => requests.filter((item) => !requestStatus || item.status === requestStatus), [requests, requestStatus]);
  const focusedRequest = useMemo(() => requests.find((item) => item.id === focusedRequestId), [requests, focusedRequestId]);
  const visibleVisits = useMemo(() => {
    const now = Date.now();
    const sorted = [...visits].sort((a, b) => +new Date(a.scheduledStart) - +new Date(b.scheduledStart));
    if (calendarView === "upcoming") return sorted.filter((v) => +new Date(v.scheduledEnd) >= now && v.status !== "CANCELLED");
    if (calendarView === "past") return sorted.filter((v) => +new Date(v.scheduledEnd) < now || v.status === "COMPLETED").reverse();
    return sorted;
  }, [visits, calendarView]);
  const filteredAccountability = useMemo(() => {
    const items = actions?.messageAccountability || [];
    if (actionFilter === "needs_response") return items.filter((x) => ["UNREAD", "READ", "NEEDS_RESPONSE"].includes(x.status));
    if (actionFilter === "awaiting_ack") return items.filter((x) => x.status !== "ACKNOWLEDGED" && x.status !== "RESPONDED" && x.status !== "RESOLVED");
    if (actionFilter === "escalated") return items.filter((x) => x.reminderCount > 0);
    if (actionFilter === "completed") return items.filter((x) => ["RESPONDED", "RESOLVED"].includes(x.status));
    return items;
  }, [actions, actionFilter]);

  const canSchedule = role === "engineer" || isProjectManager || isAdmin;
  const canCreateRequest = role === "owner" || isProjectManager || isAdmin;
  const canReview = (item: OwnerRequest) => isProjectManager || isAdmin || item.assignedToId === user?.id;

  const run = async (key: string, operation: () => Promise<unknown>, message: string) => {
    setBusy(key);
    try { await operation(); toast.success(message); await load(); }
    catch (error: any) { toast.error(errorText(error, t("errors.actionFailed"))); }
    finally { setBusy(""); }
  };

  const createRequest = async () => {
    if (!projectId || !requestForm.title.trim() || !requestForm.description.trim()) return toast.error(t("errors.requiredFields"));
    await run("create-request", async () => {
      await axios.post("/owner-requests", { projectId, ...requestForm, discipline: requestForm.discipline || null });
      setRequestForm({ title: "", description: "", category: "GENERAL_REQUEST", discipline: "", priority: "NORMAL", floor: "", room: "" });
      setRequestOpen(false);
    }, t("ownerRequest.submittedToast"));
  };

  const patchRequest = (item: OwnerRequest, body: Record<string, unknown>, message: string) =>
    run(item.id, () => axios.patch(`/owner-requests/${item.id}`, body), message);

  const convertRequest = (item: OwnerRequest) =>
    run(item.id, () => axios.post(`/owner-requests/${item.id}/convert-to-design-change`, {
      affectedDisciplines: item.discipline ? [item.discipline] : [],
    }), "Design change proposed — the existing human approval workflow still applies.");

  /** Editing the visit invalidates any conflict warning raised for the old times. */
  const editVisit = (patch: Partial<typeof visitForm>) => {
    setVisitForm((current) => ({ ...current, ...patch }));
    setVisitConflicts([]); setVisitError("");
  };

  /** Client-side gate, so obvious mistakes are named instead of round-tripped. */
  const validateVisit = () => {
    if (!projectId) return t("siteVisit.errors.projectRequired");
    if (!visitForm.title.trim()) return t("siteVisit.errors.titleRequired");
    if (!visitForm.start || !visitForm.end) return t("siteVisit.errors.datesRequired");
    if (Number.isNaN(+new Date(visitForm.start)) || Number.isNaN(+new Date(visitForm.end))) return t("siteVisit.errors.datesInvalid");
    if (+new Date(visitForm.end) <= +new Date(visitForm.start)) return t("siteVisit.errors.endBeforeStart");
    return "";
  };

  const createVisit = async (allowConflict = false) => {
    const problem = validateVisit();
    if (problem) { setVisitError(problem); return toast.error(problem); }
    setVisitError("");
    setBusy("create-visit");
    try {
      await axios.post("/site-visits", {
        projectId, title: visitForm.title.trim(),
        scheduledStart: new Date(visitForm.start).toISOString(), scheduledEnd: new Date(visitForm.end).toISOString(),
        visitType: visitForm.visitType, location: visitForm.location.trim() || null,
        engineerId: visitForm.engineerId || null,
        participantIds: visitForm.participantIds, allowConflict,
      });
      setVisitOpen(false); setVisitConflicts([]);
      setVisitForm({ title: "", start: "", end: "", visitType: "ROUTINE_INSPECTION", location: "", engineerId: "", participantIds: [] });
      toast.success(t("siteVisit.scheduledToast")); await load();
    } catch (error: any) {
      // A scheduling clash carries a structured payload the form renders as a
      // list; everything else is flattened to a sentence.
      const detail = error?.response?.data?.detail as { conflicts?: VisitConflict[] } | undefined;
      if (error?.response?.status === 409 && detail?.conflicts) {
        setVisitConflicts(detail.conflicts);
        setVisitError(t("siteVisit.conflictToast"));
        toast.error(t("siteVisit.conflictToast"));
      } else {
        const message = errorText(error, t("errors.visitFailed"));
        // The form stays open and states the reason; the visit was NOT created.
        setVisitError(message);
        toast.error(message);
      }
    } finally { setBusy(""); }
  };

  const clearFocus = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("requestId"); next.delete("visitId");
    setSearchParams(next, { replace: true });
  };

  // The server now describes each clash, including ones in other projects that
  // this page never loaded — previously those rendered as an empty warning.
  const conflictLine = (item: VisitConflict) =>
    `“${item.title}” · ${dateTime(item.scheduledStart)} – ${new Date(item.scheduledEnd).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
    + (item.projectName ? ` · ${item.projectName}` : "");

  return <div className="page-container space-y-6">
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div><p className="text-sm font-semibold text-primary">{t("collaboration.accountableCollaboration")}</p><h1 className="text-3xl font-bold">{t("collaboration.actionCenter")}</h1><p className="mt-1 max-w-3xl text-muted-foreground">{t("collaboration.intro")}</p></div>
      <div className="flex flex-wrap items-end gap-2">
        {!workspace.projectId && <Select label={t("project.project")} value={projectId} onChange={(e) => setProjectId(e.target.value)} options={[{ value: "", label: t("nav.assignedProjects") }, ...projects.map((p) => ({ value: p.id, label: p.name }))]} />}
        <Button variant="outline" onClick={load}><RefreshCw size={16} /> {t("common.refresh")}</Button>
      </div>
    </div>
    <div className="flex flex-wrap gap-2">{(["actions", "requests", "schedule", "activity"] as Tab[]).map((value) => <Button key={value} variant={tab === value ? "primary" : "outline"} onClick={() => { setTab(value); clearFocus(); }}>{t("collaboration.tabs." + value, { defaultValue: humanize(value) })}</Button>)}</div>

    {loading ? <Card className="p-8 text-center text-muted-foreground">{t("common.loading")}</Card> : null}

    {!loading && tab === "actions" && <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {Object.entries(actions?.counts || {}).map(([key, value]) => <Card key={key} className="p-4"><p className="text-xs text-muted-foreground">{t("collaboration.counts." + key, { defaultValue: humanize(key) })}</p><p className="mt-2 text-3xl font-bold">{value}</p></Card>)}
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-5"><div className="flex items-center gap-2"><MessageSquareWarning size={18} /><h2 className="font-semibold">{t("collaboration.needsMyResponse")}</h2></div><div className="mt-4 space-y-3">{actions?.ownerRequests.map((item) => <div key={item.id} className="rounded-lg border p-3"><div className="flex items-start justify-between gap-3"><div><Link to={projectEntityPath(item.projectId, "OWNER_REQUEST", item.id, role, affiliation)} className="font-medium hover:text-primary hover:underline">{item.title}</Link><p className="text-xs text-muted-foreground">{item.discipline ? humanize(item.discipline) : t("ownerRequest.category." + item.category, { defaultValue: humanize(item.category) })} · {t("task.priority." + item.priority.toLowerCase(), { defaultValue: humanize(item.priority) })}</p></div><Badge variant={statusTone(item.status) as any}>{t("ownerRequest.status." + item.status, { defaultValue: humanize(item.status) })}</Badge></div>{item.assignedToId === user?.id && !item.acknowledgedAt && <Button className="mt-3" size="sm" variant="outline" disabled={busy === item.id} onClick={() => patchRequest(item, { status: item.status === "ASSIGNED" ? "UNDER_REVIEW" : undefined }, t("collaboration.acknowledge"))}>{t("collaboration.acknowledgeAction")}</Button>}</div>)}{!actions?.ownerRequests.length && <div className="empty-state"><p className="empty-state-title">{t("empty.noActionsNeeded")}</p><p className="text-sm text-muted-foreground">{t("empty.noActionsNeededHint")}</p></div>}</div></Card>
        <Card className="p-5"><div className="flex items-center gap-2"><CalendarDays size={18} /><h2 className="font-semibold">{t("collaboration.upcomingSiteVisits")}</h2></div><div className="mt-4 space-y-3">{actions?.upcomingSiteVisits.map((visit) => <Link key={visit.id} to={projectEntityPath(visit.projectId, "SITE_VISIT", visit.id, role, affiliation)} className="block rounded-lg border p-3 transition-colors hover:bg-muted/40"><p className="font-medium">{visit.title}</p><p className="text-sm text-muted-foreground">{dateTime(visit.scheduledStart)} · {t("siteVisit.type." + visit.visitType, { defaultValue: humanize(visit.visitType) })}</p></Link>)}{!actions?.upcomingSiteVisits.length && <p className="text-sm text-muted-foreground">{t("empty.noVisitsHint")}</p>}</div></Card>
      </div>
      <Card className="p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div><h2 className="font-semibold">{t("collaboration.communicationAccountability")}</h2><p className="text-sm text-muted-foreground">{t("collaboration.accountabilityHint")}</p></div>
          <Select label={t("common.filter")} value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} options={[
            { value: "", label: t("collaboration.messageFilters.all") }, { value: "needs_response", label: t("collaboration.messageFilters.needs_response") },
            { value: "awaiting_ack", label: t("collaboration.messageFilters.awaiting_ack") }, { value: "escalated", label: t("collaboration.messageFilters.escalated") },
            { value: "completed", label: t("collaboration.messageFilters.completed") },
          ]} />
        </div>
        <div className="mt-4 space-y-2">
          {filteredAccountability.map((item) => <div key={item.messageId} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
            <div className="flex items-center gap-3"><Badge variant={item.status === "RESOLVED" || item.status === "RESPONDED" ? "success" : item.status === "UNREAD" ? "warning" : "info"}>{humanize(item.status)}</Badge>{item.reminderCount > 0 && <span className="text-xs font-medium text-state-review">{t("collaboration.remindersSent", { count: item.reminderCount })}</span>}</div>
            <div className="flex gap-2">
              {!["ACKNOWLEDGED", "RESPONDED", "RESOLVED"].includes(item.status) && <Button size="sm" variant="outline" disabled={busy === item.messageId} onClick={() => run(item.messageId, () => axios.post(`/messages/${item.messageId}/accountability`, { action: "ACKNOWLEDGE" }), "Acknowledged.")}>{t("collaboration.acknowledge")}</Button>}
              {item.status !== "RESOLVED" && <Button size="sm" variant="outline" disabled={busy === item.messageId} onClick={() => run(item.messageId, () => axios.post(`/messages/${item.messageId}/accountability`, { action: "RESOLVED" }), "Marked resolved.")}>{t("collaboration.markResolved")}</Button>}
              {projectId && <Link to={projectModulePath(projectId, "messages", role, affiliation)} className="inline-flex items-center gap-1 text-sm font-medium text-primary"><ExternalLink size={14} /> {t("common.openRecord")}</Link>}
            </div>
          </div>)}
          {!filteredAccountability.length && <p className="text-sm text-muted-foreground">{t("empty.noResults")}</p>}
        </div>
      </Card>
      <Card className="border-primary/20 bg-primary/5 p-5"><div className="flex gap-3"><Sparkles className="text-primary" /><div><h2 className="font-semibold">{t("collaboration.counts.aiAlertsRequiringReview")}: {actions?.counts.aiAlertsRequiringReview || 0}</h2><p className="text-sm text-muted-foreground">{t("ai.reviewRequiredHint")}</p>{projectId && <Link className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-primary" to={projectModulePath(projectId, "ai-intelligence", role, affiliation)}><ExternalLink size={14} /> {t("ai.reviewQueue")}</Link>}</div></div></Card>
    </>}

    {!loading && tab === "requests" && <>
      {focusedRequest && <Card className="border-primary/40 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><p className="text-xs font-semibold uppercase tracking-wider text-primary">{t("ownerRequest.requestDetail")}</p><h2 className="mt-1 text-xl font-semibold">{focusedRequest.title}</h2><p className="mt-1 text-sm text-muted-foreground">{t("ownerRequest.category." + focusedRequest.category, { defaultValue: humanize(focusedRequest.category) })} · {humanize(focusedRequest.discipline || "general")} · {[focusedRequest.floor, focusedRequest.room].filter(Boolean).join(" / ") || t("common.notAvailable")}</p></div>
          <div className="flex gap-2"><Badge variant={statusTone(focusedRequest.status) as any}>{t("ownerRequest.status." + focusedRequest.status, { defaultValue: humanize(focusedRequest.status) })}</Badge><Button size="sm" variant="outline" onClick={clearFocus}>{t("common.close")}</Button></div>
        </div>
        <div className="mt-4 grid gap-5 lg:grid-cols-2">
          <div>
            <p className="text-sm leading-6">{focusedRequest.description}</p>
            <p className="mt-3 text-xs text-muted-foreground">{t("ownerRequest.submittedBy", { name: memberName(focusedRequest.createdById) })} · {t("ownerRequest.assignedTo", { name: memberName(focusedRequest.assignedToId) })}</p>
            {focusedRequest.clarificationText && <div className="mt-3 rounded-lg border border-state-review/30 bg-wash-review/50 p-3 text-sm"><strong>{t("ownerRequest.clarification")}:</strong> {focusedRequest.clarificationText}</div>}
            {focusedRequest.responseText && <div className="mt-3 rounded-lg bg-muted p-3 text-sm"><strong>{t("ownerRequest.engineeringResponse")}:</strong> {focusedRequest.responseText}</div>}
            {focusedRequest.convertedDesignChangeId && <Link className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary" to={projectEntityPath(focusedRequest.projectId, "DESIGN_CHANGE", focusedRequest.convertedDesignChangeId, role, affiliation)}><ExternalLink size={14} /> {t("ownerRequest.openLinkedChange")}</Link>}
          </div>
          <div className="rounded-xl border p-4"><p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("ownerRequest.workflowTimeline")}</p><RequestTimeline request={focusedRequest} /></div>
        </div>
        {canReview(focusedRequest) && <div className="mt-5 space-y-3 rounded-xl border bg-muted/20 p-4">
          <p className="text-sm font-semibold">{t("ownerRequest.reviewActions")}</p>
          <label className="block text-sm font-medium">{t("ownerRequest.responseToClient")}<textarea className="mt-1 min-h-20 w-full rounded-lg border bg-background p-3" value={responseDraft} onChange={(e) => setResponseDraft(e.target.value)} placeholder={t("ownerRequest.responsePlaceholder")} /></label>
          <label className="block text-sm font-medium">{t("ownerRequest.askClarification")}<textarea className="mt-1 min-h-16 w-full rounded-lg border bg-background p-3" value={clarificationDraft} onChange={(e) => setClarificationDraft(e.target.value)} placeholder={t("ownerRequest.clarificationPlaceholder")} /></label>
          <div className="flex flex-wrap gap-2">
            {focusedRequest.status === "ASSIGNED" && <Button size="sm" variant="outline" disabled={busy === focusedRequest.id} onClick={() => patchRequest(focusedRequest, { status: "UNDER_REVIEW" }, "Review started.")}>{t("ownerRequest.startReview")}</Button>}
            <Button size="sm" variant="outline" disabled={!responseDraft.trim() || busy === focusedRequest.id} onClick={() => patchRequest(focusedRequest, { responseText: responseDraft }, "Response recorded.").then(() => setResponseDraft(""))}>{t("ownerRequest.sendResponse")}</Button>
            <Button size="sm" variant="outline" disabled={!clarificationDraft.trim() || busy === focusedRequest.id} onClick={() => patchRequest(focusedRequest, { status: "NEEDS_CLARIFICATION", clarificationText: clarificationDraft }, "Clarification requested.").then(() => setClarificationDraft(""))}>{t("ownerRequest.requestClarification")}</Button>
            <Button size="sm" variant="outline" disabled={busy === focusedRequest.id} onClick={() => patchRequest(focusedRequest, { status: "ACCEPTED" }, "Request accepted.")}>{t("ownerRequest.accept")}</Button>
            <Button size="sm" variant="outline" disabled={busy === focusedRequest.id} onClick={() => patchRequest(focusedRequest, { status: "REJECTED" }, "Request rejected.")}>{t("ownerRequest.reject")}</Button>
            {["UNDER_REVIEW", "ACCEPTED"].includes(focusedRequest.status) && !focusedRequest.convertedDesignChangeId &&
              <Button size="sm" disabled={busy === focusedRequest.id} onClick={() => convertRequest(focusedRequest)}>{t("ownerRequest.proposeDesignChange")}</Button>}
            {focusedRequest.status === "ACCEPTED" && <Button size="sm" variant="outline" disabled={busy === focusedRequest.id} onClick={() => patchRequest(focusedRequest, { status: "COMPLETED" }, "Request completed.")}>{t("ownerRequest.markCompleted")}</Button>}
          </div>
          <p className="text-xs text-muted-foreground">{t("ownerRequest.conversionNote")}</p>
        </div>}
      </Card>}

      <Card className="p-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-semibold">{t("ownerRequest.requests")}</h2><p className="text-sm text-muted-foreground">{t("ownerRequest.neverChangesDesign")}</p></div><div className="flex items-end gap-2"><Select label={t("common.status")} value={requestStatus} onChange={(e) => setRequestStatus(e.target.value)} options={[{ value: "", label: t("common.all") }, ...Array.from(new Set(requests.map((x) => x.status))).map((x) => ({ value: x, label: t("ownerRequest.status." + x, { defaultValue: humanize(x) }) }))]} />{canCreateRequest && <Button onClick={() => setRequestOpen((x) => !x)}><Plus size={16} /> {t("ownerRequest.newRequest")}</Button>}</div></div>
        {requestOpen && <div className="mt-5 grid gap-3 rounded-xl border bg-muted/20 p-4 md:grid-cols-2"><Input label={t("ownerRequest.requestTitle")} value={requestForm.title} onChange={(e) => setRequestForm({ ...requestForm, title: e.target.value })} /><Select label={t("common.category")} value={requestForm.category} onChange={(e) => setRequestForm({ ...requestForm, category: e.target.value })} options={["DESIGN_MODIFICATION", "QUESTION", "MATERIAL_PREFERENCE", "ROOM_CHANGE", "ARCHITECTURAL_REQUEST", "ELECTRICAL_REQUEST", "MECHANICAL_REQUEST", "GENERAL_REQUEST"].map((x) => ({ value: x, label: t("ownerRequest.category." + x, { defaultValue: humanize(x) }) }))} /><Select label={t("common.discipline")} value={requestForm.discipline} onChange={(e) => setRequestForm({ ...requestForm, discipline: e.target.value })} options={[{ value: "", label: t("ownerRequest.routeForMe") }, ...["architectural", "civil", "electrical", "mechanical"].map((x) => ({ value: x, label: humanize(x) }))]} /><Select label={t("common.priority")} value={requestForm.priority} onChange={(e) => setRequestForm({ ...requestForm, priority: e.target.value })} options={["NORMAL", "HIGH", "CRITICAL"].map((x) => ({ value: x, label: t("task.priority." + x.toLowerCase(), { defaultValue: humanize(x) }) }))} /><Input label={t("ownerRequest.floor")} value={requestForm.floor} onChange={(e) => setRequestForm({ ...requestForm, floor: e.target.value })} /><Input label={t("ownerRequest.room")} value={requestForm.room} onChange={(e) => setRequestForm({ ...requestForm, room: e.target.value })} /><label className="md:col-span-2 text-sm font-medium">{t("ownerRequest.whatToAsk")}<textarea className="mt-1 min-h-28 w-full rounded-lg border bg-background p-3" value={requestForm.description} onChange={(e) => setRequestForm({ ...requestForm, description: e.target.value })} /></label><div className="md:col-span-2 flex justify-end"><Button disabled={busy === "create-request"} onClick={createRequest}>{t("ownerRequest.submitForReview")}</Button></div></div>}
        <div className="mt-5 space-y-3">{filteredRequests.map((item) => <div key={item.id} className={`rounded-xl border p-4 ${item.id === focusedRequestId ? "border-primary" : ""}`}><div className="flex flex-wrap items-start justify-between gap-3"><div><Link to={`?requestId=${item.id}`} className="font-semibold hover:text-primary hover:underline">{item.title}</Link><p className="mt-1 text-sm text-muted-foreground">{item.description}</p><p className="mt-2 text-xs text-muted-foreground">{t("ownerRequest.category." + item.category, { defaultValue: humanize(item.category) })} · {humanize(item.discipline || "general")} · {dateTime(item.createdAt)} · {t("ownerRequest.assignedTo", { name: memberName(item.assignedToId) })}</p></div><div className="flex gap-2"><Badge variant={item.priority === "CRITICAL" ? "danger" : item.priority === "HIGH" ? "warning" : "neutral"}>{t("task.priority." + item.priority.toLowerCase(), { defaultValue: humanize(item.priority) })}</Badge><Badge variant={statusTone(item.status) as any}>{t("ownerRequest.status." + item.status, { defaultValue: humanize(item.status) })}</Badge></div></div>{item.responseText && <div className="mt-3 rounded-lg bg-muted p-3 text-sm"><strong>{t("ownerRequest.engineeringResponse")}:</strong> {item.responseText}</div>}</div>)}{!filteredRequests.length && <div className="empty-state"><p className="empty-state-title">{t("empty.noRequests")}</p><p className="text-sm text-muted-foreground">{t("empty.noRequestsHint")}</p></div>}</div>
      </Card>
    </>}

    {!loading && tab === "schedule" && <Card className="p-5">
      <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-semibold">{t("siteVisit.siteVisits")}</h2><p className="text-sm text-muted-foreground">{t("siteVisit.conflictBlockedHint")}</p></div><div className="flex flex-wrap gap-2">{(["upcoming", "past", "all"] as const).map((x) => <Button size="sm" key={x} variant={calendarView === x ? "primary" : "outline"} onClick={() => setCalendarView(x)}>{t("siteVisit.views." + x)}</Button>)}{canSchedule && <Button onClick={() => setVisitOpen((x) => !x)}><Plus size={16} /> {t("siteVisit.scheduleVisit")}</Button>}</div></div>
      {visitOpen && <div className="mt-5 grid gap-3 rounded-xl border bg-muted/20 p-4 md:grid-cols-2">
        {!projectId && <p className="md:col-span-2 rounded-lg border border-state-review/30 bg-wash-review/60 p-3 text-sm text-state-review">{t("siteVisit.errors.projectRequired")}</p>}
        <Input label={`${t("siteVisit.visitTitle")} *`} required value={visitForm.title} onChange={(e) => editVisit({ title: e.target.value })} />
        <Select label={t("siteVisit.visitType")} value={visitForm.visitType} onChange={(e) => editVisit({ visitType: e.target.value })} options={["ROUTINE_INSPECTION", "PROGRESS_REVIEW", "CLIENT_MEETING", "TECHNICAL_INSPECTION", "PROBLEM_INVESTIGATION", "HANDOVER", "OTHER"].map((x) => ({ value: x, label: t("siteVisit.type." + x, { defaultValue: humanize(x) }) }))} />
        <Input type="datetime-local" label={`${t("siteVisit.start")} *`} required value={visitForm.start} onChange={(e) => editVisit({ start: e.target.value })} />
        <Input type="datetime-local" label={`${t("siteVisit.end")} *`} required value={visitForm.end} onChange={(e) => editVisit({ end: e.target.value })} />
        <Input label={t("siteVisit.location")} helperText={t("siteVisit.locationHint")} value={visitForm.location} onChange={(e) => editVisit({ location: e.target.value })} />
        {/* A manager schedules on an engineer's behalf; conflicts are checked
            against that engineer's calendar, so it must be selectable. */}
        {(isProjectManager || isAdmin) && (
          <Select label={t("siteVisit.responsibleEngineer")} value={visitForm.engineerId} onChange={(e) => editVisit({ engineerId: e.target.value })}
            options={[{ value: "", label: t("siteVisit.responsibleEngineerSelf") }, ...selectableMembers.map((m) => { const id = m.user?.id || m.userId; return { value: id, label: memberName(id) }; })]} />
        )}
        <div className="md:col-span-2">
          <p className="text-sm font-medium">{t("siteVisit.participants")}</p>
          <p className="text-xs text-muted-foreground">{t("siteVisit.participantsHint")}</p>
          {selectableMembers.length === 0
            ? <p className="mt-2 text-sm text-muted-foreground">{t("siteVisit.noMembersHint")}</p>
            : <div className="mt-2 grid max-h-48 gap-1 overflow-y-auto rounded-lg border bg-background p-2 sm:grid-cols-2">
              {selectableMembers.map((m) => {
                const id = m.user?.id || m.userId;
                const checked = visitForm.participantIds.includes(id);
                return <label key={id} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted/50">
                  <input type="checkbox" className="h-4 w-4 shrink-0" checked={checked}
                    onChange={(e) => editVisit({ participantIds: e.target.checked ? [...visitForm.participantIds, id] : visitForm.participantIds.filter((x) => x !== id) })} />
                  <span className="truncate">{memberName(id)}</span>
                  {m.roleOnProject && <span className="ml-auto shrink-0 text-xs text-muted-foreground">{humanize(m.roleOnProject)}</span>}
                </label>;
              })}
            </div>}
        </div>
        {visitConflicts.length > 0 && <div className="md:col-span-2 rounded-lg border border-state-review/30 bg-wash-review/60 p-3 text-sm">
          <p className="flex items-center gap-2 font-semibold text-state-review"><AlertTriangle size={16} /> {t("siteVisit.conflictTitle")}</p>
          <ul className="mt-2 list-disc pl-5 text-state-review">{visitConflicts.map((item) => <li key={item.id}>{conflictLine(item)}</li>)}</ul>
          <p className="mt-2 text-state-review">{t("siteVisit.conflictHint")}</p>
        </div>}
        {visitError && !visitConflicts.length && <p role="alert" className="md:col-span-2 rounded-lg border border-state-overdue/30 bg-wash-overdue/60 p-3 text-sm text-state-overdue">{visitError}</p>}
        <div className="md:col-span-2 flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={() => { setVisitOpen(false); setVisitConflicts([]); setVisitError(""); }}>{t("common.cancel")}</Button>
          {visitConflicts.length > 0 && <Button variant="outline" disabled={busy === "create-visit"} onClick={() => createVisit(true)}>{t("siteVisit.scheduleAnyway")}</Button>}
          <Button disabled={busy === "create-visit" || !projectId} onClick={() => createVisit(false)}>
            {busy === "create-visit" ? t("common.saving") : t("siteVisit.scheduleAndNotify")}
          </Button>
        </div>
      </div>}
      <div className="mt-5 grid gap-3 md:grid-cols-2">{visibleVisits.map((visit) => <div key={visit.id} className={`rounded-xl border p-4 ${visit.id === focusedVisitId ? "border-primary" : ""}`}>
        <div className="flex justify-between gap-2">
          <div><p className="font-semibold">{visit.title}</p><p className="mt-1 text-sm text-muted-foreground">{dateTime(visit.scheduledStart)} — {new Date(visit.scheduledEnd).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p><p className="text-xs text-muted-foreground">{t("siteVisit.type." + visit.visitType, { defaultValue: humanize(visit.visitType) })} · {visit.location || t("project.location")}</p></div>
          <Badge variant={statusTone(visit.status) as any}>{t("siteVisit.status." + visit.status, { defaultValue: humanize(visit.status) })}</Badge>
        </div>
        <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground"><Users size={13} /> {memberName(visit.engineerId)}{visit.participantIds.length ? " " + t("siteVisit.participantCount", { count: visit.participantIds.length }) : " · " + t("siteVisit.noParticipants")}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Link className="inline-flex items-center gap-1 text-sm font-medium text-primary" to={`${projectModulePath(visit.projectId, "site-reports", role, affiliation)}?siteVisitId=${visit.id}`}>{t("siteVisit.createOrOpenReport")}</Link>
          {canSchedule && visit.status !== "COMPLETED" && visit.status !== "CANCELLED" &&
            <Button size="sm" variant="outline" disabled={busy === visit.id} onClick={() => run(visit.id, () => axios.patch(`/site-visits/${visit.id}`, { status: "COMPLETED" }), t("siteVisit.completedToast"))}>{t("siteVisit.markCompleted")}</Button>}
        </div>
      </div>)}{!visibleVisits.length && <div className="empty-state md:col-span-2"><p className="empty-state-title">No {calendarView === "past" ? "past" : "scheduled"} site visits</p><p className="text-sm text-muted-foreground">{t("empty.noVisitsHint")}</p></div>}</div>
    </Card>}

    {!loading && tab === "activity" && <Card className="p-5"><h2 className="text-xl font-semibold">{t("collaboration.activityFeed")}</h2><p className="text-sm text-muted-foreground">{t("collaboration.activityHint")}</p><div className="mt-5 space-y-1">{activity.map((item) => <div key={item.id} className="flex gap-4 border-l-2 border-primary/30 py-3 pl-4"><Clock3 size={16} className="mt-1 shrink-0 text-primary" /><div>{projectId && item.entityId
      ? <Link to={projectEntityPath(projectId, item.entityType, item.entityId, role, affiliation)} className="font-medium hover:text-primary hover:underline">{humanize(item.action)}</Link>
      : <p className="font-medium">{humanize(item.action)}</p>}<p className="text-sm text-muted-foreground">{humanize(item.entityType)} · {dateTime(item.occurredAt)}</p></div></div>)}{!projectId && <p className="text-sm text-muted-foreground">{t("empty.selectProject")}</p>}{projectId && !activity.length && <div className="empty-state"><CheckCircle2 className="mx-auto mb-2" /><p className="empty-state-title">{t("empty.noActivity")}</p><p className="text-sm text-muted-foreground">{t("empty.noActivityHint")}</p></div>}</div></Card>}
  </div>;
};
