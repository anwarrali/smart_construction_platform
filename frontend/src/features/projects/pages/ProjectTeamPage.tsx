import { useCallback, useEffect, useMemo, useState } from "react";
import { formatDate } from "../../../utils/dates";
import { useVocabulary } from "../../../utils/vocabulary";
import { useTranslation } from "react-i18next";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Modal, ModalActions } from "../../../components/ui/Modal";
import { Select } from "../../../components/ui/Select";
import api from "../../../services/api";
import type { User } from "../../../types/auth";
import type { ApprovalMode, Project, ProjectMember } from "../../../types/project";
import { useProjectWorkspace } from "../context/ProjectWorkspaceContext";
import { useParams } from "react-router-dom";
import { useRole } from "../../../hooks/useRole";

const DISCIPLINES = ["civil", "architectural", "electrical", "mechanical"];

export const ProjectTeamPage = () => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const workspace = useProjectWorkspace();
  const { projectId: routeProjectId } = useParams<{ projectId?: string }>();
  const { isAdmin } = useRole();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [available, setAvailable] = useState<User[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<ProjectMember | null>(null);
  const [anotherMember, setAnotherMember] = useState<ProjectMember | null>(null);
  const [transferMember, setTransferMember] = useState<ProjectMember | null>(null);
  const [targetProjectId, setTargetProjectId] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [disciplineFilter, setDisciplineFilter] = useState("");
  const [affiliationFilter, setAffiliationFilter] = useState("");
  const [selectedUserId, setSelectedUserId] = useState("");
  const [assignmentTitle, setAssignmentTitle] = useState("");
  const [projectDiscipline, setProjectDiscipline] = useState("");
  const [projectNotes, setProjectNotes] = useState("");
  const [siteEngineer, setSiteEngineer] = useState(false);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("DISCIPLINE_BASED_REVIEW");
  const [centralizedReviewerId, setCentralizedReviewerId] = useState("");
  const [disciplineReviewers, setDisciplineReviewers] = useState<Record<string, string>>({});
  const [approvalBusy, setApprovalBusy] = useState(false);

  useEffect(() => {
    api.projects.list({ limit: 100 }).then((response) => {
      const list = response.data || [];
      setProjects(list);
      setProjectId(routeProjectId || workspace.projectId || list[0]?.id || "");
    }).catch(() => setError("Unable to load assigned projects."));
  }, [routeProjectId, workspace.projectId]);

  const loadTeam = useCallback(async () => {
    if (!projectId) return;
    setBusy(true);
    setError("");
    try {
      const [team, approval] = await Promise.all([
        api.projects.getMembers(projectId),
        api.projects.getApprovalWorkflow(projectId),
      ]);
      setMembers(team.filter((member) => member.isActive));
      setApprovalMode(approval.mode);
      setCentralizedReviewerId(approval.centralizedReviewerId || "");
      setDisciplineReviewers(Object.fromEntries(
        DISCIPLINES.map((discipline) => [
          discipline,
          approval.disciplineReviewers[discipline]?.[0] || "",
        ]),
      ));
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Unable to load project team.");
    } finally { setBusy(false); }
  }, [projectId]);

  useEffect(() => { loadTeam(); }, [loadTeam]);

  useEffect(() => {
    if (!addOpen || !projectId) return;
    const timer = window.setTimeout(() => {
      api.projects.getAvailableTeamMembers(projectId, {
        search: search || undefined,
        role: roleFilter || undefined,
        discipline: disciplineFilter || undefined,
        affiliation: affiliationFilter || undefined,
      }).then((users) => {
        setAvailable(users);
        setSelectedUserId((current) => users.some((user) => user.id === current) ? current : users[0]?.id || "");
      }).catch((err: any) => setError(err?.response?.data?.detail || "Unable to load eligible users."));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [addOpen, affiliationFilter, disciplineFilter, projectId, roleFilter, search]);

  const selectedUser = useMemo(() => available.find((user) => user.id === selectedUserId), [available, selectedUserId]);
  const otherProjects = projects.filter((project) => project.id !== projectId);
  /* Everyone serving as a Consultant on this project is eligible to be its
     reviewer. Requiring the external-consultant affiliation on top of the
     project role also excluded accounts whose global role is Consultant, which
     left the reviewer dropdown empty on projects staffed with those accounts. */
  const consultantMembers = useMemo(
    () => members.filter((member) =>
      member.roleOnProject === "consultant" && member.user?.status === "active"),
    [members],
  );

  const run = async (operation: () => Promise<unknown>, success?: string) => {
    setBusy(true); setError("");
    try { await operation(); await loadTeam(); if (success) setError(success); return true; }
    catch (err: any) { setError(err?.response?.data?.detail || t("projectTeam.update_failed")); return false; }
    finally { setBusy(false); }
  };

  const resetAssignmentForm = () => {
    setAssignmentTitle(""); setProjectDiscipline(""); setProjectNotes(""); setSiteEngineer(false);
  };

  const saveApprovalWorkflow = async () => {
    const mappings = Object.fromEntries(
      Object.entries(disciplineReviewers)
        .filter(([, reviewerId]) => Boolean(reviewerId))
        .map(([discipline, reviewerId]) => [discipline, [reviewerId]]),
    );
    if (approvalMode === "CENTRALIZED_REVIEW" && !centralizedReviewerId) {
      setError("Select a centralized Consultant reviewer.");
      return;
    }
    if (approvalMode === "DISCIPLINE_BASED_REVIEW" && !Object.keys(mappings).length) {
      setError("Assign at least one discipline reviewer.");
      return;
    }
    setApprovalBusy(true);
    setError("");
    try {
      const updated = await api.projects.updateApprovalWorkflow(projectId, {
        mode: approvalMode,
        centralizedReviewerId: approvalMode === "CENTRALIZED_REVIEW" ? centralizedReviewerId : undefined,
        disciplineReviewers: approvalMode === "DISCIPLINE_BASED_REVIEW" ? mappings : {},
      });
      setApprovalMode(updated.mode);
      setError("Approval workflow saved.");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Unable to save approval workflow.");
    } finally {
      setApprovalBusy(false);
    }
  };

  /* The server derives the project role from the account and rejects a mismatch,
     so this must use the same rule: only an *Engineer* marked as an external
     consultant is assigned as a Consultant. A Worker who carries that
     affiliation stays a Worker. */
  const isExternalConsultantEngineer = (user: User) =>
    user.role === "engineer" && user.engineerAffiliation === "external_consultant";
  const canBeSiteEngineer = (user?: User | null) =>
    !!user && user.role === "engineer" && !isExternalConsultantEngineer(user);

  const addMember = async () => {
    if (!selectedUser) return;
    const projectRole = isExternalConsultantEngineer(selectedUser) ? "consultant" : selectedUser.role;
    /* The Site Engineer box is hidden for anyone who cannot hold that
       responsibility, but hiding it left the last value behind: after looking at
       an engineer the flag stayed set, and assigning a consultant next was
       rejected with 400. Send it only when it can apply. */
    const ok = await run(() => api.projects.addMember(projectId, selectedUser.id, projectRole,
      assignmentTitle || undefined, canBeSiteEngineer(selectedUser) && siteEngineer,
      projectDiscipline || selectedUser.engineerProfile?.discipline,
      projectNotes || undefined));
    if (ok) { setAddOpen(false); resetAssignmentForm(); }
  };

  const openEdit = (member: ProjectMember) => {
    setEditing(member);
    setAssignmentTitle(member.assignmentTitle || "");
    setProjectDiscipline(member.projectDiscipline || member.user?.engineerProfile?.discipline || "");
    setProjectNotes(member.projectNotes || "");
    setSiteEngineer(member.isSiteEngineer);
  };

  return <div className="page-container space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h1 className="text-2xl font-bold">Project Team{workspace.project ? ` · ${workspace.project.name}` : ""}</h1>
        <p className="text-muted-foreground">{t("projectTeam.manage_existing_engineers_and")}</p></div>
      <Button onClick={() => { resetAssignmentForm(); setAddOpen(true); }}>{t("projectTeam.add_team_member")}</Button>
    </div>
    <Card className="space-y-4">
      {workspace.projectId ? <p className="text-sm"><span className="text-muted-foreground">{t("projectTeam.active_project")}</span> {workspace.project?.name}</p>
        : <Select label={t("projectTeam.project")} value={projectId} onChange={(event) => setProjectId(event.target.value)} options={projects.map((project) => ({ value: project.id, label: project.name }))} />}
      {error && <p className={`text-sm ${error.includes("added") || error.includes("transferred") || error.includes("preserved") || error.includes("saved") ? "text-green-600" : "text-red-600"}`}>{error}</p>}
    </Card>
    {isAdmin && <Card className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold">{t("projectTeam.approval_workflow")}</h2>
        <p className="text-sm text-muted-foreground">{t("projectTeam.configure_which_project_consultants_may")}</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <button type="button" onClick={() => setApprovalMode("CENTRALIZED_REVIEW")}
          className={`rounded-lg border p-4 text-left transition ${approvalMode === "CENTRALIZED_REVIEW" ? "border-primary bg-primary/5" : "hover:border-primary/50"}`}>
          <span className="font-medium">{t("projectTeam.centralized_review")}</span>
          <span className="mt-1 block text-sm text-muted-foreground">{t("projectTeam.one_authorized_consultant_reviews_all")}</span>
        </button>
        <button type="button" onClick={() => setApprovalMode("DISCIPLINE_BASED_REVIEW")}
          className={`rounded-lg border p-4 text-left transition ${approvalMode === "DISCIPLINE_BASED_REVIEW" ? "border-primary bg-primary/5" : "hover:border-primary/50"}`}>
          <span className="font-medium">{t("projectTeam.discipline_based_review")}</span>
          <span className="mt-1 block text-sm text-muted-foreground">{t("projectTeam.different_consultants_review_their")}</span>
        </button>
      </div>
      {!consultantMembers.length ? <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        {t("projectTeam.add_consultant_before_approval")}
      </p> : approvalMode === "CENTRALIZED_REVIEW" ? (
        <Select label={t("projectTeam.centralized_consultant_reviewer")} value={centralizedReviewerId}
          onChange={(event) => setCentralizedReviewerId(event.target.value)}
          options={[{ value: "", label: t("projectTeam.select_consultant") }, ...consultantMembers.map((member) => ({
            value: member.userId,
            label: `${member.user.fullName} · ${member.user.engineerProfile?.discipline ? vocabulary.discipline(member.user.engineerProfile.discipline) : t("projectTeam.no_specialty")}`,
          }))]} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {DISCIPLINES.map((discipline) => <Select key={discipline} label={t("projectTeam.discipline_reviewer", { discipline: vocabulary.discipline(discipline) })}
            value={disciplineReviewers[discipline] || ""}
            onChange={(event) => setDisciplineReviewers((current) => ({ ...current, [discipline]: event.target.value }))}
            options={[{ value: "", label: t("projectTeam.not_assigned") }, ...consultantMembers.map((member) => ({
              value: member.userId,
              label: `${member.user.fullName} · ${member.user.engineerProfile?.discipline ? vocabulary.discipline(member.user.engineerProfile.discipline) : t("projectTeam.no_specialty")}`,
            }))]} />)}
        </div>
      )}
      <div className="flex justify-end">
        <Button disabled={approvalBusy || !consultantMembers.length} onClick={saveApprovalWorkflow}>
          {approvalBusy ? t("projectTeam.saving") : t("projectTeam.save_approval_workflow")}
        </Button>
      </div>
    </Card>}
    <Card>
      <div className="overflow-x-auto"><table className="w-full min-w-[900px] text-left text-sm"><thead><tr className="border-b text-muted-foreground">
        <th className="p-3">{t("projectTeam.member")}</th><th className="p-3">{t("projectTeam.role_discipline")}</th><th className="p-3">{t("projectTeam.company_affiliation")}</th><th className="p-3">{t("projectTeam.project_responsibility")}</th><th className="p-3">{t("projectTeam.assigned")}</th><th className="p-3">{t("projectTeam.actions")}</th>
      </tr></thead><tbody>{members.map((member) => <tr key={member.id} className="border-b align-top last:border-0">
        <td className="p-3"><p className="font-medium">{member.user?.fullName}</p><p className="text-xs text-muted-foreground">{member.user?.email}</p><Badge size="sm" variant={member.user?.status === "active" ? "success" : "neutral"}>{member.user?.status ? vocabulary.term(member.user.status) : t("projectTeam.unknown_status")}</Badge></td>
        <td className="p-3"><p>{vocabulary.role(member.user?.role)}</p><p className="text-muted-foreground">{member.projectDiscipline || member.user?.engineerProfile?.discipline ? vocabulary.discipline(member.projectDiscipline || member.user?.engineerProfile?.discipline) : "—"}</p></td>
        <td className="p-3"><p>{member.user?.organization || "—"}</p>{member.user?.engineerAffiliation && <Badge size="sm" variant={member.user.engineerAffiliation === "external_consultant" ? "warning" : "neutral"}>{vocabulary.role(member.user.engineerAffiliation)}</Badge>}</td>
        <td className="p-3"><p>{member.assignmentTitle || t("projectTeam.project_participant")}</p>{member.isSiteEngineer && <Badge size="sm" variant="success">{t("projectTeam.site_engineer")}</Badge>}<p className="mt-1 max-w-xs text-xs text-muted-foreground">{member.projectNotes}</p></td>
        <td className="p-3 text-muted-foreground">{formatDate(member.createdAt || "")}</td>
        <td className="p-3">{["engineer", "consultant", "worker"].includes(member.user?.role || "") && <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => openEdit(member)}>{t("projectTeam.edit_project_assignment")}</Button>
          {otherProjects.length > 0 && <Button size="sm" variant="outline" onClick={() => { setAnotherMember(member); setTargetProjectId(otherProjects[0]?.id || ""); }}>{t("projectTeam.add_to_another_project")}</Button>}
          {isAdmin && otherProjects.length > 0 && <Button size="sm" variant="outline" onClick={() => { setTransferMember(member); setTargetProjectId(otherProjects[0]?.id || ""); }}>{t("projectTeam.transfer")}</Button>}
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => { if (window.confirm(t("projectTeam.confirm_remove_member", { name: member.user.fullName }))) run(() => api.projects.removeMember(projectId, member.userId), t("projectTeam.member_removed")); }}>{t("projectTeam.remove_from_project")}</Button>
        </div>}</td>
      </tr>)}{!busy && members.length === 0 && <tr><td className="p-6 text-center text-muted-foreground" colSpan={6}>{t("projectTeam.no_participants_assigned")}</td></tr>}</tbody></table></div>
    </Card>

    <Modal isOpen={addOpen} onClose={() => setAddOpen(false)} title={t("projectTeam.add_team_member")} size="lg"><div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2"><Input label={t("projectTeam.search_database_users")} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("projectTeam.name_or_email")} />
        <Select label={t("projectTeam.global_role")} value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)} options={[{ value: "", label: t("projectTeam.engineer_consultant_or_worker") }, { value: "engineer", label: vocabulary.role("engineer") }, { value: "consultant", label: vocabulary.role("consultant") }, { value: "worker", label: vocabulary.role("worker") }]} />
        <Select label={t("projectTeam.discipline")} value={disciplineFilter} onChange={(event) => setDisciplineFilter(event.target.value)} options={[{ value: "", label: t("projectTeam.all_disciplines") }, ...DISCIPLINES.map((value) => ({ value, label: vocabulary.discipline(value) }))]} />
        <Select label={t("projectTeam.company_affiliation")} value={affiliationFilter} onChange={(event) => setAffiliationFilter(event.target.value)} options={[{ value: "", label: t("projectTeam.all_affiliations") }, { value: "internal_engineer", label: vocabulary.role("internal_engineer") }, { value: "main_contractor", label: vocabulary.role("main_contractor") }, { value: "external_consultant", label: vocabulary.role("external_consultant") }]} /></div>
      <Select label={t("projectTeam.eligible_active_user")} value={selectedUserId} onChange={(event) => setSelectedUserId(event.target.value)} options={available.map((user) => ({ value: user.id, label: `${user.fullName} · ${vocabulary.role(user.role)} · ${user.engineerProfile?.discipline ? vocabulary.discipline(user.engineerProfile.discipline) : t("projectTeam.no_discipline")} · ${user.organization || t("projectTeam.no_organization")}` }))} />
      {selectedUser && <div className="rounded border p-3 text-sm"><p className="font-medium">{selectedUser.fullName}</p><p>{selectedUser.email} · {vocabulary.role(selectedUser.role)} · {selectedUser.engineerProfile?.discipline}</p><p>{selectedUser.organization || t("projectTeam.no_organization")} · {selectedUser.engineerAffiliation ? vocabulary.role(selectedUser.engineerAffiliation) : ""}</p></div>}
      <div className="grid gap-3 sm:grid-cols-2"><Input label={t("projectTeam.project_responsibility_title")} value={assignmentTitle} onChange={(event) => setAssignmentTitle(event.target.value)} placeholder={t("projectTeam.technical_reviewer_project_engineer")} />
        <Select label={t("projectTeam.project_discipline")} value={projectDiscipline} onChange={(event) => setProjectDiscipline(event.target.value)} options={[{ value: "", label: t("projectTeam.use_account_discipline") }, ...DISCIPLINES.map((value) => ({ value, label: vocabulary.discipline(value) }))]} /></div>
      <label className="block text-sm"><span className="font-medium">{t("projectTeam.project_specific_notes")}</span><textarea className="mt-1 w-full rounded-md border bg-background p-2" rows={3} value={projectNotes} onChange={(event) => setProjectNotes(event.target.value)} /></label>
      {canBeSiteEngineer(selectedUser) && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={siteEngineer} onChange={(event) => setSiteEngineer(event.target.checked)} /> {t("projectTeam.assign_as_site_engineer")}</label>}
      {!available.length && <p className="text-sm text-muted-foreground">{t("projectTeam.no_eligible_active_users_match_these")}</p>}
      <ModalActions><Button variant="outline" onClick={() => setAddOpen(false)}>{t("projectTeam.cancel")}</Button><Button disabled={!selectedUserId || busy} onClick={addMember}>{t("projectTeam.add_team_member")}</Button></ModalActions>
    </div></Modal>

    <Modal isOpen={!!editing} onClose={() => setEditing(null)} title={t("projectTeam.edit_project_assignment")} size="lg"><div className="space-y-4">
      <p className="text-sm text-muted-foreground">Only this project membership is changed. Email, global role, account status, and organization remain Administrator-only.</p>
      <Input label={t("projectTeam.project_responsibility_title")} value={assignmentTitle} onChange={(event) => setAssignmentTitle(event.target.value)} />
      <Select label={t("projectTeam.project_discipline")} value={projectDiscipline} onChange={(event) => setProjectDiscipline(event.target.value)} options={DISCIPLINES.map((value) => ({ value, label: value }))} />
      <label className="block text-sm"><span className="font-medium">{t("projectTeam.project_specific_notes")}</span><textarea className="mt-1 w-full rounded-md border bg-background p-2" rows={3} value={projectNotes} onChange={(event) => setProjectNotes(event.target.value)} /></label>
      {editing?.user?.role === "engineer" && editing.user.engineerAffiliation !== "external_consultant" && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={siteEngineer} onChange={(event) => setSiteEngineer(event.target.checked)} /> {t("projectTeam.site_engineer_responsibility")}</label>}
      <ModalActions><Button variant="outline" onClick={() => setEditing(null)}>{t("projectTeam.cancel")}</Button><Button disabled={busy} onClick={async () => { if (!editing) return; const ok = await run(() => api.projects.updateMemberAssignment(projectId, editing.userId, { assignmentTitle, projectDiscipline, projectNotes, isSiteEngineer: editing.user?.role === "engineer" ? siteEngineer : false })); if (ok) setEditing(null); }}>{t("projectTeam.save_project_assignment")}</Button></ModalActions>
    </div></Modal>

    <Modal isOpen={!!anotherMember} onClose={() => setAnotherMember(null)} title={t("projectTeam.add_to_another_project")}><div className="space-y-4">
      <p className="text-sm">{t("projectTeam.this_adds")} <strong>{anotherMember?.user?.fullName}</strong> to another assigned project and keeps the current membership.</p>
      <Select label={t("projectTeam.target_project")} value={targetProjectId} onChange={(event) => setTargetProjectId(event.target.value)} options={otherProjects.map((project) => ({ value: project.id, label: project.name }))} />
      <ModalActions><Button variant="outline" onClick={() => setAnotherMember(null)}>{t("projectTeam.cancel")}</Button><Button disabled={!targetProjectId || busy} onClick={async () => { if (!anotherMember) return; const ok = await run(() => api.projects.addMember(targetProjectId, anotherMember.userId, anotherMember.roleOnProject, anotherMember.assignmentTitle, false, anotherMember.projectDiscipline, anotherMember.projectNotes), "Member added to another project; current membership was kept."); if (ok) setAnotherMember(null); }}>{t("projectTeam.add_to_another_project")}</Button></ModalActions>
    </div></Modal>

    <Modal isOpen={!!transferMember} onClose={() => setTransferMember(null)} title={t("projectTeam.transfer_project_member")}><div className="space-y-4">
      <p className="text-sm">{t("projectTeam.transfer")} <strong>{transferMember?.user?.fullName}</strong> to another project. This removes only the current project membership; the global account is preserved.</p>
      <Select label={t("projectTeam.target_project")} value={targetProjectId} onChange={(event) => setTargetProjectId(event.target.value)} options={otherProjects.map((project) => ({ value: project.id, label: project.name }))} />
      <p className="text-xs text-muted-foreground">Active source-project tasks are safely returned to the unassigned queue. Site Engineer responsibility must be assigned explicitly in the target project.</p>
      <ModalActions><Button variant="outline" onClick={() => setTransferMember(null)}>{t("projectTeam.cancel")}</Button><Button disabled={!targetProjectId || busy} onClick={async () => { if (!transferMember) return; const ok = await run(() => api.projects.transferMember(projectId, transferMember.userId, targetProjectId), "Member transferred; the global account was preserved."); if (ok) setTransferMember(null); }}>{t("projectTeam.transfer_member")}</Button></ModalActions>
    </div></Modal>
  </div>;
};
