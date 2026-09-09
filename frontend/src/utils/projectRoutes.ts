/**
 * Links into the project workspace.
 *
 * There is one workspace URL now — `/projects/:projectId/…` — so this module
 * no longer decides *which* address somebody gets. It decides two things that
 * are still real questions:
 *
 *  * which modules exist, and which of them this person can actually open, so
 *    a link never lands on a page that immediately redirects away;
 *  * how a backend entity reference (a notification's `relatedEntityType`, an
 *    audit-log row, an AI insight's source) becomes a deep link to that exact
 *    record.
 *
 * The retired version answered the first question from a table keyed on role
 * name and `engineerAffiliation`. That table could only ever describe the six
 * roles that existed when it was written, which is the specific thing a
 * configurable role model makes impossible — an office that creates "Resident
 * Engineer" has no row in it. Module access is therefore derived from the
 * permission each route is guarded by, which is the same answer the router and
 * the endpoint give.
 */

/** Every module the shared workspace registers, and what it costs to open. */
const MODULE_PERMISSIONS: Record<string, string> = {
  dashboard: "task.view",
  "my-work": "task.view",
  tasks: "task.view",
  messages: "task.view",
  notifications: "task.view",
  evidence: "task.view",
  collaboration: "task.view",
  requests: "task.view",
  "site-visits": "task.view",
  activity: "task.view",
  "voice-assistant": "task.view",
  documents: "document.view",
  "site-reports": "site_report.view",
  issues: "issue.view",
  "design-changes": "design_change.view",
  schedule: "schedule.view",
  milestones: "schedule.view",
  ifc: "ifc.view",
  "ai-intelligence": "ai.view_insights",
  // The agents page shows the whole catalogue and marks which of the five
  // this person may run, so it is gated on the broadest of their five
  // permissions rather than on any one agent's. A module missing from this
  // map resolves to `false` and silently redirects to the fallback, so the
  // sidebar link would point at the wrong page without this line.
  agents: "task.view",
  "review-queue": "task.review",
  reviews: "task.review",
  history: "task.review",
  "voice-reports": "field_evidence.verify",
  team: "project.manage_members",
  parties: "project.manage_parties",
};

/** The one portfolio address. Kept as a function so callers need not change. */
export const portfolioProjectsPath = () => "/projects";

export const projectWorkspaceBase = (projectId: string) =>
  `/projects/${encodeURIComponent(projectId)}`;

/** Module everybody with project access can open, used as a fallback. */
const FALLBACK_MODULE = "dashboard";

/**
 * Whether this person can open a module.
 *
 * `hasPermission` is `useRole().hasCapability` — the backend's effective
 * permission list. Callers that have not loaded permissions yet pass nothing
 * and get `true`: a link that turns out to be unreachable redirects, which is
 * a better failure than hiding navigation from somebody who does hold the
 * permission but whose answer had not arrived.
 */
export const canOpenProjectModule = (
  module: string,
  hasPermission?: (code: string) => boolean,
) => {
  const root = module.replace(/^\/+/, "").split(/[/?]/)[0];
  const required = MODULE_PERMISSIONS[root];
  if (!required) return false;
  if (!hasPermission) return true;
  return hasPermission(required);
};

export const projectModulePath = (
  projectId: string,
  module = FALLBACK_MODULE,
  hasPermission?: (code: string) => boolean,
) => {
  const requested = module.replace(/^\/+/, "") || FALLBACK_MODULE;
  const effective = canOpenProjectModule(requested, hasPermission) ? requested : FALLBACK_MODULE;
  return `${projectWorkspaceBase(projectId)}/${effective}`;
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
  hasPermission?: (code: string) => boolean,
) => {
  const target = ENTITY_TARGETS[String(entityType || "").toUpperCase()];
  // An unmapped entity still belongs to the project: the activity feed is the
  // honest destination, never a portfolio-level page that loses the project.
  if (!target) return projectModulePath(projectId, "activity", hasPermission);
  if (!canOpenProjectModule(target.module, hasPermission)) {
    return projectModulePath(projectId, "activity", hasPermission);
  }
  const id = encodeURIComponent(entityId);
  const base = projectModulePath(projectId, target.module, hasPermission);
  if (!entityId) return base;
  // An empty query name means the record is addressed by a path segment.
  return target.query ? `${base}?${target.query}=${id}` : `${base}/${id}`;
};

/**
 * Swap the project in the current pathname while keeping the module in view.
 *
 * The three retired prefixes are still matched. A person can arrive on one of
 * them from a notification sent before the collapse, and although the router
 * redirects, this may run against the pre-redirect pathname — switching
 * projects from such a URL has to keep working rather than silently produce a
 * path with two project ids in it.
 */
export const replaceProjectInPath = (pathname: string, nextProjectId: string) => {
  const encoded = encodeURIComponent(nextProjectId);
  return pathname
    .replace(/^\/project-manager\/projects\/[^/]+/, `/projects/${encoded}`)
    .replace(/^\/engineer\/projects\/[^/]+/, `/projects/${encoded}`)
    .replace(/^\/consultant-engineer\/projects\/[^/]+/, `/projects/${encoded}`)
    .replace(/^\/projects\/[^/]+/, `/projects/${encoded}`);
};
