import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Layers, Plus, RefreshCw, ShieldCheck, Trash2, Users } from "lucide-react";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { errorMessage } from "../../../utils/errorMessage";
import { accessControlService, type Permission } from "../services/accessControl.service";
import organizationService, {
  type Discipline,
  type Role,
  type RoleScope,
} from "../services/organization.service";

type Tab = "roles" | "disciplines";

const SCOPES: { value: RoleScope; labelKey: string }[] = [
  { value: "BOTH", labelKey: "officeRoles.scopeBoth" },
  { value: "ORG", labelKey: "officeRoles.scopeOrg" },
  { value: "PROJECT", labelKey: "officeRoles.scopeProject" },
];

const slug = (value: string) =>
  value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60);

/**
 * The office configures itself here: its roles, what each may do, and its
 * disciplines.
 *
 * This is the screen that makes "configurable" true rather than aspirational.
 * The legacy Access Control page still shows the seeded roles as a grid; this
 * one lets an office add "Resident Engineer", decide what it may do, and put
 * somebody on it — with no deployment.
 *
 * Two things are shown rather than hidden, because an administrator changing
 * authority should see the consequences before committing:
 *
 *   * how many people hold a role, next to its name;
 *   * which permissions an outside party can never hold, so a role meant for a
 *     contractor cannot be built wrong and then rejected by the server.
 *
 * Nothing here is the authorization boundary. Every control calls an endpoint
 * that checks `org.manage_roles` again, and the resolution refuses office
 * authority to an external participant whatever this page saves.
 */
