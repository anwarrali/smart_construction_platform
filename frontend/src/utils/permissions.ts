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
