import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Info, Lock, RefreshCw, Search, ShieldCheck, UserCog, Users } from "lucide-react";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import api from "../../../services/api";
import { errorMessage } from "../../../utils/errorMessage";
import {
  accessControlService,
  type ConsultantScope,
  type Permission,
  type RolePermissionState,
  type UserPermissionSummary,
} from "../services/accessControl.service";

type Tab = "roles" | "people" | "consultants";
type Person = { id: string; fullName: string; email: string; role: string; status: string };
type ProjectRow = { id: string; name: string };
type MemberRow = { userId: string; roleOnProject?: string; isActive?: boolean; user?: { id: string; fullName: string; role?: string; status?: string } };

const ROLES = ["admin", "project_manager", "engineer", "consultant", "owner", "worker"] as const;

/**
 * Access control for administrators.
 *
 * The page is deliberately written in the language of the business rather than
 * of the code: an administrator sees "Approve design changes", not
 * `design_change.approve`. Three questions are separated because they are
 * genuinely different decisions:
 *
 *   Roles       — what a kind of person can do everywhere by default.
 *   People      — an exception for one person, optionally on one project.
 *   Consultants — which engineers and disciplines a consultant reviews.
 *
 * Every control here changes server-side state. Nothing on this page is the
 * only thing standing between a user and a protected operation.
 */
