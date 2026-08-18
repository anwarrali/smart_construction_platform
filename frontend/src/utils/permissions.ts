import type { UserRole } from "../types/auth";

export type PermissionAction =
  | "view_all_projects"
  | "create_project"
  | "edit_project"
  | "delete_project"
  | "manage_project_members"
  | "view_project_details"
  | "view_project_tasks"
  | "create_task"
  | "edit_task"
  | "delete_task"
  | "assign_task"
  | "update_task_status"
  | "view_own_tasks"
  | "view_all_tasks"
  | "upload_document"
  | "view_documents"
  | "delete_document"
  | "submit_report"
  | "review_report"
  | "view_reports"
  | "view_owner_dashboard"
  | "view_cost_details"
  | "manage_users"
  | "manage_system_settings"
  | "send_message"
  | "view_messages"
  | "view_notifications"
  | "view_gantt_chart"
  | "view_analytics"
  | "export_data"
  | "create_issue"
  | "manage_issues"
  | "propose_design_change"
  | "approve_design_change"
  | "submit_cost_validation"
  | "review_cost_validation"
  | "submit_site_report";

const ROLE_PERMISSIONS: Record<UserRole, PermissionAction[]> = {
  admin: [
    "view_all_projects",
    "create_project",
    "edit_project",
    "manage_project_members",
    "view_project_details",
    "manage_users",
    "manage_system_settings",
    "view_analytics",
    "export_data",
  ],
  owner: [
    "view_project_details",
    "view_project_tasks",
    "view_reports",
    "view_owner_dashboard",
    "view_cost_details",
    "view_documents",
    "view_messages",
    "view_notifications",
    "submit_cost_validation",
  ],
  project_manager: [
    "edit_project",
    "manage_project_members",
    "view_project_details",
    "view_project_tasks",
    "create_task",
    "edit_task",
    "delete_task",
    "assign_task",
    "update_task_status",
    "view_own_tasks",
    "view_all_tasks",
    "upload_document",
    "view_documents",
    "delete_document",
    "submit_report",
    "view_reports",
    "view_cost_details",
    "send_message",
    "view_messages",
    "view_notifications",
    "view_gantt_chart",
    "view_analytics",
    "export_data",
    "create_issue",
    "manage_issues",
    "propose_design_change",
    "submit_site_report",
  ],
  engineer: [
    "view_project_details",
    "view_project_tasks",
    "update_task_status",
    "view_own_tasks",
    "upload_document",
    "view_documents",
    "submit_report",
    "view_reports",
    "send_message",
    "view_messages",
    "view_notifications",
    "submit_site_report",
    "create_issue",
  ],
  consultant: [
    "view_project_details",
    "view_project_tasks",
    "view_all_tasks",
    "view_documents",
    "review_report",
    "view_reports",
    "send_message",
    "view_messages",
    "view_notifications",
    "approve_design_change",
    "review_cost_validation",
    "create_issue",
  ],
  worker: [
    "view_project_details",
    "view_own_tasks",
    "view_notifications",
  ],
};

export const hasPermission = (
  role: UserRole,
  action: PermissionAction,
): boolean => {
  return ROLE_PERMISSIONS[role]?.includes(action) ?? false;
};

export const hasAnyPermission = (
  role: UserRole,
  actions: PermissionAction[],
): boolean => {
  return actions.some((action) => hasPermission(role, action));
};

export const hasAllPermissions = (
  role: UserRole,
  actions: PermissionAction[],
): boolean => {
  return actions.every((action) => hasPermission(role, action));
};

export const getPermissions = (role: UserRole): PermissionAction[] => {
  return ROLE_PERMISSIONS[role] || [];
};

/**
 * Bridges the legacy role/action names above to the backend's permission
 * catalogue codes (`app.core.permission_catalogue` / GET `/access-control/me`).
 *
 * Only actions with a genuine one-to-one catalogue equivalent are listed here
 * — one the backend enforces with a plain `require(db, user, code, project_id)`
 * role check. Actions left out (e.g. `edit_task`, `update_task_status`,
 * `delete_project`) are ownership- or assignment-scoped on the server (ROLE
 * such as PM-of-this-project, or task-assignee is checked in the endpoint
 * itself), so a flat permission code cannot represent them without either
 * losing that scoping or misrepresenting who the button should show for; those
 * keep using the static role table above for UI visibility, exactly as before.
 *
 * `useRole().checkPermission` prefers the live backend answer for anything
 * mapped here once it has loaded, and falls back to the static table for
 * everything else (and while the backend answer is still loading).
 */
export const BACKEND_PERMISSION_CODE: Partial<Record<PermissionAction, string>> = {
  view_all_projects: "platform.view_all_projects",
  create_project: "platform.create_project",
  edit_project: "project.edit",
  manage_project_members: "project.manage_members",
  create_task: "task.create",
  upload_document: "document.upload",
  submit_report: "site_report.submit",
  submit_site_report: "site_report.submit",
  view_gantt_chart: "schedule.view",
  manage_users: "platform.manage_users",
  create_issue: "issue.create",
  manage_issues: "issue.resolve",
  propose_design_change: "design_change.propose",
  approve_design_change: "design_change.approve",
};

/**
 * The single hybrid decision `useRole().checkPermission` makes, pulled out as
 * a pure function so it is testable without rendering a component: prefer the
 * backend's effective-permission list for anything `BACKEND_PERMISSION_CODE`
 * maps, once that list has actually loaded (`effectivePermissions !== null`);
 * otherwise fall back to the static role table — for actions with no backend
 * mapping at all, and for any mapped action while the backend answer is still
 * in flight.
 */
export const resolvePermission = (
  role: UserRole | undefined,
  action: PermissionAction,
  effectivePermissions: string[] | null,
): boolean => {
  if (!role) return false;
  const backendCode = BACKEND_PERMISSION_CODE[action];
  if (backendCode && effectivePermissions !== null) {
    return effectivePermissions.includes(backendCode);
  }
  return hasPermission(role, action);
};
