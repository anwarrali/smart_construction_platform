export const ENDPOINTS = {
  AUTH: {
    LOGIN: "/auth/login",
    REFRESH: "/auth/refresh",
    LOGOUT: "/auth/logout",
    FORGOT_PASSWORD: "/auth/forgot-password",
    RESET_PASSWORD: "/auth/reset-password",
    ME: "/auth/me",
  },

  USERS: {
    BASE: "/users",
    BY_ID: (id: string) => `/users/${id}`,
    PROFILE: "/users/profile",
    UPDATE_PROFILE: "/users/profile",
    CHANGE_PASSWORD: "/users/change-password",
    AVATAR: "/users/avatar",
    RESET_PASSWORD: (id: string) => `/users/${id}/reset-password`,
  },

  PROJECTS: {
    BASE: "/projects",
    BY_ID: (id: string) => `/projects/${id}`,
    MEMBERS: (id: string) => `/projects/${id}/members`,
    ADD_MEMBER: (id: string) => `/projects/${id}/members`,
    REMOVE_MEMBER: (projectId: string, userId: string) =>
      `/projects/${projectId}/members/${userId}`,
    UPDATE_ASSIGNMENT: (projectId: string, userId: string) =>
      `/projects/${projectId}/members/${userId}/assignment`,
    AVAILABLE_ENGINEERS: (id: string) => `/projects/${id}/available-engineers`,
    AVAILABLE_TEAM_MEMBERS: (id: string) => `/projects/${id}/available-team-members`,
    APPROVAL_WORKFLOW: (id: string) => `/projects/${id}/approval-workflow`,
    SUMMARY: "/projects/summary",
    OWNER_DASHBOARD: (id: string) => `/projects/${id}/owner-dashboard`,
  },

  TASKS: {
    BASE: "/tasks",
    BY_ID: (id: string) => `/tasks/${id}`,
    BY_PROJECT: (projectId: string) => `/tasks/project/${projectId}`,
    MY_TASKS: "/tasks/my-tasks",
    COMMENTS: (id: string) => `/tasks/${id}/comments`,
    PROGRESS: (id: string) => `/tasks/${id}/progress`,
    DEPENDENCIES: (id: string) => `/tasks/${id}/dependencies`,
    REVIEW_AUTHORITY: (id: string) => `/tasks/${id}/review-authority`,
    ANALYTICS: (projectId: string) => `/tasks/analytics/project/${projectId}`,
    REORDER: "/tasks/reorder",
  },
  FIELD_SUBMISSIONS: {
    BASE: "/field-submissions",
    BY_ID: (id: string) => `/field-submissions/${id}`,
    BY_TASK: (taskId: string) => `/field-submissions/task/${taskId}`,
    MINE: "/field-submissions/mine",
    PENDING: "/field-submissions/pending",
    VERIFY: (id: string) => `/field-submissions/${id}/verify`,
    REJECT: (id: string) => `/field-submissions/${id}/reject`,
    PHOTO_CATEGORIES: (photoId: string) => `/field-submissions/photos/${photoId}/categories`,
  },
  PHOTO_ARCHIVE: {
    LIST: (projectId: string) => `/projects/${projectId}/evidence-photos`,
    DETAIL: (projectId: string, photoId: string) =>
      `/projects/${projectId}/evidence-photos/${photoId}`,
    CATEGORIES: (projectId: string) => `/projects/${projectId}/photo-categories`,
    CATEGORY: (projectId: string, categoryId: string) =>
      `/projects/${projectId}/photo-categories/${categoryId}`,
  },

  MILESTONES: {
    BASE: "/milestones",
    BY_ID: (id: string) => `/milestones/${id}`,
  },

  MESSAGES: {
    BASE: "/messages",
    PARTICIPANTS: "/messages/participants",
    RECIPIENT_OPTIONS: "/messages/recipient-options",
    CONVERSATIONS: "/messages/conversations",
    CONVERSATION: (id: string) => `/messages/conversations/${id}`,
    CONVERSATION_MESSAGES: (id: string) => `/messages/conversations/${id}/messages`,
    CONVERSATION_READ: (id: string) => `/messages/conversations/${id}/read`,
    ANNOUNCEMENTS: "/messages/announcements",
    SEARCH: "/messages/search",
    CONTEXT: (type: string, id: string) => `/messages/context/${type}/${id}`,
    UNREAD_COUNT: "/messages/unread-count",
    MARK_READ: (id: string) => `/messages/${id}/read`,
  },

  DOCUMENTS: {
    BASE: "/documents",
    BY_ID: (id: string) => `/documents/${id}`,
    UPLOAD: "/documents/upload",
    DOWNLOAD: (id: string) => `/documents/${id}/download`,
    BY_PROJECT: (projectId: string) => `/documents/project/${projectId}`,
    SEARCH: "/documents/search",
    ARCHIVE: (id: string) => `/documents/${id}/archive`,
    RESTORE: (id: string) => `/documents/${id}/restore`,
  },

  REPORTS: {
    BASE: "/reports",
    BY_ID: (id: string) => `/reports/${id}`,
    BY_PROJECT: (projectId: string) => `/reports/project/${projectId}`,
    SUBMIT: "/reports/submit",
    REVIEW: (id: string) => `/reports/${id}/review`,
  },

  NOTIFICATIONS: {
    BASE: "/notifications",
    BY_ID: (id: string) => `/notifications/${id}`,
    MARK_READ: (id: string) => `/notifications/${id}/read`,
    MARK_ALL_READ: "/notifications/read-all",
    UNREAD_COUNT: "/notifications/unread-count",
    PREFERENCES: "/notifications/preferences",
  },

  SCHEDULING: {
    GANTT: (projectId: string) => `/scheduling/${projectId}/gantt`,
    CRITICAL_PATH: (projectId: string) => `/scheduling/${projectId}/critical-path`,
    TIMELINE: (projectId: string) => `/scheduling/${projectId}/timeline`,
    DELAY_ANALYSIS: (projectId: string) => `/scheduling/${projectId}/delay-analysis`,
    SHIFT: (projectId: string) => `/scheduling/${projectId}/shift`,
  },

  ISSUES: {
    BASE: "/issues",
    BY_ID: (id: string) => `/issues/${id}`,
    BY_PROJECT: (projectId: string) => `/issues/project/${projectId}`,
  },

  DASHBOARD: {
    STATS: "/dashboard/stats",
    PROJECT: (id: string) => `/dashboard/projects/${id}`,
    ENGINEER_PROJECT: (id: string) => `/dashboard/engineer/projects/${id}`,
  },

  CONSULTANT: {
    DASHBOARD: (projectId: string) => `/consultant/projects/${projectId}/dashboard`,
    REVIEWS: (projectId: string) => `/consultant/projects/${projectId}/reviews`,
    REVIEW: (projectId: string, reviewId: string) => `/consultant/projects/${projectId}/reviews/${reviewId}`,
    HISTORY: (projectId: string) => `/consultant/projects/${projectId}/history`,
  },

  DESIGN_CHANGES: {
    BASE: "/design-changes",
    BY_ID: (id: string) => `/design-changes/${id}`,
    BY_PROJECT: (projectId: string) => `/design-changes/project/${projectId}`,
    AFFECTED_DISCIPLINES: (id: string) =>
      `/design-changes/${id}/affected-disciplines`,
  },

  SITE_REPORTS: {
    BASE: "/site-reports",
    LIST: "/site-reports",
    BY_ID: (id: string) => `/site-reports/${id}`,
    BY_PROJECT: (projectId: string) => `/site-reports/project/${projectId}`,
    SUBMIT: "/site-reports/submit",
  },

  ATTACHMENTS: {
    BASE: "/attachments",
    UPLOAD: "/attachments/upload",
    BY_ID: (id: string) => `/attachments/${id}`,
  },
  FIELD: {
    CONTEXT: "/field/context",
    VALIDATE_PROPOSAL: "/field/action-proposals/validate",
    CONFIRM_PROPOSAL: "/field/action-proposals/confirm",
  },

  WEBSOCKET: {
    CONNECT: "/ws",
    PROJECT_ROOM: (projectId: string) => `/ws/project/${projectId}`,
    NOTIFICATIONS: "/ws/notifications",
    MESSAGES: "/ws/messages",
  },

  ANALYTICS: {
    DASHBOARD: "/analytics/dashboard",
    PROJECT: (projectId: string) => `/analytics/project/${projectId}`,
    USER: (userId: string) => `/analytics/user/${userId}`,
    EXPORT: "/analytics/export",
  },

  SETTINGS: {
    BASE: "/settings",
    GENERAL: "/settings/general",
    NOTIFICATIONS: "/settings/notifications",
    SECURITY: "/settings/security",
    SYSTEM: "/settings/system",
  },

  UPLOAD: {
    SINGLE: "/upload/single",
    MULTIPLE: "/upload/multiple",
    DELETE: (fileId: string) => `/upload/${fileId}`,
  },
} as const;
