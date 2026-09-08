import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";

import { Button } from "../../../components/ui/Button";
import { Input } from "../../../components/ui/Input";
import { Modal } from "../../../components/ui/Modal";
import { Select } from "../../../components/ui/Select";
import { errorMessage } from "../../../utils/errorMessage";
import { McpTokenSecret } from "./McpTokenSecret";
import { mcpTokensService } from "../services/mcpTokens.service";
import {
  SCOPE_PROPOSE,
  SCOPE_READ,
  type McpScope,
  type McpTokenCreated,
} from "../../../types/mcp";

/**
 * Minting a token, in two steps inside one dialog.
 *
 * The second step is not a separate modal and not a toast, because it carries
 * the only copy of the secret that will ever exist. Keeping it in the dialog
 * the person deliberately opened means closing it is also deliberate — and
 * while it is showing, an accidental click outside cannot take it away.
 *
 * ## What this form does not validate
 *
 * The lifetime is sent as typed. The server caps it, refuses anything longer
 * with a sentence saying what the cap is, and `errorMessage` puts that
 * sentence on screen. Duplicating the number here would give the client a
 * second opinion about a server setting an operator can change — and the
 * client's copy would be the one that went stale.
 */

interface ProjectOption {
  id: string;
  name: string;
}

interface McpTokenCreateDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projects: ProjectOption[];
  /** Called once, after the person dismisses the secret. */
  onCreated: () => void;
}

export const McpTokenCreateDialog = ({
  isOpen,
  onClose,
  projects,
  onCreated,
}: McpTokenCreateDialogProps) => {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [projectId, setProjectId] = useState("");
  const [allowPropose, setAllowPropose] = useState(false);
  const [lifetimeDays, setLifetimeDays] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [created, setCreated] = useState<McpTokenCreated | null>(null);

  // A dialog that reopens holding the previous token's secret would be a way
  // to see a credential without having just created it. Reset on every open.
  useEffect(() => {
    if (!isOpen) return;
    setName("");
    setProjectId(projects.length === 1 ? projects[0].id : "");
    setAllowPropose(false);
    setLifetimeDays("");
    setCreated(null);
  }, [isOpen, projects]);

  const canSubmit = Boolean(name.trim() && projectId) && !isSubmitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setIsSubmitting(true);
    try {
      const scopes: McpScope[] = allowPropose
        ? [SCOPE_READ, SCOPE_PROPOSE]
        : [SCOPE_READ];
      const parsedLifetime = Number.parseInt(lifetimeDays, 10);
      const result = await mcpTokensService.create({
        name: name.trim(),
        projectId,
        scopes,
        ...(Number.isFinite(parsedLifetime) && parsedLifetime > 0
          ? { lifetimeDays: parsedLifetime }
          : {}),
      });
      setCreated(result);
    } catch (error) {
      toast.error(errorMessage(error, t("mcpClients.createFailed")));
    } finally {
      setIsSubmitting(false);
    }
  };

  // The list is refreshed on the way out rather than the moment the token
  // exists, so the row cannot appear behind a dialog the person is still
  // reading the secret from.
  const handleClose = () => {
    if (created) onCreated();
    onClose();
  };

  const projectName = projects.find((item) => item.id === created?.record.projectId)?.name;

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      size={created ? "full" : "md"}
      title={created ? t("mcpClients.createdTitle") : t("mcpClients.createTitle")}
      description={created ? undefined : t("mcpClients.createSubtitle")}
      // While the secret is on screen, a stray click on the overlay would
      // destroy the only copy of it.
      closeOnOverlayClick={!created}
      footer={
        created ? (
          <div className="flex justify-end">
            <Button onClick={handleClose}>{t("mcpClients.doneCopying")}</Button>
          </div>
        ) : (
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleClose} disabled={isSubmitting}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => void handleSubmit()} disabled={!canSubmit} isLoading={isSubmitting}>
              {t("mcpClients.create")}
            </Button>
          </div>
        )
      }
    >
      {created ? (
        <McpTokenSecret created={created} projectName={projectName} />
      ) : (
        <div className="space-y-1">
          <Input
            label={t("mcpClients.nameLabel")}
            value={name}
            maxLength={120}
            onChange={(event) => setName(event.target.value)}
            placeholder={t("mcpClients.namePlaceholder")}
            helperText={t("mcpClients.nameHelp")}
          />

          <Select
            label={t("mcpClients.projectLabel")}
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
            placeholder={t("mcpClients.projectPlaceholder")}
            options={projects.map((project) => ({
              value: project.id,
              label: project.name,
            }))}
            helperText={t("mcpClients.projectHelp")}
          />

          <div className="form-group">
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 shrink-0"
                checked={allowPropose}
                onChange={(event) => setAllowPropose(event.target.checked)}
              />
              <span>
                <span className="font-medium">{t("mcpClients.allowPropose")}</span>
                <span className="block text-xs text-muted-foreground">
                  {t("mcpClients.allowProposeHelp")}
                </span>
              </span>
            </label>
          </div>

          <Input
            label={t("mcpClients.lifetimeLabel")}
            type="number"
            min={1}
            value={lifetimeDays}
            onChange={(event) => setLifetimeDays(event.target.value)}
            placeholder={t("mcpClients.lifetimePlaceholder")}
            helperText={t("mcpClients.lifetimeHelp")}
          />
        </div>
      )}
    </Modal>
  );
};
