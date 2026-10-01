import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Info, ShieldCheck, UserCog, Users, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Select } from "../../../components/ui/Select";
import api from "../../../services/api";
import { errorMessage } from "../../../utils/errorMessage";
import { useRole } from "../../../hooks/useRole";
import { useVocabulary } from "../../../utils/vocabulary";
import { ROUTES } from "../../../utils/constants";
import { useAuthStore } from "../../../app/store/auth.store";
import { useStepUp } from "../../../hooks/useStepUp";
import {
  accessControlService,
  type ConsultantScope,
  type Permission,
  type UserPermissionSummary,
} from "../services/accessControl.service";

type Tab = "roles" | "people" | "consultants";
type Person = { id: string; fullName: string; email: string; status: string; orgRole?: { nameEn: string; nameAr?: string | null } | null };
type ProjectRow = { id: string; name: string };
type MemberRow = { userId: string; isActive?: boolean; user?: { id: string; fullName: string; status?: string } };

/**
 * Access control for administrators.
 *
 * The page is deliberately written in the language of the business rather than
 * of the code: an administrator sees "Approve design changes", not
 * `design_change.approve`. Three questions are separated because they are
 * genuinely different decisions:
 *
 *   Roles       — what a kind of person can do; edited on the Office roles
 *                 page, where every role the office has — seeded or its own —
 *                 is listed. This tab points there.
 *   People      — an exception for one person, optionally on one project.
 *   Consultants — which engineers and disciplines a consultant reviews.
 *
 * Every control here changes server-side state. Nothing on this page is the
 * only thing standing between a user and a protected operation.
 */
