import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Download, Flag } from "lucide-react";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import api from "../../../services/api";
import { errorMessage } from "../../../utils/errorMessage";
import type { IFCVersion } from "../../../types/ifc";

/**
 * The three things a person can do with a processed revision, in the header
 * that already names it.
 *
 * Active and Baseline are separate designations and are deliberately not
 * merged into one control: the active revision is the one the rest of the
 * platform reads — `ifc_knowledge` answers questions from it — while the
 * baseline is the revision comparisons are measured against. A model group
 * holds at most one of each, and the server enforces that by clearing the flag
 * from every sibling revision, which is why `onVersionUpdated` reports which
 * designation moved rather than only handing back the row that changed.
 *
 * Extracted from `IFCWorkspacePage` rather than inlined into it because these
 * are the page's only mutations of a revision, and they are worth being able
 * to exercise without standing up the whole workspace.
 */
export type RevisionDesignation = "active" | "baseline";

export const IFCRevisionActions = ({
  projectId, version, canManageVersions, canDownload, onVersionUpdated,
}: {
  projectId: string;
  version: IFCVersion;
  canManageVersions: boolean;
  canDownload: boolean;
  onVersionUpdated: (updated: IFCVersion, designation: RevisionDesignation) => void;
}) => {
  const { t } = useTranslation();
  /* The action in flight, or "". Keyed rather than boolean so only the pressed
     button spins while every other one is closed: activating and baselining
     the same revision at once would race two writes against the same row. */
  const [busy, setBusy] = useState("");

  const designate = async (designation: RevisionDesignation) => {
    if (busy) return;
    setBusy(designation);
    try {
      const updated = designation === "active"
        ? await api.ifc.activateVersion(projectId, version.id)
        : await api.ifc.baselineVersion(projectId, version.id);
      onVersionUpdated(updated, designation);
      toast.success(t(
        designation === "active"
          ? "ifcWorkspace.revision_is_now_active"
          : "ifcWorkspace.revision_is_now_baseline",
      ));
    } catch (error) {
      console.error(`[IFC Intelligence] set ${designation} failed`, error);
      toast.error(errorMessage(error, t("ifcWorkspace.revision_designation_failed")));
    } finally {
      setBusy("");
    }
  };

  const download = async () => {
    if (busy) return;
    setBusy("download");
    try {
      const { blob, filename } = await api.ifc.downloadVersion(projectId, version.id);
      // The server's own name where the browser exposes the header, and the
      // revision's stored name otherwise — never a name invented here, so the
      // file a person opens is the file that was uploaded.
      const name = filename ? decodeURIComponent(filename) : version.originalFilename;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = name;
      anchor.click();
      URL.revokeObjectURL(url);
      toast.success(t("ifcWorkspace.download_started", { filename: name }));
    } catch (error) {
      console.error("[IFC Intelligence] IFC download failed", error);
      toast.error(errorMessage(error, t("ifcWorkspace.download_failed")));
    } finally {
      setBusy("");
    }
  };

  return <div className="flex flex-wrap items-center gap-2">
    {version.isActive && <Badge variant="success">{t("ifcWorkspace.active_revision")}</Badge>}
    {version.isBaseline && <Badge variant="info">{t("ifcWorkspace.baseline_revision")}</Badge>}
    {canManageVersions && !version.isActive && <Button
      size="sm" variant="outline" disabled={!!busy} isLoading={busy === "active"}
      onClick={() => void designate("active")}
    ><CheckCircle2 size={15}/> {t("ifcWorkspace.set_as_active")}</Button>}
    {canManageVersions && !version.isBaseline && <Button
      size="sm" variant="outline" disabled={!!busy} isLoading={busy === "baseline"}
      onClick={() => void designate("baseline")}
    ><Flag size={15}/> {t("ifcWorkspace.set_as_baseline")}</Button>}
    {canDownload && <Button
      size="sm" variant="outline" disabled={!!busy} isLoading={busy === "download"}
      onClick={() => void download()}
    ><Download size={15}/> {t("ifcWorkspace.download_ifc")}</Button>}
  </div>;
};