export const AccessControlPage = () => {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("roles");
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [matrix, setMatrix] = useState<RolePermissionState[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [search, setSearch] = useState("");

  const [personId, setPersonId] = useState("");
  const [personProjectId, setPersonProjectId] = useState("");
  const [summary, setSummary] = useState<UserPermissionSummary | null>(null);

  const [scopeProjectId, setScopeProjectId] = useState("");
  const [consultants, setConsultants] = useState<ConsultantScope[]>([]);
  const [members, setMembers] = useState<MemberRow[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [catalogue, roleMatrix] = await Promise.all([
        accessControlService.permissions(),
        accessControlService.roleMatrix(),
      ]);
      setPermissions(catalogue);
      setMatrix(roleMatrix);
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

  const visiblePermissions = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return permissions;
    return permissions.filter((item) =>
      item.label.toLowerCase().includes(needle) || item.description.toLowerCase().includes(needle));
  }, [permissions, search]);

  const stateFor = useCallback(
    (role: string, code: string) => matrix.find((item) => item.role === role && item.permissionCode === code),
    [matrix],
  );

  const toggleRole = async (role: string, permission: Permission, next: boolean) => {
    const current = stateFor(role, permission.code);
    // Returning to the default is expressed by clearing the override, which
    // keeps the catalogue as the single source of truth.
    const allowed = next === permission.defaultRoles.includes(role) ? null : next;
    setBusy(`${role}:${permission.code}`);
    try {
      const updated = await accessControlService.setRolePermission(role, permission.code, allowed);
      setMatrix((rows) => rows.map((row) =>
        row.role === role && row.permissionCode === permission.code ? updated : row));
      toast.success(t("accessControl.roleUpdated"));
    } catch (error) {
      toast.error(errorMessage(error, t("accessControl.updateFailed")));
      if (current) setMatrix((rows) => [...rows]);
    } finally { setBusy(""); }
  };

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
      setSummary(await accessControlService.setUserPermission(
        summary.userId, permission.code, next, personProjectId || null));
      toast.success(t("accessControl.personUpdated"));
    } catch (error) {
      toast.error(errorMessage(error, t("accessControl.updateFailed")));
    } finally { setBusy(""); }
  };

  const loadConsultants = useCallback(async (projectId: string) => {
    if (!projectId) { setConsultants([]); setMembers([]); return; }
    try {
      const [scopes, memberRows] = await Promise.all([
        accessControlService.consultants(projectId),
        api.projects.getMembers(projectId) as unknown as Promise<MemberRow[]>,
      ]);
      setConsultants(scopes);
      setMembers(memberRows || []);
    } catch (error) {
      toast.error(errorMessage(error, t("accessControl.loadFailed")));
    }
  }, [t]);

  useEffect(() => { void loadConsultants(scopeProjectId); }, [scopeProjectId, loadConsultants]);

  const reviewableEngineers = useMemo(
    () => members.filter((item) =>
      item.isActive !== false
      && (item.user?.status ?? "active") === "active"
      && item.roleOnProject !== "consultant"
      && item.roleOnProject !== "owner"),
    [members],
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
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">{t("accessControl.rolesTitle")}</h2>
              <p className="text-sm text-muted-foreground">{t("accessControl.rolesHint")}</p>
            </div>
            <Input label={t("common.search")} value={search} onChange={(e) => setSearch(e.target.value)}
              rightElement={<Search size={15} className="text-muted-foreground" />} />
          </div>

          {groups.map((group) => {
            const rows = visiblePermissions.filter((item) => item.group === group);
            if (!rows.length) return null;
            return (
              <section key={group} className="mt-6">
                <h3 className="label-caps text-muted-foreground">{t(`accessControl.groups.${group}`, { defaultValue: group })}</h3>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full min-w-[46rem] border-separate border-spacing-0 text-sm">
                    <thead>
                      <tr>
                        <th className="sticky start-0 bg-card py-2 text-start font-semibold">{t("accessControl.permission")}</th>
                        {ROLES.map((role) => (
                          <th key={role} className="px-2 py-2 text-center text-xs font-semibold text-muted-foreground">
                            {t(`roles.${role}`, { defaultValue: role })}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((permission) => (
                        <tr key={permission.code} className="border-t">
                          <td className="sticky start-0 max-w-sm bg-card py-2.5 pe-3">
                            <p className="font-medium">{t(`permissions.${permission.code}.label`, { defaultValue: permission.label })}</p>
                            <p className="text-xs text-muted-foreground">
                              {t(`permissions.${permission.code}.description`, { defaultValue: permission.description })}
                            </p>
                          </td>
                          {ROLES.map((role) => {
                            const state = stateFor(role, permission.code);
                            const locked = role === "admin" && permission.adminLocked;
                            return (
                              <td key={role} className="px-2 py-2.5 text-center">
                                <label className="inline-flex items-center justify-center" title={locked ? t("accessControl.lockedHint") : undefined}>
                                  <input
                                    type="checkbox"
                                    className="h-4 w-4"
                                    disabled={locked || busy === `${role}:${permission.code}`}
                                    checked={state?.effectiveAllowed ?? permission.defaultRoles.includes(role)}
                                    onChange={(e) => void toggleRole(role, permission, e.target.checked)}
                                  />
                                </label>
                                {state?.overridden && (
                                  <p className="mt-1 text-[10px] font-medium text-state-review">{t("accessControl.changed")}</p>
                                )}
                                {locked && <Lock size={11} className="mx-auto mt-1 text-muted-foreground" />}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            );
          })}
        </Card>
      )}

      {!loading && tab === "people" && (
        <Card className="p-5">
          <div className="flex items-center gap-2"><UserCog size={18} /><h2 className="text-xl font-semibold">{t("accessControl.peopleTitle")}</h2></div>
          <p className="text-sm text-muted-foreground">{t("accessControl.peopleHint")}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Select label={t("accessControl.person")} value={personId} onChange={(e) => setPersonId(e.target.value)}
              options={[{ value: "", label: t("accessControl.selectPerson") },
                ...people.map((item) => ({ value: item.id, label: `${item.fullName} — ${t(`roles.${item.role}`, { defaultValue: item.role })}` }))]} />
            <Select label={t("accessControl.projectScope")} value={personProjectId} onChange={(e) => setPersonProjectId(e.target.value)}
              helperText={t("accessControl.projectScopeHint")}
              options={[{ value: "", label: t("accessControl.everywhere") },
                ...projects.map((item) => ({ value: item.id, label: item.name }))]} />
          </div>

          {!summary && <p className="mt-6 text-sm text-muted-foreground">{t("accessControl.selectPersonHint")}</p>}

          {summary && (
            <div className="mt-6 space-y-4">
              <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/20 p-3 text-sm">
                <Badge variant="info">{t(`roles.${summary.role}`, { defaultValue: summary.role })}</Badge>
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
    </div>
  );
};

export default AccessControlPage;
