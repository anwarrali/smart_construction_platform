import { useAuthStore } from "../app/store/auth.store";
import {
  hasPermission,
  hasAnyPermission,
  hasAllPermissions,
} from "../utils/permissions";
import { getRoleLabel, getDefaultRoute } from "../utils/roleMapper";
import type { UserRole } from "../types/auth";
import type { PermissionAction } from "../utils/permissions";

export const useRole = () => {
  const user = useAuthStore((state) => state.user);
  const role: UserRole | undefined = user?.role;

  const checkPermission = (action: PermissionAction): boolean => {
    if (!role) return false;
    return hasPermission(role, action);
  };

  const checkAnyPermission = (actions: PermissionAction[]): boolean => {
    if (!role) return false;
    return hasAnyPermission(role, actions);
  };

  const checkAllPermissions = (actions: PermissionAction[]): boolean => {
    if (!role) return false;
    return hasAllPermissions(role, actions);
  };

  const isAdmin = role === "admin";
  const isProjectManager = role === "project_manager";
  const isOwner = role === "owner";
  const isEngineer = role === "engineer";
  const isMainContractorEngineer = isEngineer
    && user?.engineerAffiliation === "main_contractor"
    && user?.status === "active";
  const isConsultantEngineer = isEngineer
    && user?.engineerAffiliation === "external_consultant"
    && user?.status === "active";

  const roleLabel = role ? getRoleLabel(role) : "";
  const dashboardRoute = role ? getDefaultRoute(role) : "/";

  return {
    role,
    roleLabel,
    dashboardRoute,
    isAdmin,
    isProjectManager,
    isOwner,
    isEngineer,
    isMainContractorEngineer,
    isConsultantEngineer,
    checkPermission,
    checkAnyPermission,
    checkAllPermissions,
  };
};