export const AccessControlPage = () => {
  // Sensitive operations may answer with a step-up challenge; `run` shows the
  // shared verification dialog and replays the call once it is satisfied.
  const { run, dialog } = useStepUp();
  const { t } = useTranslation();
  const { refreshPermissions } = useRole();
  const vocabulary = useVocabulary();
  const ownUserId = useAuthStore((state) => state.user?.id);
  const [tab, setTab] = useState<Tab>("roles");
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  const [personId, setPersonId] = useState("");
  const [personProjectId, setPersonProjectId] = useState("");
  const [summary, setSummary] = useState<UserPermissionSummary | null>(null);

  const [scopeProjectId, setScopeProjectId] = useState("");
  const [consultants, setConsultants] = useState<ConsultantScope[]>([]);
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [assigneeIds, setAssigneeIds] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setPermissions(await accessControlService.permissions());
      const [userList, projectList] = await Promise.all([
        api.users.list({ limit: 200 }).catch(() => []),
        api.projects.list({ limit: 100 }).catch(() => []),
      ]);
      // `/users` answers with a bare array while `/projects` wraps its rows in
      // `data`; accept either rather than depending on one of them.
      const rows = <T,>(value: unknown): T[] =>
        Array.isArray(value) ? (value as T[]) : ((value as { data?: T[] })?.data ?? []);
      setPeople(rows<Person>(userList));
      setProjects(rows<ProjectRow>(projectList));
    } catch (error) {
      toast.error(errorMessage(error, t("accessControl.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { void load(); }, [load]);

  const groups = useMemo(() => {
    const seen: string[] = [];
    for (const item of permissions) if (!seen.includes(item.group)) seen.push(item.group);
    return seen;
  }, [permissions]);

  const visiblePermissions = permissions;

  const loadPerson = useCallback(async (userId: string, projectId: string) => {
    if (!userId) { setSummary(null); return; }
    try {
      setSummary(await accessControlService.user(userId, projectId || undefined));
    } catch (error) {
      toast.error(errorMessage(error, t("accessControl.loadFailed")));
    }
  }, [t]);

  useEffect(() => { void loadPerson(personId, personProjectId); }, [personId, personProjectId, loadPerson]);

  const togglePerson = async (permission: Permission, next: boolean | null) => {
    if (!summary) return;
    setBusy(`user:${permission.code}`);
    try {
      setSummary(await run(() => accessControlService.setUserPermission(
        summary.userId, permission.code, next, personProjectId || null)));
      toast.success(t("accessControl.personUpdated"));
      // An administrator can grant or revoke a permission on their own
      // account; their cached permissions must not stay stale.
      if (summary.userId === ownUserId) void refreshPermissions();
    } catch (error) {
      toast.error(errorMessage(error, t("accessControl.updateFailed")));
    } finally { setBusy(""); }
  };

  const loadConsultants = useCallback(async (projectId: string) => {
    if (!projectId) { setConsultants([]); setMembers([]); setAssigneeIds([]); return; }
    try {
      const [scopes, memberRows, assignable] = await Promise.all([
        accessControlService.consultants(projectId),
        api.projects.getMembers(projectId) as unknown as Promise<MemberRow[]>,
        api.projects.getEligibleMembers(projectId, "task_assignee"),
      ]);
      setConsultants(scopes);
      setMembers(memberRows || []);
      setAssigneeIds(assignable);
    } catch (error) {
      toast.error(errorMessage(error, t("accessControl.loadFailed")));
    }
  }, [t]);

  useEffect(() => { void loadConsultants(scopeProjectId); }, [scopeProjectId, loadConsultants]);

  /* Whose work a reviewer can be limited to: the members who can hold tasks
     on this project, by the server's own assignment rule. */
  const reviewableEngineers = useMemo(
    () => members.filter((item) => assigneeIds.includes(item.user?.id || item.userId)),
    [members, assigneeIds],
  );

  const setScope = async (consultant: ConsultantScope, engineerId: string, include: boolean) => {
    const next = include
      ? [...consultant.engineerUserIds, engineerId]
      : consultant.engineerUserIds.filter((id) => id !== engineerId);
    setBusy(`scope:${consultant.consultantUserId}`);
    try {
      const updated = await accessControlService.setConsultantScope(
        consultant.projectId, consultant.consultantUserId, next);
      setConsultants((rows) => rows.map((row) =>
        row.consultantUserId === updated.consultantUserId ? updated : row));
      toast.success(t("accessControl.scopeUpdated"));
    } catch (error) {
      toast.error(errorMessage(error, t("accessControl.updateFailed")));
    } finally { setBusy(""); }
  };

  const personName = (id: string) => people.find((item) => item.id === id)?.fullName || id.slice(0, 8);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold text-primary">{t("accessControl.eyebrow")}</p>
          <h1 className="text-3xl font-bold">{t("accessControl.title")}</h1>
          <p className="mt-1 max-w-3xl text-muted-foreground">{t("accessControl.intro")}</p>
        </div>
        <Button variant="outline" onClick={() => void load()}>
          <RefreshCw size={16} /> {t("common.refresh")}
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        {(["roles", "people", "consultants"] as Tab[]).map((value) => (
          <Button key={value} variant={tab === value ? "primary" : "outline"} onClick={() => setTab(value)}>
            {t(`accessControl.tabs.${value}`)}
          </Button>
        ))}
      </div>

      {loading && <Card className="p-8 text-center text-muted-foreground">{t("common.loading")}</Card>}

      {!loading && tab === "roles" && (
        <Card className="p-5">
          <h2 className="text-xl font-semibold">{t("accessControl.rolesTitle")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("accessControl.rolesMoved")}</p>
          <Link to={ROUTES.ADMIN_OFFICE_ROLES} className="mt-4 inline-block">
            <Button variant="outline">{t("accessControl.openOfficeRoles")}</Button>
          </Link>
        </Card>
      )}

      {!loading && tab === "people" && (
        <Card className="p-5">
          <div className="flex items-center gap-2"><UserCog size={18} /><h2 className="text-xl font-semibold">{t("accessControl.peopleTitle")}</h2></div>
          <p className="text-sm text-muted-foreground">{t("accessControl.peopleHint")}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Select label={t("accessControl.person")} value={personId} onChange={(e) => setPersonId(e.target.value)}
              options={[{ value: "", label: t("accessControl.selectPerson") },
                ...people.map((item) => ({ value: item.id, label: `${item.fullName} — ${vocabulary.orgRole(item.orgRole)}` }))]} />
            <Select label={t("accessControl.projectScope")} value={personProjectId} onChange={(e) => setPersonProjectId(e.target.value)}
              helperText={t("accessControl.projectScopeHint")}
              options={[{ value: "", label: t("accessControl.everywhere") },
                ...projects.map((item) => ({ value: item.id, label: item.name }))]} />
          </div>

          {!summary && <p className="mt-6 text-sm text-muted-foreground">{t("accessControl.selectPersonHint")}</p>}

          {summary && (
            <div className="mt-6 space-y-4">
              <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/20 p-3 text-sm">
                <Badge variant="info">{summary.roleName || "—"}</Badge>
                <span className="text-muted-foreground">{summary.email}</span>
                <span className="ms-auto text-xs text-muted-foreground">
                  {t("accessControl.holdsCount", { count: summary.effectivePermissions.length })}
                </span>
              </div>

              {groups.map((group) => {
                const rows = visiblePermissions.filter((item) => item.group === group);
                if (!rows.length) return null;
                return (
                  <section key={group}>
                    <h3 className="label-caps text-muted-foreground">{t(`accessControl.groups.${group}`, { defaultValue: group })}</h3>
                    <div className="mt-2 grid gap-2">
                      {rows.map((permission) => {
                        const override = summary.overrides.find((item) =>
                          item.permissionCode === permission.code
                          && (item.projectId ?? null) === (personProjectId || null));
                        const held = summary.effectivePermissions.includes(permission.code);
                        const disabled = Boolean(personProjectId) && !permission.projectScoped;
                        return (
                          <div key={permission.code} className="flex flex-wrap items-center gap-3 rounded-lg border p-3">
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium">{t(`permissions.${permission.code}.label`, { defaultValue: permission.label })}</p>
                              <p className="text-xs text-muted-foreground">
                                {disabled
                                  ? t("accessControl.notProjectScoped")
                                  : t(`permissions.${permission.code}.description`, { defaultValue: permission.description })}
                              </p>
                            </div>
                            <Badge variant={held ? "success" : "neutral"}>
                              {held ? t("accessControl.allowed") : t("accessControl.denied")}
                            </Badge>
                            <div className="flex gap-1">
                              <Button size="sm" variant={override?.allowed === true ? "primary" : "outline"}
                                disabled={disabled || busy === `user:${permission.code}`}
                                onClick={() => void togglePerson(permission, true)}>{t("accessControl.grant")}</Button>
                              <Button size="sm" variant={override?.allowed === false ? "primary" : "outline"}
                                disabled={disabled || busy === `user:${permission.code}`}
                                onClick={() => void togglePerson(permission, false)}>{t("accessControl.revoke")}</Button>
                              <Button size="sm" variant="ghost"
                                disabled={disabled || !override || busy === `user:${permission.code}`}
                                onClick={() => void togglePerson(permission, null)}>{t("accessControl.useDefault")}</Button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                );
              })}
            </div>
          )}
        </Card>
      )}

      {!loading && tab === "consultants" && (
        <Card className="p-5">
          <div className="flex items-center gap-2"><ShieldCheck size={18} /><h2 className="text-xl font-semibold">{t("accessControl.consultantsTitle")}</h2></div>
          <p className="text-sm text-muted-foreground">{t("accessControl.consultantsHint")}</p>

          <div className="mt-4 max-w-md">
            <Select label={t("project.project")} value={scopeProjectId} onChange={(e) => setScopeProjectId(e.target.value)}
              options={[{ value: "", label: t("accessControl.selectProject") },
                ...projects.map((item) => ({ value: item.id, label: item.name }))]} />
          </div>

          {scopeProjectId && !consultants.length && (
            <div className="empty-state mt-6">
              <Users className="mx-auto mb-2" />
              <p className="empty-state-title">{t("accessControl.noConsultants")}</p>
              <p className="text-sm text-muted-foreground">{t("accessControl.noConsultantsHint")}</p>
            </div>
          )}

          <div className="mt-5 grid gap-4">
            {consultants.map((consultant) => (
              <div key={consultant.consultantUserId} className="rounded-xl border p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">{consultant.consultantName || personName(consultant.consultantUserId)}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t(`accessControl.approvalMode.${consultant.approvalMode}`, { defaultValue: consultant.approvalMode })}
                      {" · "}
                      {consultant.disciplines.length === 0
                        ? t("accessControl.noDisciplineAssignment")
                        : consultant.disciplines.map((item) =>
                            item ? t(`discipline.${item}`, { defaultValue: item }) : t("accessControl.projectWide")).join(", ")}
                    </p>
                  </div>
                  <Badge variant={consultant.engineerUserIds.length ? "info" : "neutral"}>
                    {consultant.engineerUserIds.length
                      ? t("accessControl.limitedToCount", { count: consultant.engineerUserIds.length })
                      : t("accessControl.allEngineers")}
                  </Badge>
                </div>

                <p className="mt-3 text-xs text-muted-foreground">{t("accessControl.engineerScopeHint")}</p>
                <div className="mt-2 grid gap-1 sm:grid-cols-2">
                  {reviewableEngineers.map((member) => {
                    const id = member.user?.id || member.userId;
                    const checked = consultant.engineerUserIds.includes(id);
                    return (
                      <label key={id} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted/40">
                        <input type="checkbox" className="h-4 w-4 shrink-0" checked={checked}
                          disabled={busy === `scope:${consultant.consultantUserId}`}
                          onChange={(e) => void setScope(consultant, id, e.target.checked)} />
                        <span className="truncate">{member.user?.fullName || personName(id)}</span>
                      </label>
                    );
                  })}
                  {!reviewableEngineers.length && (
                    <p className="text-sm text-muted-foreground">{t("accessControl.noEngineers")}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card className="border-primary/20 bg-primary/5 p-4">
        <div className="flex gap-3">
          <Info className="shrink-0 text-primary" size={18} />
          <p className="text-sm text-muted-foreground">{t("accessControl.enforcementNote")}</p>
        </div>
      </Card>
      {dialog}
    </div>
  );
};

export default AccessControlPage;
