import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { AlertTriangle } from "lucide-react";

import { CopyableBlock } from "./CopyableBlock";
import { mcpClientConfig } from "../services/mcpTokens.service";
import type { McpTokenCreated } from "../../../types/mcp";

/**
 * The one screen in this application that shows a credential.
 *
 * It exists because the server keeps only a SHA-256 of the token: this is not
 * "the last convenient moment" to copy it, it is the only moment it exists
 * anywhere outside the client that will hold it.
 *
 * Two decisions follow from that:
 *
 * **The whole configuration block is offered, not just the secret.** The
 * documented next step is pasting a token into a `mcpServers` entry by hand,
 * where the URL is as easy to get wrong as the secret and much harder to
 * diagnose — a wrong project id is a 403 with no explanation on the client's
 * side. Assembling it here removes both mistakes at once.
 *
 * **The warning is translated, not echoed.** The response carries the server's
 * own `warning` sentence and this deliberately does not render it: it is
 * English-only, and an Arabic reader being told in English that they will
 * never see their token again is the worst possible moment for the interface
 * to change language. The server's sentence stays in the payload for API
 * consumers; what it says — shown once, only a hash kept — is a property of
 * the design this whole feature is built on, not a message that can drift.
 * A *failure* is different, and is still surfaced in the server's own words.
 */

interface McpTokenSecretProps {
  created: McpTokenCreated;
  /** Resolved for display; the config itself is keyed by project id. */
  projectName?: string;
}

export const McpTokenSecret = ({ created, projectName }: McpTokenSecretProps) => {
  const { t } = useTranslation();
  const onCopyError = () => toast.error(t("mcpClients.copyFailed"));

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200">
        <AlertTriangle size={18} className="mt-0.5 shrink-0" />
        <p>{t("mcpClients.secretWarning")}</p>
      </div>

      <CopyableBlock
        label={t("mcpClients.secretLabel")}
        value={created.token}
        onError={onCopyError}
      />

      <CopyableBlock
        label={t("mcpClients.configLabel", {
          project: projectName || created.record.projectId,
        })}
        value={mcpClientConfig(created.record.projectId, created.token)}
        multiline
        onError={onCopyError}
      />

      <p className="text-xs text-muted-foreground">
        {t("mcpClients.configHint")}
      </p>
    </div>
  );
};
