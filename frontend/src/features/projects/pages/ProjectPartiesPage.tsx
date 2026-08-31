import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Building2, Plus, RefreshCw, Trash2 } from "lucide-react";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Select } from "../../../components/ui/Select";
import { errorMessage } from "../../../utils/errorMessage";
import { useRole } from "../../../hooks/useRole";
import organizationService, {
  type PartyKind,
  type ProjectParty,
} from "../../admin/services/organization.service";

const KIND_ORDER: PartyKind[] = [
  "CLIENT",
  "MAIN_CONTRACTOR",
  "SUBCONTRACTOR",
  "CONSULTANT",
  "SUPPLIER",
  "AUTHORITY",
  "OTHER",
];

/**
 * The external parties on one project: the client, the contractors, anybody
 * else the office deals with on this job.
 *
 * A party belongs to a *project*, not to the office. A contractor works with
 * many consulting offices and an office with many contractors, so there is no
 * standing firm-to-firm relationship to show here — the project is where they
 * meet, and this page is that record.
 *
 * A subcontractor names the contractor it works under, which is the whole of
 * the contractor/subcontractor distinction; the platform does not model them
 * as different kinds of thing.
 */
export const ProjectPartiesPage = () => {
  const { t } = useTranslation();
  const { projectId = "" } = useParams();
  const { hasCapability, permissionsReady } = useRole();
  const canManage = !permissionsReady || hasCapability("project.manage_parties");

  const [parties, setParties] = useState<ProjectParty[]>([]);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState<PartyKind>("MAIN_CONTRACTOR");
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const [contact, setContact] = useState("");

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      setParties(await organizationService.parties(projectId));
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const contractors = useMemo(
    () => parties.filter((party) => party.kind === "MAIN_CONTRACTOR"),
    [parties],
  );

  const grouped = useMemo(() => {
    const byKind = new Map<PartyKind, ProjectParty[]>();
    for (const party of parties) {
      const list = byKind.get(party.kind) ?? [];
      list.push(party);
      byKind.set(party.kind, list);
    }
    return KIND_ORDER.filter((value) => byKind.has(value)).map(
      (value) => [value, byKind.get(value) ?? []] as const,
    );
  }, [parties]);

  const add = async () => {
    const displayName = name.trim();
    if (!displayName) return;
    try {
      const created = await organizationService.createParty(projectId, {
        kind,
        displayName,
        parentPartyId: kind === "SUBCONTRACTOR" && parentId ? parentId : null,
        contactName: contact.trim() || undefined,
        isPrimary: kind === "MAIN_CONTRACTOR" && contractors.length === 0,
      });
      setParties((current) => [...current, created]);
      setName("");
      setContact("");
      toast.success(t("projectParties.added", { name: displayName }));
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  const remove = async (party: ProjectParty) => {
    try {
      await organizationService.deleteParty(projectId, party.id);
      setParties((current) => current.filter((item) => item.id !== party.id));
      toast.success(t("projectParties.removed", { name: party.displayName }));
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  const parentName = (party: ProjectParty) =>
    parties.find((item) => item.id === party.parentPartyId)?.displayName ?? "";

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{t("projectParties.title")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            {t("projectParties.subtitle")}
          </p>
        </div>
        <Button variant="secondary" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          {t("common.refresh")}
        </Button>
      </header>

      {canManage && (
        <Card className="p-4">
          <h2 className="text-sm font-semibold">{t("projectParties.addHeading")}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Select
              label={t("projectParties.kind")}
              value={kind}
              onChange={(event) => setKind(event.target.value as PartyKind)}
              options={KIND_ORDER.map((value) => ({
                value,
                label: t(`projectParties.kind_${value}`),
              }))}
            />
            <Input
              label={t("projectParties.name")}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t("projectParties.namePlaceholder")}
            />
            {kind === "SUBCONTRACTOR" && (
              <Select
                label={t("projectParties.worksUnder")}
                value={parentId}
                onChange={(event) => setParentId(event.target.value)}
                options={[
                  { value: "", label: t("projectParties.worksUnderNone") },
                  ...contractors.map((party) => ({
                    value: party.id,
                    label: party.displayName,
                  })),
                ]}
              />
            )}
            <Input
              label={t("projectParties.contact")}
              value={contact}
              onChange={(event) => setContact(event.target.value)}
            />
          </div>
          <Button className="mt-3" onClick={() => void add()} disabled={!name.trim()}>
            <Plus size={15} />
            {t("projectParties.add")}
          </Button>
        </Card>
      )}

      {grouped.length === 0 && !loading ? (
        <Card className="p-8 text-center text-sm text-muted-foreground">
          {t("projectParties.empty")}
        </Card>
      ) : (
        grouped.map(([value, list]) => (
          <Card key={value} className="p-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Building2 size={15} />
              {t(`projectParties.kind_${value}`)}
            </h2>
            <div className="mt-3 space-y-2">
              {list.map((party) => (
                <div
                  key={party.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded border p-3"
                >
                  <div>
                    <p className="text-sm font-medium">
                      {party.displayName}
                      {party.isPrimary && (
                        <Badge variant="neutral" size="sm" className="ms-2">
                          {t("projectParties.primary")}
                        </Badge>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {party.parentPartyId
                        ? t("projectParties.worksUnderName", { name: parentName(party) })
                        : t("projectParties.peopleOnProject", { count: party.memberCount })}
                    </p>
                  </div>
                  {canManage && party.memberCount === 0 && (
                    <Button variant="ghost" onClick={() => void remove(party)}>
                      <Trash2 size={15} />
                      {t("common.remove")}
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </Card>
        ))
      )}

      <p className="text-xs text-muted-foreground">{t("projectParties.accessNote")}</p>
    </div>
  );
};

export default ProjectPartiesPage;
