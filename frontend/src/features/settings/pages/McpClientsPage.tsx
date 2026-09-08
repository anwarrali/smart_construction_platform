import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { Plug, Plus, ShieldOff, Trash2 } from "lucide-react";

import api from "../../../services/api";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Modal } from "../../../components/ui/Modal";
import { Table } from "../../../components/ui/Table";
import type { Column } from "../../../components/ui/Table/Table";
import { errorMessage } from "../../../utils/errorMessage";
import { formatDate, timeAgo } from "../../../utils/date";
import { useRole } from "../../../hooks/useRole";
import { McpTokenCreateDialog } from "../components/McpTokenCreateDialog";
import { mcpTokensService } from "../services/mcpTokens.service";
import { SCOPE_PROPOSE, type McpToken } from "../../../types/mcp";

/**
 * Connected AI clients — the screen for the credentials an MCP client holds.
 *
 * Until now these could only be minted with an HTTP client, which made a
 * feature built for engineers usable only by whoever was comfortable with
 * curl. Everything here is the same three REST calls; what it adds is that a
 * person can see what is connected, and take one back.
 *
 * ## Three things this page is careful about
 *
 * **Revoking is the important verb, not creating.** It is offered on every
 * live row, it asks once, and the confirmation names the client and its
 * project rather than saying "are you sure" — the whole point of the
 * credential design is that taking one back is cheap and immediate, and a UI
 * that buries it wastes that.
 *
 * **A disabled surface is explained, not failed.** With `MCP_ENABLED=false`
 * the API answers 503, which would otherwise land as a red toast reading like
 * a bug. The server's own sentence is shown instead, the same way the document
 * assistant surfaces "not enabled on this server".
 *
 * **Nothing here can show a secret.** The list endpoint has no such field.
 * The one moment a token is visible is inside the create dialog, which is why
 * that is the only component in this feature that ever holds one.
 */

const REVOKED = "revoked";
const EXPIRED = "expired";
const ACTIVE = "active";

const statusOf = (token: McpToken): typeof REVOKED | typeof EXPIRED | typeof ACTIVE => {
  if (token.revokedAt) return REVOKED;
  if (!token.active) return EXPIRED;
  return ACTIVE;
};

