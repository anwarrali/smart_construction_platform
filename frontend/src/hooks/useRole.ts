import { useTranslation } from "react-i18next";
import { useAuthStore } from "../app/store/auth.store";
import { usePermissions } from "./usePermissions";

/**
 * The signed-in person's office role and capabilities.
 *
 * Every access decision in the interface is `hasCapability(code)`: a catalogue
 * code from `GET /access-control/me`, the same answer the endpoint behind the
 * button will give. The office role is for *display* — its name, and whether
 * the person is office staff or an external participant. There is no role
 * string to branch on: an office defines its own roles, so a check written
 * against a role name would be wrong for every role the office invents.
 */
export const useRole = () => {
  const { i18n } = useTranslation();
  const user = useAuthStore((state) => state.user);
  const {
    isReady: permissionsReady,
    isLoading: permissionsLoading,
    error: permissionsError,
    hasPermission,
    hasAnyPermission,
    refresh: refreshPermissions,
  } = usePermissions();

  const orgRole = user?.orgRole ?? null;
  /** Office staff, as opposed to an external participant. */
  const isInternal = orgRole ? orgRole.isInternalOnly : user?.isInternal !== false;

  const locale = (i18n.resolvedLanguage || i18n.language || "en").startsWith("ar") ? "ar" : "en";
  /** What the office calls this person's role. */
  const orgRoleLabel = orgRole
    ? (locale === "ar" ? orgRole.nameAr || orgRole.nameEn : orgRole.nameEn)
    : "";

  return {
    orgRole,
    orgRoleLabel,
    roleLabel: orgRoleLabel,
    isInternal,
    disciplines: user?.disciplines ?? [],
    /** Whether the backend grants this catalogue code. `false` until loaded. */
    hasCapability: hasPermission,
    hasAnyCapability: hasAnyPermission,
    permissionsReady,
    permissionsLoading,
    permissionsError,
    refreshPermissions,
  };
};
