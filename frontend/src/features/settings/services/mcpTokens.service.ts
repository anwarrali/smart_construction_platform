import api from "../../../services/api";
import { ENDPOINTS } from "../../../services/endpoints";
import type {
  McpToken,
  McpTokenCreateRequest,
  McpTokenCreated,
} from "../../../types/mcp";

/**
 * MCP client tokens, and the one piece of knowledge the API layer cannot hold:
 * the address a client is configured with.
 *
 * `serverUrl` is not a call. Nothing in this application ever requests the MCP
 * endpoint — it exists for something else entirely — so the URL is assembled
 * here, from the same base every other request uses, purely to be copied into
 * a client's configuration file.
 */
export const mcpTokensService = {
  list: (includeRevoked = false): Promise<McpToken[]> =>
    api.mcpTokens.list(includeRevoked),
  create: (data: McpTokenCreateRequest): Promise<McpTokenCreated> =>
    api.mcpTokens.create(data),
  revoke: (tokenId: string): Promise<void> => api.mcpTokens.revoke(tokenId),
};

/**
 * The MCP server address for one project, absolute.
 *
 * `VITE_API_BASE_URL` is usually the relative `/api/v1`, which is fine for
 * this app — every request is same-origin — but useless in a configuration
 * file read by a program on somebody's laptop. Resolved against the current
 * origin so what gets copied is a URL that can actually be dialled.
 *
 * Whether it can be dialled *from that laptop* is a question this code cannot
 * answer — a development server on localhost cannot be — which is why the
 * dialog says so rather than pretending the copied value always works.
 */
export const mcpServerUrl = (projectId: string): string => {
  const base =
    import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "") || "/api/v1";
  const absolute = /^https?:\/\//i.test(base)
    ? base
    : `${window.location.origin}${base}`;
  return `${absolute}${ENDPOINTS.MCP.SERVER(projectId)}`;
};

/** The `mcpServers` entry a client expects, ready to paste. */
export const mcpClientConfig = (projectId: string, secret: string): string =>
  JSON.stringify(
    {
      mcpServers: {
        "construction-platform": {
          url: mcpServerUrl(projectId),
          headers: { Authorization: `Bearer ${secret}` },
        },
      },
    },
    null,
    2,
  );
