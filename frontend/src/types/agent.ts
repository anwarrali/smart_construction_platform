/**
 * The five project agents, as the backend describes them.
 *
 * Mirrors `app/services/agents/contracts.py` and the responses in
 * `app/api/agents.py`. Nothing here is invented: every field is one the API
 * already returns, because the agent layer was fully built and simply had no
 * client.
 */

/** What kind of claim a finding makes. Ordered strongest to weakest. */
export type Certainty =
  | "FACT"
  | "DETECTED"
  | "INFERRED"
  | "RECOMMENDATION"
  | "UNCERTAIN";

/** One agent's declared contract, from `GET .../agents`. */
export interface AgentDefinition {
  name: string;
  title: string;
  responsibility: string;
  /** The only tools this agent may call — a hard gate, not advice in a prompt. */
  allowedTools: string[];
  /** Catalogue permission the caller needs to run it. */
  permission: string;
  /** `AIInsight.source_engine` its findings carry. */
  sourceEngine: string;
  /** Domain events that would wake it when automatic analysis is on. */
  subscribesTo: string[];
}

export interface AgentCatalogue {
  /** Agents this caller may actually run here. A subset of `catalogue`. */
  available: AgentDefinition[];
  /** Every agent that exists, whether or not this caller may run it. */
  catalogue: AgentDefinition[];
}

export interface AgentEvidence {
  sourceType: string;
  sourceId: string;
  label: string;
  detail: Record<string, unknown>;
}

export interface AgentFinding {
  code: string;
  certainty: Certainty;
  severity: string;
  confidence: number;
  title: string;
  description: string;
  /** Why the agent concluded this — the reasoning, not a restatement. */
  reason: string;
  recommendedAction: string;
  /** True when acting on it would change project data. A person decides. */
  requiresConfirmation: boolean;
  evidence: AgentEvidence[];
  affected: Record<string, unknown>;
}

/** One tool call an agent made, recorded so its reasoning is reviewable. */
export interface AgentToolCall {
  tool: string;
  ok: boolean;
  errorCode: string | null;
  arguments: Record<string, unknown>;
}

/** The result of one run, from `POST .../agents/{name}/run`. */
export interface AgentRunResult {
  agent: string;
  ok: boolean;
  findingCount: number;
  findings: AgentFinding[];
  storedInsightIds: string[];
  toolCalls: AgentToolCall[];
  durationMs: number | null;
  errorCode?: string;
  error?: string;
}

/** Why an agent did not run. A skip is a normal outcome, not a failure. */
export interface AgentSkip {
  agent: string;
  shouldRun: boolean;
  reason: string;
  skipCode: string | null;
}

/** One governed pass over several agents, from `POST .../agents/orchestrate`. */
export interface OrchestrationReport {
  projectId: string;
  trigger: { type: string; reason: string };
  ran: (AgentRunResult & { reason?: string })[];
  skipped: AgentSkip[];
  failed: (Partial<AgentRunResult> & { agent: string })[];
  agentsRun: number;
  agentsSkipped: number;
  agentsFailed: number;
  findingCount: number;
}

/** A persisted run record, from `GET .../agents/runs`. */
export interface AgentRunRecord {
  id: string;
  agent: string;
  status: string;
  /** MANUAL when a person asked; EVENT when something happened. */
  triggerType: string;
  triggerReason: string | null;
  findingCount: number;
  findingCodes: string[];
  highestConfidence: number | null;
  toolCalls: AgentToolCall[];
  insightIds: string[];
  durationMs: number | null;
  errorCode: string | null;
  error: string | null;
  createdAt: string | null;
}

export interface AgentSubscriptions {
  /** Event type → the agents that declared an interest in it. */
  subscriptions: Record<string, string[]>;
  /** Whether event-triggered analysis is switched on for this server. */
  automaticAnalysisEnabled: boolean;
  note: string;
}