export const OfficeRolesPage = () => {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("roles");
  const [roles, setRoles] = useState<Role[]>([]);
  const [disciplines, setDisciplines] = useState<Discipline[]>([]);
  const [catalogue, setCatalogue] = useState<Permission[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftScope, setDraftScope] = useState<RoleScope>("BOTH");
  const [draftInternal, setDraftInternal] = useState(true);
  const [disciplineName, setDisciplineName] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [roleRows, disciplineRows, permissionRows] = await Promise.all([
        organizationService.roles(),
        organizationService.disciplines(),
        accessControlService.permissions(),
      ]);
      setRoles(roleRows);
      setDisciplines(disciplineRows);
      setCatalogue(permissionRows);
      setSelectedId((current) => current ?? roleRows[0]?.id ?? null);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => roles.find((role) => role.id === selectedId) ?? null,
    [roles, selectedId],
  );

  const groups = useMemo(() => {
    const byGroup = new Map<string, Permission[]>();
    for (const permission of catalogue) {
      const list = byGroup.get(permission.group) ?? [];
      list.push(permission);
      byGroup.set(permission.group, list);
    }
    return [...byGroup.entries()];
  }, [catalogue]);

  /** Codes the server will refuse on a role meant for people outside the office. */
  const refusedForExternal = useCallback(
    (permission: Permission) => !permission.projectScoped,
    [],
  );

  const togglePermission = async (permission: Permission) => {
    if (!selected) return;
    const held = selected.permissions.includes(permission.code);
    const next = held
      ? selected.permissions.filter((code) => code !== permission.code)
      : [...selected.permissions, permission.code];
    setSaving(true);
    try {
      const updated = await organizationService.setRolePermissions(selected.id, next);
      setRoles((current) => {
        const others = current.filter((role) => role.id !== updated.id && role.code !== updated.code);
        return [...others, updated].sort((a, b) => a.rank - b.rank);
      });
      setSelectedId(updated.id);
      toast.success(
        held ? t("officeRoles.permissionRemoved") : t("officeRoles.permissionAdded"),
      );
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const createRole = async () => {
    const name = draftName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const created = await organizationService.createRole({
        code: slug(name) || `role_${Date.now()}`,
        nameEn: name,
        scope: draftScope,
        isInternalOnly: draftInternal,
        permissions: [],
      });
      setRoles((current) => [...current, created].sort((a, b) => a.rank - b.rank));
      setSelectedId(created.id);
      setDraftName("");
      toast.success(t("officeRoles.roleCreated", { name }));
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setCreating(false);
    }
  };

  const removeRole = async (role: Role) => {
    try {
      await organizationService.deleteRole(role.id);
      setRoles((current) => current.filter((item) => item.id !== role.id));
      setSelectedId((current) => (current === role.id ? null : current));
      toast.success(t("officeRoles.roleDeleted", { name: role.nameEn }));
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  const createDiscipline = async () => {
    const name = disciplineName.trim();
    if (!name) return;
    try {
      const created = await organizationService.createDiscipline({
        code: slug(name) || `discipline_${Date.now()}`,
        nameEn: name,
      });
      setDisciplines((current) => [...current, created].sort((a, b) => a.rank - b.rank));
      setDisciplineName("");
      toast.success(t("officeRoles.disciplineCreated", { name }));
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  const toggleDiscipline = async (discipline: Discipline) => {
    try {
      const updated = await organizationService.updateDiscipline(discipline.id, {
        isActive: !discipline.isActive,
      });
      setDisciplines((current) => {
        const others = current.filter(
          (item) => item.id !== updated.id && item.code !== updated.code,
        );
        return [...others, updated].sort((a, b) => a.rank - b.rank);
      });
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{t("officeRoles.title")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            {t("officeRoles.subtitle")}
          </p>
        </div>
        <Button variant="secondary" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          {t("common.refresh")}
        </Button>
      </header>

      <div className="flex gap-2">
        {(["roles", "disciplines"] as Tab[]).map((value) => (
          <Button
            key={value}
            variant={tab === value ? "primary" : "ghost"}
            onClick={() => setTab(value)}
          >
            {value === "roles" ? <ShieldCheck size={15} /> : <Layers size={15} />}
            {t(`officeRoles.tab_${value}`)}
          </Button>
        ))}
      </div>

      {tab === "roles" ? (
        <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          <Card className="p-4">
            <h2 className="text-sm font-semibold">{t("officeRoles.rolesHeading")}</h2>
            <div className="mt-3 space-y-1">
              {roles.map((role) => (
                <button
                  key={role.id}
                  type="button"
                  onClick={() => setSelectedId(role.id)}
                  className={`flex w-full items-center justify-between gap-2 rounded px-3 py-2 text-start text-sm ${
                    role.id === selectedId ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                  }`}
                >
                  <span className="truncate">
                    {role.nameEn}
                    {!role.isInternalOnly && (
                      <Badge variant="neutral" size="sm" className="ms-2">
                        {t("officeRoles.external")}
                      </Badge>
                    )}
                  </span>
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Users size={12} />
                    {role.memberCount}
                  </span>
                </button>
              ))}
            </div>

            <div className="mt-4 space-y-2 border-t pt-4">
              <Input
                label={t("officeRoles.newRoleName")}
                value={draftName}
                onChange={(event) => setDraftName(event.target.value)}
                placeholder={t("officeRoles.newRolePlaceholder")}
              />
              <Select
                label={t("officeRoles.scope")}
                value={draftScope}
                onChange={(event) => setDraftScope(event.target.value as RoleScope)}
                options={SCOPES.map((item) => ({ value: item.value, label: t(item.labelKey) }))}
              />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draftInternal}
                  onChange={(event) => setDraftInternal(event.target.checked)}
                />
                {t("officeRoles.internalOnly")}
              </label>
              <Button onClick={() => void createRole()} disabled={creating || !draftName.trim()}>
                <Plus size={15} />
                {t("officeRoles.createRole")}
              </Button>
            </div>
          </Card>

          <Card className="p-4">
            {!selected ? (
              <p className="text-sm text-muted-foreground">{t("officeRoles.selectRole")}</p>
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold">{selected.nameEn}</h2>
                    <p className="text-sm text-muted-foreground">
                      {selected.description || t("officeRoles.noDescription")}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t("officeRoles.heldBy", { count: selected.memberCount })}
                    </p>
                  </div>
                  {!selected.undeletable && selected.memberCount === 0 && (
                    <Button variant="ghost" onClick={() => void removeRole(selected)}>
                      <Trash2 size={15} />
                      {t("common.delete")}
                    </Button>
                  )}
                </div>

                {selected.undeletable && (
                  <p className="mt-3 rounded bg-muted p-3 text-xs text-muted-foreground">
                    {t("officeRoles.administratorLocked")}
                  </p>
                )}

                <div className="mt-5 space-y-5">
                  {groups.map(([group, items]) => (
                    <section key={group}>
                      <h3 className="label-caps text-muted-foreground">{group}</h3>
                      <div className="mt-2 space-y-1">
                        {items.map((permission) => {
                          const refused =
                            !selected.isInternalOnly && refusedForExternal(permission);
                          return (
                            <label
                              key={permission.code}
                              className={`flex items-start gap-3 rounded px-2 py-1.5 text-sm ${
                                refused ? "opacity-50" : "hover:bg-muted"
                              }`}
                            >
                              <input
                                type="checkbox"
                                className="mt-1"
                                disabled={saving || refused}
                                checked={selected.permissions.includes(permission.code)}
                                onChange={() => void togglePermission(permission)}
                              />
                              <span>
                                <span className="font-medium">{permission.label}</span>
                                <span className="block text-xs text-muted-foreground">
                                  {refused
                                    ? t("officeRoles.refusedForExternal")
                                    : permission.description}
                                </span>
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              </>
            )}
          </Card>
        </div>
      ) : (
        <Card className="p-4">
          <h2 className="text-sm font-semibold">{t("officeRoles.disciplinesHeading")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("officeRoles.disciplinesHelp")}
          </p>
          <div className="mt-4 flex flex-wrap items-end gap-2">
            <Input
              label={t("officeRoles.newDisciplineName")}
              value={disciplineName}
              onChange={(event) => setDisciplineName(event.target.value)}
              placeholder={t("officeRoles.newDisciplinePlaceholder")}
            />
            <Button
              onClick={() => void createDiscipline()}
              disabled={!disciplineName.trim()}
            >
              <Plus size={15} />
              {t("officeRoles.createDiscipline")}
            </Button>
          </div>
          <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {disciplines.map((discipline) => (
              <div
                key={discipline.id}
                className="flex items-start justify-between gap-2 rounded border p-3"
              >
                <div>
                  <p className="text-sm font-medium">{discipline.nameEn}</p>
                  {discipline.ifcDisciplines.length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t("officeRoles.coversModelClasses", {
                        list: discipline.ifcDisciplines.join(", "),
                      })}
                    </p>
                  )}
                </div>
                <Button variant="ghost" onClick={() => void toggleDiscipline(discipline)}>
                  {discipline.isActive ? t("common.disable") : t("common.enable")}
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};

export default OfficeRolesPage;
