export const ROUTES = {
  HOME: "/",
  LOGIN: "/auth/login",
  FORGOT_PASSWORD: "/auth/forgot-password",
  RESET_PASSWORD: "/auth/reset-password",
  CHANGE_PASSWORD: "/auth/change-password",
  DASHBOARD: "/dashboard",
  PROJECTS: "/projects",
  /* Retired per-role workspace prefixes. Kept as constants because
     `LegacyProjectPrefixRedirect` registers them and `replaceProjectInPath`
     still has to recognise a URL that arrived from a notification sent before
     the collapse. Nothing *produces* these any more: every link the app writes
     now points at `/projects/:projectId/...`. */
  PM_PROJECTS: "/project-manager/projects",
  ENGINEER_PROJECTS: "/engineer/projects",
  CONSULTANT_PROJECTS: "/consultant-engineer/projects",

  PROJECT_DASHBOARD: "/projects/:projectId/dashboard",
  PROJECT_TASKS: "/projects/:projectId/tasks",
  PROJECT_TASK_DETAIL: "/projects/:projectId/tasks/:taskId",
  PROJECT_DOCUMENTS: "/projects/:projectId/documents",
  PROJECT_SITE_REPORTS: "/projects/:projectId/site-reports",
  PROJECT_ISSUES: "/projects/:projectId/issues",
  PROJECT_DESIGN_CHANGES: "/projects/:projectId/design-changes",
  PROJECT_TEAM: "/projects/:projectId/team",
  PROJECT_MESSAGES: "/projects/:projectId/messages",
  PROJECT_REQUESTS: "/projects/:projectId/requests",
  PROJECT_SITE_VISITS: "/projects/:projectId/site-visits",
  PROJECT_ACTIVITY: "/projects/:projectId/activity",
  PROJECT_EVIDENCE: "/projects/:projectId/evidence",
  PROJECT_IFC: "/projects/:projectId/ifc",
  PROJECT_AI_INTELLIGENCE: "/projects/:projectId/ai-intelligence",
  PROJECT_DETAIL: "/projects/:id",
  PROJECT_SCHEDULE: "/projects/:projectId/schedule",
  PROJECT_MILESTONES: "/projects/:projectId/milestones",
  /* Modules that used to exist only under a role prefix. `my-work` was
     the engineer dashboard and `review-queue` the consultant one; both
     were spelled `dashboard`, which meant three different pages
     depending on who was asking. */
  PROJECT_MY_WORK: "/projects/:projectId/my-work",
  PROJECT_REVIEW_QUEUE: "/projects/:projectId/review-queue",
  PROJECT_REVIEWS: "/projects/:projectId/reviews",
  PROJECT_REVIEW_DETAIL: "/projects/:projectId/reviews/:reviewId",
  PROJECT_REVIEW_HISTORY: "/projects/:projectId/history",
  PROJECT_NOTIFICATIONS: "/projects/:projectId/notifications",
  PROJECT_VOICE_ASSISTANT: "/projects/:projectId/voice-assistant",
  PROJECT_VOICE_REPORTS: "/projects/:projectId/voice-reports",
  PROJECT_PARTIES: "/projects/:projectId/parties",
  TEAM: "/team",
  TASKS: "/tasks",
  TASK_DETAIL: "/tasks/:id",
  DOCUMENTS: "/documents",
  REPORTS: "/reports",
  MESSAGES: "/messages",
  NOTIFICATIONS: "/notifications",
  // Where a tapped push notification lands. Resolved to the real destination
  // by NotificationRedirectPage, which knows the signed-in user's role.
  NOTIFICATION_DETAIL: "/notifications/:id",
  USERS: "/users",
  SETTINGS: "/settings",
  OWNER_DASHBOARD: "/owner-dashboard",
  EXECUTIVE_OVERVIEW: "/executive-overview",
  ADMIN_DASHBOARD: "/admin",
  ADMIN_TEAMS: "/admin/project-teams",
  ADMIN_ACCESS_CONTROL: "/admin/access-control",
  ADMIN_OFFICE_ROLES: "/admin/roles",
  ADMIN_PROJECT_TEAM: "/admin/projects/:projectId/team",
  ISSUES: "/issues",
  DESIGN_CHANGES: "/design-changes",
  SITE_REPORTS: "/site-reports",
  MY_ACTIONS: "/my-actions",
  REQUESTS: "/requests",
  SCHEDULE: "/schedule",
  PROJECT_MILESTONES_PORTFOLIO: "/milestones",
  PROJECT_COLLABORATION: "/projects/:projectId/collaboration",
  NOT_FOUND: "*",
} as const;

/* ─── Date format strings (date-fns compatible) ─── */
export const DATE_FORMAT = "yyyy-MM-dd";
export const DATE_TIME_FORMAT = "yyyy-MM-dd'T'HH:mm:ss";
export const DISPLAY_DATE_FORMAT = "dd MMM yyyy";
export const DISPLAY_DATE_TIME_FORMAT = "dd MMM yyyy, HH:mm";

/* ─── Auth storage keys ─── */
export const ACCESS_TOKEN_KEY = "scp_access_token";
export const REFRESH_TOKEN_KEY = "scp_refresh_token";