export const McpClientsPage = () => {
  const { t, i18n } = useTranslation();
  const { isAdmin } = useRole();
  const locale = i18n.language?.startsWith("ar") ? "ar" : "en";

  const [tokens, setTokens] = useState<McpToken[] | null>(null);
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  const [includeRevoked, setIncludeRevoked] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [pendingRevoke, setPendingRevoke] = useState<McpToken | null>(null);
  const [isRevoking, setIsRevoking] = useState(false);
  /**
   * The server's words when the surface is switched off. A string rather than
   * a boolean so the sentence shown is the one the server actually sent — if
   * the platform changes what it says, so does this page.
   */
  const [unavailable, setUnavailable] = useState<string | null>(null);

  const loadTokens = useCallback(async () => {
    try {
      const rows = await mcpTokensService.list(includeRevoked);
      setTokens(rows);
      setUnavailable(null);
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 503) {
        // Not a failure: this deployment has not turned the surface on.
        setUnavailable(errorMessage(error, t("mcpClients.disabled")));
        setTokens([]);
        return;
      }
      toast.error(errorMessage(error, t("mcpClients.loadFailed")));
      setTokens([]);
    }
  }, [includeRevoked, t]);

  useEffect(() => {
    void loadTokens();
  }, [loadTokens]);

  useEffect(() => {
    let cancelled = false;
    // Only for turning ids into names, and for the create dialog's picker.
    // A failure degrades the display to raw ids rather than breaking the page,
    // so it deliberately raises nothing.
    api.projects
      .list({ limit: 200 })
      .then((page) => {
        if (cancelled) return;
        const items = page.items || page.data || [];
        setProjects(items.map((item) => ({ id: item.id, name: item.name })));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const projectName = useCallback(
    (id: string) => projects.find((item) => item.id === id)?.name || id.slice(0, 8),
    [projects],
  );

  const handleRevoke = async () => {
    if (!pendingRevoke) return;
    setIsRevoking(true);
    try {
      await mcpTokensService.revoke(pendingRevoke.id);
      toast.success(t("mcpClients.revoked", { name: pendingRevoke.name }));
      setPendingRevoke(null);
      await loadTokens();
    } catch (error) {
      toast.error(errorMessage(error, t("mcpClients.revokeFailed")));
    } finally {
      setIsRevoking(false);
    }
  };

  /** Shown only when there is somebody else's token in the list to label. */
  const showsOwner = useMemo(
    () => isAdmin && (tokens ?? []).some((token) => token.ownerName),
    [isAdmin, tokens],
  );

  const columns: Column<McpToken>[] = [
    {
      key: "name",
      header: t("mcpClients.columnClient"),
      render: (token) => (
        <div className="min-w-0">
          <div className="truncate font-medium">{token.name}</div>
          <code dir="ltr" className="block text-xs text-muted-foreground">
            {token.prefix}…
          </code>
        </div>
      ),
    },
    ...(showsOwner
      ? [
          {
            key: "owner",
            header: t("mcpClients.columnOwner"),
            render: (token: McpToken) => token.ownerName || "—",
          },
        ]
      : []),
    {
      key: "project",
      header: t("mcpClients.columnProject"),
      render: (token) => projectName(token.projectId),
    },
    {
      key: "scopes",
      header: t("mcpClients.columnAccess"),
      render: (token) =>
        token.scopes.includes(SCOPE_PROPOSE) ? (
          <Badge variant="warning" size="sm" className="whitespace-nowrap">
            {t("mcpClients.scopePropose")}
          </Badge>
        ) : (
          <Badge variant="neutral" size="sm" className="whitespace-nowrap">
            {t("mcpClients.scopeRead")}
          </Badge>
        ),
    },
    {
      key: "lastUsed",
      header: t("mcpClients.columnLastUsed"),
      render: (token) =>
        token.lastUsedAt ? (
          timeAgo(token.lastUsedAt, locale)
        ) : (
          <span className="text-muted-foreground">{t("mcpClients.neverUsed")}</span>
        ),
    },
    {
      key: "expires",
      header: t("mcpClients.columnExpires"),
      render: (token) => formatDate(token.expiresAt),
    },
    {
      key: "status",
      header: t("mcpClients.columnStatus"),
      render: (token) => {
        const status = statusOf(token);
        if (status === ACTIVE)
          return <Badge variant="success" size="sm" className="whitespace-nowrap">{t("mcpClients.statusActive")}</Badge>;
        if (status === REVOKED)
          return <Badge variant="danger" size="sm" className="whitespace-nowrap">{t("mcpClients.statusRevoked")}</Badge>;
        return <Badge variant="neutral" size="sm" className="whitespace-nowrap">{t("mcpClients.statusExpired")}</Badge>;
      },
    },
    {
      key: "actions",
      header: "",
      className: "text-end",
      render: (token) =>
        statusOf(token) === ACTIVE ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setPendingRevoke(token)}
            aria-label={t("mcpClients.revoke")}
          >
            <Trash2 size={15} />
            <span className="hidden sm:inline">{t("mcpClients.revoke")}</span>
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="page-container space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold">
            <Plug size={22} /> {t("mcpClients.title")}
          </h1>
          <p className="mt-1 max-w-3xl text-muted-foreground">
            {t("mcpClients.subtitle")}
          </p>
        </div>
        <Button onClick={() => setIsCreateOpen(true)} disabled={Boolean(unavailable)}>
          <Plus size={15} /> {t("mcpClients.new")}
        </Button>
      </div>

      {unavailable ? (
        <Card>
          <div className="flex items-start gap-3">
            <ShieldOff size={18} className="mt-0.5 shrink-0 text-muted-foreground" />
            <div>
              <p className="font-medium">{t("mcpClients.disabledTitle")}</p>
              {/* The server's sentence, not a restatement of it. */}
              <p className="mt-1 text-sm text-muted-foreground">{unavailable}</p>
            </div>
          </div>
        </Card>
      ) : (
        <>
          <Card padding="sm">
            <p className="text-sm text-muted-foreground">
              {t("mcpClients.explainer")}
            </p>
          </Card>

          <div className="flex items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                className="h-4 w-4 shrink-0"
                checked={includeRevoked}
                onChange={(event) => setIncludeRevoked(event.target.checked)}
              />
              {t("mcpClients.showInactive")}
            </label>
            {isAdmin && (
              <span className="text-xs text-muted-foreground">
                {t("mcpClients.adminNote")}
              </span>
            )}
          </div>

          <Table
            columns={columns}
            data={tokens ?? []}
            keyExtractor={(token) => token.id}
            isLoading={tokens === null}
            emptyMessage={t("mcpClients.empty")}
          />
        </>
      )}

      <McpTokenCreateDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        projects={projects}
        onCreated={() => void loadTokens()}
      />

      <Modal
        isOpen={Boolean(pendingRevoke)}
        onClose={() => setPendingRevoke(null)}
        title={t("mcpClients.revokeTitle")}
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setPendingRevoke(null)} disabled={isRevoking}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" onClick={() => void handleRevoke()} isLoading={isRevoking}>
              {t("mcpClients.revoke")}
            </Button>
          </div>
        }
      >
        <p className="text-sm">
          {t("mcpClients.revokeConfirm", {
            name: pendingRevoke?.name,
            project: pendingRevoke ? projectName(pendingRevoke.projectId) : "",
          })}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          {t("mcpClients.revokeEffect")}
        </p>
      </Modal>
    </div>
  );
};
