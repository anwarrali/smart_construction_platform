import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";

import axios from "../../../services/axios";
import { Button } from "../../../components/ui/Button";
import { Modal } from "../../../components/ui/Modal";
import { errorMessage } from "../../../utils/errorMessage";
import { useRole } from "../../../hooks/useRole";
import organizationService, { type ProjectParty } from "../../admin/services/organization.service";
import type { Document } from "../../../types/document";

type Share = { partyId: string; partyName?: string | null };

/**
 * Which outside parties may read this document — `document.share_external`.
 *
 * External access to documents is deny-by-default on the server; a share is
 * the only thing that opens one to a contractor or the client. Each toggle is
 * a server call whose answer is what the list then shows.
 */
export const DocumentPartySharing = ({ doc }: { doc: Document }) => {
  const { t } = useTranslation();
  const { hasCapability } = useRole();
  const [open, setOpen] = useState(false);
  const [parties, setParties] = useState<ProjectParty[]>([]);
  const [shared, setShared] = useState<Share[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [partyRows, shareRows] = await Promise.all([
        organizationService.parties(doc.projectId),
        axios.get<Share[]>(`/documents/${doc.id}/party-shares`).then((r) => r.data),
      ]);
      setParties(partyRows.filter((party) => party.isActive !== false));
      setShared(shareRows);
    } catch (err) {
      setError(errorMessage(err, t("documentSharing.loadFailed")));
    }
  }, [doc.id, doc.projectId, t]);

  if (!hasCapability("document.share_external")) return null;

  const toggle = async (party: ProjectParty, on: boolean) => {
    setBusy(party.id);
    try {
      if (on) await axios.post(`/documents/${doc.id}/party-shares`, { partyId: party.id });
      else await axios.delete(`/documents/${doc.id}/party-shares/${party.id}`);
      await load();
      toast.success(on ? t("documentSharing.shared", { party: party.displayName }) : t("documentSharing.unshared", { party: party.displayName }));
    } catch (err) {
      toast.error(errorMessage(err, t("documentSharing.failed")));
    } finally { setBusy(""); }
  };

  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => { setOpen(true); void load(); }}>{t("documentSharing.action")}</Button>
      {open && (
        <Modal isOpen onClose={() => setOpen(false)} title={t("documentSharing.title", { name: doc.title })}>
          <p className="text-sm text-muted-foreground">{t("documentSharing.hint")}</p>
          {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
          <div className="mt-3 space-y-1">
            {parties.map((party) => {
              const on = shared.some((share) => share.partyId === party.id);
              return (
                <label key={party.id} className="flex items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted">
                  <input type="checkbox" checked={on} disabled={busy === party.id}
                    onChange={(event) => void toggle(party, event.target.checked)} />
                  <span>{party.displayName}</span>
                  <span className="text-xs text-muted-foreground">{t(`partyKind.${party.kind}`, { defaultValue: party.kind })}</span>
                </label>
              );
            })}
            {!error && !parties.length && <p className="text-sm text-muted-foreground">{t("documentSharing.noParties")}</p>}
          </div>
        </Modal>
      )}
    </>
  );
};

export default DocumentPartySharing;
