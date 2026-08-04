import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, CheckCircle2, Clock3, MessageSquareWarning, Plus, RefreshCw, Sparkles } from "lucide-react";
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
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";

type Tab = "actions" | "requests" | "schedule" | "activity";
type OwnerRequest = { id: string; projectId: string; createdById: string; assignedToId?: string; title: string; description: string; category: string; discipline?: string; priority: string; status: string; room?: string; floor?: string; dueAt?: string; acknowledgedAt?: string; respondedAt?: string; responseText?: string; createdAt: string };
type SiteVisit = { id: string; projectId: string; engineerId: string; title: string; scheduledStart: string; scheduledEnd: string; visitType: string; location?: string; status: string; participantIds: string[] };
type Activity = { id: string; occurredAt: string; action: string; entityType: string; entityId?: string; details: Record<string, unknown> };
type ActionCenter = { generatedAt: string; counts: Record<string, number>; ownerRequests: OwnerRequest[]; messageAccountability: { messageId: string; status: string; reminderCount: number }[]; upcomingSiteVisits: SiteVisit[]; notifications: { id: string; title: string; message: string }[] };

const humanize = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (x) => x.toUpperCase());
const dateTime = (value: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
const statusTone = (status: string) => status === "COMPLETED" || status === "ACCEPTED" ? "success" : status === "REJECTED" || status === "CANCELLED" ? "danger" : status === "NEEDS_CLARIFICATION" ? "warning" : "info";

export const CollaborationPage = ({ initialTab = "actions" }: { initialTab?: Tab }) => {
  const workspace = useProjectWorkspace();
  const { user } = useAuth();
  const { role, isProjectManager, isAdmin } = useRole();
  const [tab, setTab] = useState<Tab>(initialTab);
  const [projects, setProjects] = useState<Project[]>(workspace.assignedProjects);
  const [projectId, setProjectId] = useState(workspace.projectId || "");
  const [requests, setRequests] = useState<OwnerRequest[]>([]);
  const [visits, setVisits] = useState<SiteVisit[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [actions, setActions] = useState<ActionCenter | null>(null);
  const [loading, setLoading] = useState(true);
  const [requestOpen, setRequestOpen] = useState(false);
  const [visitOpen, setVisitOpen] = useState(false);
  const [requestForm, setRequestForm] = useState({ title: "", description: "", category: "GENERAL_REQUEST", discipline: "", priority: "NORMAL", floor: "", room: "" });
  const [visitForm, setVisitForm] = useState({ title: "", start: "", end: "", visitType: "ROUTINE_INSPECTION", location: "" });
  const [requestStatus, setRequestStatus] = useState("");
  const [calendarView, setCalendarView] = useState<"day" | "week" | "month" | "agenda">("agenda");

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
      if (projectId) setActivity((await axios.get<Activity[]>(`/projects/${projectId}/activity`)).data);
      else setActivity([]);
    } catch (error: any) {
      toast.error(error?.response?.data?.detail?.message || error?.response?.data?.detail || "Unable to load collaboration data.");
    } finally { setLoading(false); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const filteredRequests = useMemo(() => requests.filter((item) => !requestStatus || item.status === requestStatus), [requests, requestStatus]);
  const canSchedule = role === "engineer" || isProjectManager || isAdmin;
  const canCreateRequest = role === "owner" || isProjectManager || isAdmin;

  const createRequest = async () => {
    if (!projectId || !requestForm.title.trim() || !requestForm.description.trim()) return toast.error("Project, title, and description are required.");
    try {
      await axios.post("/owner-requests", { projectId, ...requestForm, discipline: requestForm.discipline || null });
      setRequestForm({ title: "", description: "", category: "GENERAL_REQUEST", discipline: "", priority: "NORMAL", floor: "", room: "" });
      setRequestOpen(false); toast.success("Request submitted for engineering review."); await load();
    } catch (error: any) { toast.error(error?.response?.data?.detail || "Request could not be submitted."); }
  };
  const acknowledge = async (item: OwnerRequest) => {
    try { await axios.patch(`/owner-requests/${item.id}`, { status: item.status === "ASSIGNED" ? "UNDER_REVIEW" : undefined }); toast.success("Action acknowledged."); await load(); }
    catch (error: any) { toast.error(error?.response?.data?.detail || "Request could not be acknowledged."); }
  };
  const createVisit = async () => {
    if (!projectId || !visitForm.title || !visitForm.start || !visitForm.end) return toast.error("Project, title, start, and end are required.");
    try {
      await axios.post("/site-visits", { projectId, title: visitForm.title, scheduledStart: new Date(visitForm.start).toISOString(), scheduledEnd: new Date(visitForm.end).toISOString(), visitType: visitForm.visitType, location: visitForm.location || null, participantIds: [] });
      setVisitOpen(false); toast.success("Site visit scheduled."); await load();
    } catch (error: any) { toast.error(error?.response?.data?.detail?.message || error?.response?.data?.detail || "Visit could not be scheduled."); }
  };

  return <div className="page-container space-y-6">
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div><p className="text-sm font-semibold text-primary">Accountable collaboration</p><h1 className="text-3xl font-bold">My Action Center</h1><p className="mt-1 max-w-3xl text-muted-foreground">Requests, responses, visits, and project history stay connected to their project. AI remains advisory; authorized people approve official work.</p></div>
      <div className="flex flex-wrap items-end gap-2">
        {!workspace.projectId && <Select label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)} options={[{ value: "", label: "All assigned projects" }, ...projects.map((p) => ({ value: p.id, label: p.name }))]} />}
        <Button variant="outline" onClick={load}><RefreshCw size={16} /> Refresh</Button>
      </div>
    </div>
    <div className="flex flex-wrap gap-2">{(["actions", "requests", "schedule", "activity"] as Tab[]).map((value) => <Button key={value} variant={tab === value ? "primary" : "outline"} onClick={() => setTab(value)}>{humanize(value)}</Button>)}</div>

    {loading ? <Card className="p-8 text-center text-muted-foreground">Loading accountable project information…</Card> : null}
    {!loading && tab === "actions" && <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {Object.entries(actions?.counts || {}).map(([key, value]) => <Card key={key} className="p-4"><p className="text-xs text-muted-foreground">{humanize(key)}</p><p className="mt-2 text-3xl font-bold">{value}</p></Card>)}
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-5"><div className="flex items-center gap-2"><MessageSquareWarning size={18} /><h2 className="font-semibold">Needs my response</h2></div><div className="mt-4 space-y-3">{actions?.ownerRequests.map((item) => <div key={item.id} className="rounded-lg border p-3"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{item.title}</p><p className="text-xs text-muted-foreground">{humanize(item.discipline || item.category)} · {humanize(item.priority)}</p></div><Badge variant={statusTone(item.status) as any}>{humanize(item.status)}</Badge></div>{item.assignedToId === user?.id && <Button className="mt-3" size="sm" variant="outline" onClick={() => acknowledge(item)}>Acknowledge action</Button>}</div>)}{!actions?.ownerRequests.length && <div className="empty-state"><p className="empty-state-title">No requests need your response</p><p className="text-sm text-muted-foreground">Assigned owner and engineering requests will appear here.</p></div>}</div></Card>
        <Card className="p-5"><div className="flex items-center gap-2"><CalendarDays size={18} /><h2 className="font-semibold">Upcoming site visits</h2></div><div className="mt-4 space-y-3">{actions?.upcomingSiteVisits.map((visit) => <div key={visit.id} className="rounded-lg border p-3"><p className="font-medium">{visit.title}</p><p className="text-sm text-muted-foreground">{dateTime(visit.scheduledStart)} · {humanize(visit.visitType)}</p></div>)}{!actions?.upcomingSiteVisits.length && <p className="text-sm text-muted-foreground">No upcoming site visits across your assigned projects.</p>}</div></Card>
      </div>
      <Card className="border-primary/20 bg-primary/5 p-5"><div className="flex gap-3"><Sparkles className="text-primary" /><div><h2 className="font-semibold">AI alerts requiring review: {actions?.counts.aiAlertsRequiringReview || 0}</h2><p className="text-sm text-muted-foreground">Automated observations are advisory and retain source links. Changed or rejected source information makes dependent insights outdated.</p></div></div></Card>
    </>}

    {!loading && tab === "requests" && <Card className="p-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-semibold">Client / Owner Requests</h2><p className="text-sm text-muted-foreground">A request never changes the official design directly.</p></div><div className="flex items-end gap-2"><Select label="Status" value={requestStatus} onChange={(e) => setRequestStatus(e.target.value)} options={[{ value: "", label: "All statuses" }, ...Array.from(new Set(requests.map((x) => x.status))).map((x) => ({ value: x, label: humanize(x) }))]} />{canCreateRequest && <Button onClick={() => setRequestOpen((x) => !x)}><Plus size={16} /> New request</Button>}</div></div>
      {requestOpen && <div className="mt-5 grid gap-3 rounded-xl border bg-muted/20 p-4 md:grid-cols-2"><Input label="Request title" value={requestForm.title} onChange={(e) => setRequestForm({ ...requestForm, title: e.target.value })} /><Select label="Category" value={requestForm.category} onChange={(e) => setRequestForm({ ...requestForm, category: e.target.value })} options={["DESIGN_MODIFICATION", "QUESTION", "MATERIAL_PREFERENCE", "ROOM_CHANGE", "ARCHITECTURAL_REQUEST", "ELECTRICAL_REQUEST", "MECHANICAL_REQUEST", "GENERAL_REQUEST"].map((x) => ({ value: x, label: humanize(x) }))} /><Select label="Discipline" value={requestForm.discipline} onChange={(e) => setRequestForm({ ...requestForm, discipline: e.target.value })} options={[{ value: "", label: "General / route to PM" }, ...["architectural", "civil", "electrical", "mechanical"].map((x) => ({ value: x, label: humanize(x) }))]} /><Select label="Priority" value={requestForm.priority} onChange={(e) => setRequestForm({ ...requestForm, priority: e.target.value })} options={["NORMAL", "HIGH", "CRITICAL"].map((x) => ({ value: x, label: humanize(x) }))} /><Input label="Floor" value={requestForm.floor} onChange={(e) => setRequestForm({ ...requestForm, floor: e.target.value })} /><Input label="Room" value={requestForm.room} onChange={(e) => setRequestForm({ ...requestForm, room: e.target.value })} /><label className="md:col-span-2 text-sm font-medium">Description<textarea className="mt-1 min-h-28 w-full rounded-lg border bg-background p-3" value={requestForm.description} onChange={(e) => setRequestForm({ ...requestForm, description: e.target.value })} /></label><div className="md:col-span-2 flex justify-end"><Button onClick={createRequest}>Submit for engineering review</Button></div></div>}
      <div className="mt-5 space-y-3">{filteredRequests.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-semibold">{item.title}</p><p className="mt-1 text-sm text-muted-foreground">{item.description}</p><p className="mt-2 text-xs text-muted-foreground">{humanize(item.category)} · {humanize(item.discipline || "general")} · submitted {dateTime(item.createdAt)}</p></div><div className="flex gap-2"><Badge variant={item.priority === "CRITICAL" ? "danger" : item.priority === "HIGH" ? "warning" : "neutral"}>{humanize(item.priority)}</Badge><Badge variant={statusTone(item.status) as any}>{humanize(item.status)}</Badge></div></div>{item.responseText && <div className="mt-3 rounded-lg bg-muted p-3 text-sm"><strong>Engineering response:</strong> {item.responseText}</div>}</div>)}{!filteredRequests.length && <div className="empty-state"><p className="empty-state-title">No active owner requests</p><p className="text-sm text-muted-foreground">New client requests and their engineering responses will appear here.</p></div>}</div>
    </Card>}

    {!loading && tab === "schedule" && <Card className="p-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-semibold">Engineer multi-project calendar</h2><p className="text-sm text-muted-foreground">Conflicting visits are blocked unless the scheduler explicitly accepts the warning.</p></div><div className="flex flex-wrap gap-2">{(["day", "week", "month", "agenda"] as const).map((x) => <Button size="sm" key={x} variant={calendarView === x ? "primary" : "outline"} onClick={() => setCalendarView(x)}>{humanize(x)}</Button>)}{canSchedule && <Button onClick={() => setVisitOpen((x) => !x)}><Plus size={16} /> Schedule visit</Button>}</div></div>
      {visitOpen && <div className="mt-5 grid gap-3 rounded-xl border bg-muted/20 p-4 md:grid-cols-2"><Input label="Visit title" value={visitForm.title} onChange={(e) => setVisitForm({ ...visitForm, title: e.target.value })} /><Select label="Visit type" value={visitForm.visitType} onChange={(e) => setVisitForm({ ...visitForm, visitType: e.target.value })} options={["ROUTINE_INSPECTION", "PROGRESS_REVIEW", "CLIENT_MEETING", "TECHNICAL_INSPECTION", "PROBLEM_INVESTIGATION", "HANDOVER", "OTHER"].map((x) => ({ value: x, label: humanize(x) }))} /><Input type="datetime-local" label="Start" value={visitForm.start} onChange={(e) => setVisitForm({ ...visitForm, start: e.target.value })} /><Input type="datetime-local" label="End" value={visitForm.end} onChange={(e) => setVisitForm({ ...visitForm, end: e.target.value })} /><Input label="Site / location" value={visitForm.location} onChange={(e) => setVisitForm({ ...visitForm, location: e.target.value })} /><div className="flex items-end justify-end"><Button onClick={createVisit}>Schedule and notify participants</Button></div></div>}
      <div className={`mt-5 grid gap-3 ${calendarView === "month" ? "md:grid-cols-3 xl:grid-cols-4" : ""}`}>{visits.map((visit) => <div key={visit.id} className="rounded-xl border p-4"><div className="flex justify-between gap-2"><div><p className="font-semibold">{visit.title}</p><p className="mt-1 text-sm text-muted-foreground">{dateTime(visit.scheduledStart)} — {new Date(visit.scheduledEnd).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p><p className="text-xs text-muted-foreground">{humanize(visit.visitType)} · {visit.location || "Project site"}</p></div><Badge variant={statusTone(visit.status) as any}>{humanize(visit.status)}</Badge></div><a className="mt-3 inline-flex text-sm font-medium text-primary" href={`/site-reports?siteVisitId=${visit.id}`}>Create / open site report →</a></div>)}{!visits.length && <div className="empty-state"><p className="empty-state-title">No site visits scheduled</p><p className="text-sm text-muted-foreground">Scheduled visits across assigned projects will appear here.</p></div>}</div>
    </Card>}

    {!loading && tab === "activity" && <Card className="p-5"><h2 className="text-xl font-semibold">Project Activity Feed</h2><p className="text-sm text-muted-foreground">Chronological events reuse the platform audit trail instead of duplicating history.</p><div className="mt-5 space-y-1">{activity.map((item) => <div key={item.id} className="flex gap-4 border-l-2 border-primary/30 py-3 pl-4"><Clock3 size={16} className="mt-1 shrink-0 text-primary" /><div><p className="font-medium">{humanize(item.action)}</p><p className="text-sm text-muted-foreground">{humanize(item.entityType)} · {dateTime(item.occurredAt)}</p></div></div>)}{!projectId && <p className="text-sm text-muted-foreground">Select a project to view its activity.</p>}{projectId && !activity.length && <div className="empty-state"><CheckCircle2 className="mx-auto mb-2" /><p className="empty-state-title">No recorded project activity yet</p><p className="text-sm text-muted-foreground">Audited requests, visits, tasks, approvals, and communication events will appear here.</p></div>}</div></Card>}
  </div>;
};
