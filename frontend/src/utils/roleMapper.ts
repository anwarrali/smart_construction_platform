import type { UserRole } from "../types/auth";

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Admin",
  owner: "Project Owner",
  project_manager: "Project Manager",
  engineer: "Engineer",
  consultant: "Consultant",
};

export const ROLE_LABELS_AR: Record<UserRole, string> = {
  admin: "مدير النظام",
  owner: "مالك المشروع",
  project_manager: "مدير المشروع",
  engineer: "مهندس",
  consultant: "استشاري",
};

export const getRoleLabel = (
  role: UserRole,
  locale: "en" | "ar" = "en",
): string => {
  return locale === "ar" ? ROLE_LABELS_AR[role] : ROLE_LABELS[role];
};

/**
 * Display order only.
 *
 * This used to be consulted as seniority and is not an authorization
 * input any more: what somebody may do comes from their role's
 * permissions, which an office configures. Kept so lists sort sensibly.
 */
export const ROLE_HIERARCHY: Record<UserRole, number> = {
  admin: 10,
  owner: 8,
  project_manager: 7,
  engineer: 5,
  consultant: 6,
};

export const isRoleHigherOrEqual = (
  role: UserRole,
  comparedTo: UserRole,
): boolean => {
  return ROLE_HIERARCHY[role] >= ROLE_HIERARCHY[comparedTo];
};

export const DASHBOARD_ROUTES: Record<UserRole, string> = {
  admin: "/admin",
  owner: "/owner-dashboard",
  project_manager: "/dashboard",
  engineer: "/dashboard",
  consultant: "/dashboard",
};

export const getDefaultRoute = (role: UserRole): string => {
  return DASHBOARD_ROUTES[role] || "/dashboard";
};

export const ROLES_OPTIONS = [
  { value: "admin", label: "Admin" },
  { value: "owner", label: "Project Owner" },
  { value: "project_manager", label: "Project Manager" },
  { value: "engineer", label: "Engineer" },
  { value: "consultant", label: "Consultant" },
] as const;
