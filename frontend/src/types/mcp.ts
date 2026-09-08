/**
 * MCP client tokens — the credential a desktop AI client authenticates with.
 *
 * There is deliberately **no field here that carries a stored secret**.
 * `McpTokenCreated.token` is the plaintext, and it exists for exactly one
 * response: the server keeps only a SHA-256 and cannot produce it again. Every
 * other shape describes a token by its `prefix`, which identifies it in a list
 * and is useless for using it.
 */

/** Read the project: list tools and call read-only ones. Every token has it. */
export const SCOPE_READ = "mcp:read";
/** Reach tools that propose changes. Optional, and off unless asked for. */
export const SCOPE_PROPOSE = "mcp:propose";

export type McpScope = typeof SCOPE_READ | typeof SCOPE_PROPOSE;

export interface McpToken {
  id: string;
  /** What the person called it — "Claude Desktop, work laptop". */
  name: string;
  /** The single project this token may reach. */
  projectId: string;
  /** The displayable head of the secret, e.g. `cpmcp_A1b2C3d4`. */
  prefix: string;
  scopes: McpScope[];
  createdAt: string;
  expiresAt: string;
  lastUsedAt: string | null;
  revokedAt: string | null;
  /**
   * Neither revoked nor expired. Answered by the server rather than recomputed
   * here from two timestamps and a clock the browser may not share with it.
   */
  active: boolean;
  ownerId: string;
  ownerName: string | null;
}

export interface McpTokenCreateRequest {
  name: string;
  projectId: string;
  /** Omitted means read-only. `mcp:read` is implied by the server. */
  scopes?: McpScope[];
  /** Omitted means the server's default; capped by its maximum. */
  lifetimeDays?: number;
}

export interface McpTokenCreated {
  /** The only time the secret is ever available. */
  token: string;
  record: McpToken;
  /** The server's own sentence about that fact, shown rather than restated. */
  warning: string;
}

/** A token that has run out of time rather than been taken back. */
export const isExpired = (token: McpToken): boolean =>
  !token.active && !token.revokedAt;
