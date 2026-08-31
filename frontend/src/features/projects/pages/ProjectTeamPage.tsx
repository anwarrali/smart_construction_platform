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
import organizationService, {
  type Discipline,
  type ProjectParty,
  type Role,
} from "../../admin/services/organization.service";

/**
 * Which memberships this page may adjust.
 *
 * The server refuses to edit, transfer or remove the membership that carries
 * the project's owner or its assigned manager — those are changed in project
 * setup, not here. That is the rule the row actions mirror. It used to be
 * written as `["engineer", "consultant"].includes(member.user.role)`, which
 * asked what the *account* is instead of what the membership is, and so hid
 * the actions from anybody an office puts on a project under a role it created
 * itself.
 */
const isAdjustableMembership = (member: ProjectMember) =>
  !["owner", "project_manager"].includes(member.roleOnProject || "");

export const ProjectTeamPage = () => {
  const { t } = useTranslation();
  const vocabulary = useVocabulary();
  const workspace = useProjectWorkspace();
  const { projectId: routeProjectId } = useParams<{ projectId?: string }>();
  /* Permissions, not a role name. `project.edit` is what the approval-workflow
     endpoint checks; `project.manage_members` is what everything else on this
     page checks. Both default to the same people the retired `isAdmin` gate
     admitted, and an office can now widen either without a release. */
  const { hasCapability, permissionsReady } = useRole();
  const canConfigureApproval = !permissionsReady || hasCapability("project.edit");
  const canManageMembers = !permissionsReady || hasCapability("project.manage_members");
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
  /* The legacy "Engineer or Consultant" select is gone. Splitting the office's
     own directory by the retired enum was the last place this page asked which
     of six fixed roles somebody was; what actually narrows a search here is
     the discipline and the name, and what the assignment *is* — party, project
     role, disciplines, site responsibility — is chosen in the form below. */
  const [disciplineFilter, setDisciplineFilter] = useState("");
  // Kept as a constant rather than a control: the eligible-user query still
  // accepts the retired affiliation filter, and sending nothing means "no
  // affiliation filter". Internal vs external is now a property of the
  // assignment being made, chosen in the form below.
  const affiliationFilter = "";
  const [selectedUserId, setSelectedUserId] = useState("");
  const [assignmentTitle, setAssignmentTitle] = useState("");
  const [projectDiscipline, setProjectDiscipline] = useState("");
  const [projectNotes, setProjectNotes] = useState("");
  const [siteEngineer, setSiteEngineer] = useState(false);
  // The configurable model, loaded from the office rather than hardcoded.
  const [roles, setRoles] = useState<Role[]>([]);
  const [disciplines, setDisciplines] = useState<Discipline[]>([]);
  const [parties, setParties] = useState<ProjectParty[]>([]);
  const [projectRoleId, setProjectRoleId] = useState("");
  const [partyId, setPartyId] = useState("");
  const [disciplineIds, setDisciplineIds] = useState<string[]>([]);
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

  useEffect(() => {
    // Roles and disciplines are office-wide; parties belong to the project.
    Promise.all([organizationService.roles(), organizationService.disciplines()])
      .then(([roleRows, disciplineRows]) => {
        setRoles(roleRows.filter((role) => role.scope !== "ORG" && role.isActive));
        setDisciplines(disciplineRows.filter((item) => item.isActive));
      })
      .catch(() => setError("Unable to load the office's roles and disciplines."));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    organizationService.parties(projectId).then(setParties).catch(() => setParties([]));
  }, [projectId]);

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
        disciplineCodes.map((discipline) => [
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
        discipline: disciplineFilter || undefined,
        affiliation: affiliationFilter || undefined,
      }).then((users) => {
        setAvailable(users);
        setSelectedUserId((current) => users.some((user) => user.id === current) ? current : users[0]?.id || "");
      }).catch((err: any) => setError(err?.response?.data?.detail || "Unable to load eligible users."));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [addOpen, affiliationFilter, disciplineFilter, projectId, search]);

  const selectedUser = useMemo(() => available.find((user) => user.id === selectedUserId), [available, selectedUserId]);
  const otherProjects = projects.filter((project) => project.id !== projectId);
  const disciplineCodes = useMemo(() => disciplines.map((item) => item.code), [disciplines]);
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
    setProjectRoleId(""); setPartyId(""); setDisciplineIds([]);
  };

  const toggleDiscipline = (id: string) =>
    setDisciplineIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);

  /* Roles an office marks `isInternalOnly` cannot be given to somebody taking
     part for an outside party — the server refuses it, so the picker should
     not offer it. */
  const assignableRoles = useMemo(
    () => roles.filter((role) => (partyId ? !role.isInternalOnly : true)),
    [roles, partyId],
  );

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

  /* Site responsibility is a project assignment, not a role: any number of
     people may carry it, of any discipline. The one structural rule is that
     somebody on the project for an outside party does not carry the office's
     site responsibility — which is a property of the *assignment* being made,
     not of the account. */
  const canBeSiteEngineer = () => !partyId;

  const addMember = async () => {
    if (!selectedUser) return;
    /* `roleOnProject` is the retired column and the server derives it when the
       configurable role is supplied; it is still sent for a client that has
       not been updated. The Site Engineer flag is only sent when it can
       apply, so switching from an internal assignment to an external one does
       not carry a stale value into a 400. */
    const ok = await run(() => api.projects.addMember(
      projectId, selectedUser.id, selectedUser.role,
      assignmentTitle || undefined, canBeSiteEngineer() && siteEngineer,
      projectDiscipline || selectedUser.engineerProfile?.discipline,
      projectNotes || undefined,
      {
        projectRoleId: projectRoleId || undefined,
        partyId: partyId || null,
        disciplineIds,
      },
    ));
    if (ok) { setAddOpen(false); resetAssignmentForm(); }
  };

  const openEdit = (member: ProjectMember) => {
    setEditing(member);
    setAssignmentTitle(member.assignmentTitle || "");
    setProjectDiscipline(member.projectDiscipline || member.user?.engineerProfile?.discipline || "");
    setProjectNotes(member.projectNotes || "");
    setSiteEngineer(member.isSiteEngineer);
    setProjectRoleId(member.projectRoleId || "");
    setPartyId(member.partyId || "");
    setDisciplineIds(
      disciplines
        .filter((item) => (member.disciplineCodes || []).includes(item.code))
        .map((item) => item.id),
    );
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
    {canConfigureApproval && <Card className="space-y-5">
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
          {disciplineCodes.map((discipline) => <Select key={discipline} label={t("projectTeam.discipline_reviewer", { discipline: vocabulary.discipline(discipline) })}
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
        <td className="p-3"><p>{member.projectRoleName || vocabulary.role(member.user?.role)}</p><p className="text-muted-foreground">{(member.disciplineCodes || []).length ? (member.disciplineCodes || []).map((code) => vocabulary.discipline(code)).join(", ") : (member.projectDiscipline ? vocabulary.discipline(member.projectDiscipline) : "—")}</p></td>
        <td className="p-3"><p>{member.user?.organization || "—"}</p><Badge size="sm" variant={member.isExternal ? "warning" : "neutral"}>{member.isExternal ? (member.partyName ? t("projectTeam.external_party", { party: member.partyName }) : t("projectTeam.external_unassigned")) : t("projectTeam.internal")}</Badge></td>
        <td className="p-3"><p>{member.assignmentTitle || t("projectTeam.project_participant")}</p>{member.isSiteEngineer && <Badge size="sm" variant="success">{t("projectTeam.site_engineer")}</Badge>}<p className="mt-1 max-w-xs text-xs text-muted-foreground">{member.projectNotes}</p></td>
        <td className="p-3 text-muted-foreground">{formatDate(member.createdAt || "")}</td>
        <td className="p-3">{canManageMembers && isAdjustableMembership(member) && <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => openEdit(member)}>{t("projectTeam.edit_project_assignment")}</Button>
          {otherProjects.length > 0 && <Button size="sm" variant="outline" onClick={() => { setAnotherMember(member); setTargetProjectId(otherProjects[0]?.id || ""); }}>{t("projectTeam.add_to_another_project")}</Button>}
          {canConfigureApproval && otherProjects.length > 0 && <Button size="sm" variant="outline" onClick={() => { setTransferMember(member); setTargetProjectId(otherProjects[0]?.id || ""); }}>{t("projectTeam.transfer")}</Button>}
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => { if (window.confirm(t("projectTeam.confirm_remove_member", { name: member.user.fullName }))) run(() => api.projects.removeMember(projectId, member.userId), t("projectTeam.member_removed")); }}>{t("projectTeam.remove_from_project")}</Button>
        </div>}</td>
      </tr>)}{!busy && members.length === 0 && <tr><td className="p-6 text-center text-muted-foreground" colSpan={6}>{t("projectTeam.no_participants_assigned")}</td></tr>}</tbody></table></div>
    </Card>

    <Modal isOpen={addOpen} onClose={() => setAddOpen(false)} title={t("projectTeam.add_team_member")} size="lg"><div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2"><Input label={t("projectTeam.search_database_users")} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("projectTeam.name_or_email")} />
        <Select label={t("projectTeam.discipline")} value={disciplineFilter} onChange={(event) => setDisciplineFilter(event.target.value)} options={[{ value: "", label: t("projectTeam.all_disciplines") }, ...disciplines.map((item) => ({ value: item.code, label: item.nameEn }))]} /></div>
      <Select label={t("projectTeam.eligible_active_user")} value={selectedUserId} onChange={(event) => setSelectedUserId(event.target.value)} options={available.map((user) => ({ value: user.id, label: `${user.fullName} · ${vocabulary.role(user.role)} · ${user.engineerProfile?.discipline ? vocabulary.discipline(user.engineerProfile.discipline) : t("projectTeam.no_discipline")} · ${user.organization || t("projectTeam.no_organization")}` }))} />
      {selectedUser && <div className="rounded border p-3 text-sm"><p className="font-medium">{selectedUser.fullName}</p><p>{selectedUser.email} · {vocabulary.role(selectedUser.role)} · {selectedUser.engineerProfile?.discipline}</p><p>{selectedUser.organization || t("projectTeam.no_organization")} · {selectedUser.engineerAffiliation ? vocabulary.role(selectedUser.engineerAffiliation) : ""}</p></div>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label={t("projectTeam.participation")} value={partyId} onChange={(event) => { setPartyId(event.target.value); if (event.target.value) { setSiteEngineer(false); setProjectRoleId(""); } }}
          options={[{ value: "", label: t("projectTeam.internal") }, ...parties.map((party) => ({ value: party.id, label: `${party.displayName} · ${t(`projectParties.kind_${party.kind}`)}` }))]} />
        <Select label={t("projectTeam.project_role")} value={projectRoleId} onChange={(event) => setProjectRoleId(event.target.value)}
          options={[{ value: "", label: t("projectTeam.use_office_role") }, ...assignableRoles.map((role) => ({ value: role.id, label: role.nameEn }))]} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2"><Input label={t("projectTeam.project_responsibility_title")} value={assignmentTitle} onChange={(event) => setAssignmentTitle(event.target.value)} placeholder={t("projectTeam.technical_reviewer_project_engineer")} /></div>
      <fieldset className="rounded border p-3">
        <legend className="px-1 text-sm font-medium">{t("projectTeam.disciplines")}</legend>
        <p className="mb-2 text-xs text-muted-foreground">{t("projectTeam.disciplines_help")}</p>
        <div className="flex flex-wrap gap-2">
          {disciplines.map((item) => (
            <label key={item.id} className="flex items-center gap-1.5 rounded border px-2 py-1 text-sm">
              <input type="checkbox" checked={disciplineIds.includes(item.id)} onChange={() => toggleDiscipline(item.id)} />
              {item.nameEn}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="block text-sm"><span className="font-medium">{t("projectTeam.project_specific_notes")}</span><textarea className="mt-1 w-full rounded-md border bg-background p-2" rows={3} value={projectNotes} onChange={(event) => setProjectNotes(event.target.value)} /></label>
      {canBeSiteEngineer() && <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={siteEngineer} onChange={(event) => setSiteEngineer(event.target.checked)} /><span>{t("projectTeam.site_responsibility")}<span className="block text-xs text-muted-foreground">{t("projectTeam.site_responsibility_help")}</span></span></label>}
      {!available.length && <p className="text-sm text-muted-foreground">{t("projectTeam.no_eligible_active_users_match_these")}</p>}
      <ModalActions><Button variant="outline" onClick={() => setAddOpen(false)}>{t("projectTeam.cancel")}</Button><Button disabled={!selectedUserId || busy} onClick={addMember}>{t("projectTeam.add_team_member")}</Button></ModalActions>
    </div></Modal>

    <Modal isOpen={!!editing} onClose={() => setEditing(null)} title={t("projectTeam.edit_project_assignment")} size="lg"><div className="space-y-4">
      <p className="text-sm text-muted-foreground">Only this project membership is changed. Email, global role, account status, and organization remain Administrator-only.</p>
      <Input label={t("projectTeam.project_responsibility_title")} value={assignmentTitle} onChange={(event) => setAssignmentTitle(event.target.value)} />
      <Select label={t("projectTeam.project_role")} value={projectRoleId} onChange={(event) => setProjectRoleId(event.target.value)}
        options={[{ value: "", label: t("projectTeam.use_office_role") }, ...assignableRoles.map((role) => ({ value: role.id, label: role.nameEn }))]} />
      <fieldset className="rounded border p-3">
        <legend className="px-1 text-sm font-medium">{t("projectTeam.disciplines")}</legend>
        <div className="flex flex-wrap gap-2">
          {disciplines.map((item) => (
            <label key={item.id} className="flex items-center gap-1.5 rounded border px-2 py-1 text-sm">
              <input type="checkbox" checked={disciplineIds.includes(item.id)} onChange={() => toggleDiscipline(item.id)} />
              {item.nameEn}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="block text-sm"><span className="font-medium">{t("projectTeam.project_specific_notes")}</span><textarea className="mt-1 w-full rounded-md border bg-background p-2" rows={3} value={projectNotes} onChange={(event) => setProjectNotes(event.target.value)} /></label>
      {editing && !editing.isExternal && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={siteEngineer} onChange={(event) => setSiteEngineer(event.target.checked)} /> {t("projectTeam.site_engineer_responsibility")}</label>}
      <ModalActions><Button variant="outline" onClick={() => setEditing(null)}>{t("projectTeam.cancel")}</Button><Button disabled={busy} onClick={async () => { if (!editing) return; const ok = await run(() => api.projects.updateMemberAssignment(projectId, editing.userId, { assignmentTitle, projectDiscipline, projectNotes, projectRoleId: projectRoleId || undefined, disciplineIds, isSiteEngineer: editing.isExternal ? false : siteEngineer })); if (ok) setEditing(null); }}>{t("projectTeam.save_project_assignment")}</Button></ModalActions>
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
