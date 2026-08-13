import type { UserRole } from "../types/auth";

export type EngineerAffiliation = "internal_engineer" | "main_contractor" | "external_consultant" | undefined;

/** Route prefix that owns the project workspace for a given role. */
export const portfolioProjectsPath = (role?: UserRole, affiliation?: EngineerAffiliation) => {
  if (role === "project_manager") return "/project-manager/projects";
  if (role === "engineer") return affiliation === "external_consultant" ? "/consultant-engineer/projects" : "/engineer/projects";
  return "/projects";
};

export const projectWorkspaceBase = (projectId: string, role?: UserRole, affiliation?: EngineerAffiliation) =>
  `${portfolioProjectsPath(role, affiliation)}/${encodeURIComponent(projectId)}`;

/**
 * Modules each role can actually reach, mirroring the guards registered in
 * `app/router/index.tsx`. Linking to a module a role cannot open produces a
 * redirect to the dashboard selector, which silently drops project context —
 * so unreachable modules degrade to a module the role always has instead.
 */
const COMMON_MODULES = [
  "dashboard", "evidence", "ifc", "ai-intelligence", "messages",
  "requests", "site-visits", "activity", "collaboration",
] as const;

const MODULE_ACCESS: Record<string, readonly string[]> = {
  admin: [...COMMON_MODULES, "tasks", "team", "documents", "site-reports", "issues", "design-changes", "schedule", "milestones"],
  owner: [...COMMON_MODULES, "documents", "site-reports", "issues", "design-changes"],
  project_manager: [...COMMON_MODULES, "tasks", "documents", "site-reports", "issues", "design-changes", "team", "schedule", "milestones", "notifications"],
  engineer: [...COMMON_MODULES, "tasks", "site-reports", "issues", "documents", "notifications", "voice-reports"],
  consultant_engineer: [...COMMON_MODULES, "reviews", "history", "documents", "site-reports", "issues", "design-changes", "notifications"],
  consultant: [...COMMON_MODULES, "schedule"],
  worker: ["dashboard", "activity", "messages"],
};

const accessKey = (role?: UserRole, affiliation?: EngineerAffiliation) =>
  role === "engineer" && affiliation === "external_consultant" ? "consultant_engineer" : role || "worker";

/** Module a role can always open, used when a requested module is out of reach. */
const FALLBACK_MODULE = "dashboard";

export const canOpenProjectModule = (module: string, role?: UserRole, affiliation?: EngineerAffiliation) => {
  const allowed = MODULE_ACCESS[accessKey(role, affiliation)];
  if (!allowed) return false;
  const root = module.replace(/^\/+/, "").split(/[/?]/)[0];
  return allowed.includes(root);
};

export const projectModulePath = (
  projectId: string,
  module = FALLBACK_MODULE,
  role?: UserRole,
  affiliation?: EngineerAffiliation,
) => {
  const requested = module.replace(/^\/+/, "") || FALLBACK_MODULE;
  const effective = canOpenProjectModule(requested, role, affiliation) ? requested : FALLBACK_MODULE;
  return `${projectWorkspaceBase(projectId, role, affiliation)}/${effective}`;
};

/**
 * Maps a backend entity reference (notification `relatedEntityType`, audit-log
 * `entityType`, AI insight source) onto the deep link that opens that exact
 * record inside the project workspace.
 */
const ENTITY_TARGETS: Record<string, { module: string; query?: string }> = {
  TASK: { module: "tasks", query: "" },
  ISSUE: { module: "issues", query: "issueId" },
  DESIGN_CHANGE: { module: "design-changes", query: "changeId" },
  SITE_REPORT: { module: "site-reports", query: "reportId" },
  OWNER_REQUEST: { module: "requests", query: "requestId" },
  SITE_VISIT: { module: "site-visits", query: "visitId" },
  AI_INSIGHT: { module: "ai-intelligence", query: "insightId" },
  MILESTONE: { module: "milestones", query: "milestoneId" },
  DOCUMENT: { module: "documents", query: "documentId" },
  FIELD_SUBMISSION: { module: "evidence", query: "submissionId" },
  IFC_MODEL_VERSION: { module: "ifc", query: "versionId" },
  IFC_MODEL_GROUP: { module: "ifc", query: "modelId" },
  IFC_COMPARISON: { module: "ifc", query: "comparisonId" },
  IFC_SUGGESTION: { module: "ai-intelligence", query: "insightId" },
  IFC_COORDINATION_FINDING: { module: "ai-intelligence", query: "insightId" },
  TASK_REVIEW: { module: "reviews", query: "" },
  CONSULTANT_REVIEW: { module: "reviews", query: "" },
  VOICE_ANALYSIS: { module: "voice-reports", query: "analysisId" },
  MESSAGE: { module: "messages", query: "messageId" },
  CONVERSATION: { module: "messages", query: "conversationId" },
  PROJECT: { module: "dashboard" },
  PROJECT_MEMBER: { module: "team" },
  USER: { module: "team", query: "userId" },
};

export const projectEntityPath = (
  projectId: string,
  entityType: string,
  entityId: string,
  role?: UserRole,
  affiliation?: EngineerAffiliation,
) => {
  const target = ENTITY_TARGETS[String(entityType || "").toUpperCase()];
  // An unmapped entity still belongs to the project: the activity feed is the
  // honest destination, never a portfolio-level page that loses the project.
  if (!target) return projectModulePath(projectId, "activity", role, affiliation);
  if (!canOpenProjectModule(target.module, role, affiliation)) {
    return projectModulePath(projectId, "activity", role, affiliation);
  }
  const id = encodeURIComponent(entityId);
  const base = projectModulePath(projectId, target.module, role, affiliation);
  if (!entityId) return base;
  // An empty query name means the record is addressed by a path segment.
  return target.query ? `${base}?${target.query}=${id}` : `${base}/${id}`;
};

/** Swap the project in the current pathname while keeping the module in view. */
export const replaceProjectInPath = (pathname: string, nextProjectId: string) => {
  const encoded = encodeURIComponent(nextProjectId);
  return pathname
    .replace(/^\/project-manager\/projects\/[^/]+/, `/project-manager/projects/${encoded}`)
    .replace(/^\/engineer\/projects\/[^/]+/, `/engineer/projects/${encoded}`)
    .replace(/^\/consultant-engineer\/projects\/[^/]+/, `/consultant-engineer/projects/${encoded}`)
    .replace(/^\/projects\/[^/]+/, `/projects/${encoded}`);
};
