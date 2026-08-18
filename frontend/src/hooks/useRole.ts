import { useTranslation } from "react-i18next";
import { useAuthStore } from "../app/store/auth.store";
import { resolvePermission } from "../utils/permissions";
import { usePermissions } from "./usePermissions";
import { getRoleLabel, getDefaultRoute } from "../utils/roleMapper";
import type { UserRole } from "../types/auth";
import type { PermissionAction } from "../utils/permissions";

export const useRole = () => {
  const { i18n } = useTranslation();
  const user = useAuthStore((state) => state.user);
  const role: UserRole | undefined = user?.role;
  const {
    permissions: effectivePermissions,
    isReady: permissionsReady,
    isLoading: permissionsLoading,
    error: permissionsError,
    hasPermission: hasBackendPermission,
    refresh: refreshPermissions,
  } = usePermissions();

  // Prefers the backend's effective-permission answer once it has loaded for
  // any action the catalogue actually models with a plain role check (see
  // BACKEND_PERMISSION_CODE); falls back to the static role table for
  // everything else, and while the backend answer is still loading, so a
  // button never has to wait on a network round trip to appear. Backend
  // authorization is still re-checked server-side regardless of this result.
  const checkPermission = (action: PermissionAction): boolean =>
    resolvePermission(role, action, effectivePermissions);

  const checkAnyPermission = (actions: PermissionAction[]): boolean => {
    if (!role) return false;
    return actions.some(checkPermission);
  };

  const checkAllPermissions = (actions: PermissionAction[]): boolean => {
    if (!role) return false;
    return actions.every(checkPermission);
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

  const locale = (i18n.resolvedLanguage || i18n.language || "en").startsWith("ar") ? "ar" : "en";
  const roleLabel = role ? getRoleLabel(role, locale) : "";
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
    // A small number of capabilities (e.g. `ai.view_insights`, `schedule.view`)
    // exist only in the backend catalogue with no legacy PermissionAction name
    // to bridge from. `hasCapability` checks a raw catalogue code directly,
    // for UI (navigation, buttons) that wants to reflect one of those without
    // inventing a fictitious legacy action for it. Same loading/fallback
    // behaviour as `checkPermission`: `false` until permissions are ready, so
    // callers should gate on `permissionsReady` if a default-visible-until-known
    // fallback (rather than hidden-until-known) is more appropriate.
    hasCapability: hasBackendPermission,
    permissionsReady,
    permissionsLoading,
    permissionsError,
    refreshPermissions,
  };
};
