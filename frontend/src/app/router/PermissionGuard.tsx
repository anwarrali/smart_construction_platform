import { useTranslation } from "react-i18next";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useRole } from "../../hooks/useRole";
import { usePermissionStore } from "../store/permission.store";
import { projectModulePath } from "../../utils/projectRoutes";

interface PermissionGuardProps {
  /** Catalogue codes from the backend, e.g. `org.manage_roles`. */
  permissions: string[];
  /** When true, every code is required rather than any one of them. */
  requireAll?: boolean;
  redirectTo?: string;
}

/**
 * Route access decided by permission rather than by role name.
 *
 * `RoleGuard` asks "are you one of these five roles", which stopped being a
 * question the platform can answer once an office started creating its own.
 * This asks what the backend asks: do you hold the permission the page needs.
 *
 * `RoleGuard` is still used for the routes whose backend gate is genuinely a
 * role-shaped one — it has not been deleted, because deleting it would have
 * meant guessing a permission for every route in one pass. New routes, and any
 * route whose endpoint checks a catalogue code, use this.
 *
 * While permissions are still loading the guard renders the route rather than
 * redirecting. A guard is presentation: every endpoint behind it re-checks on
 * the server, and bouncing somebody to the dashboard for a few hundred
 * milliseconds because an answer had not arrived is a worse failure than
 * briefly showing a page whose data will simply come back empty.
 */
export const PermissionGuard = ({
  permissions,
  requireAll = false,
  redirectTo,
}: PermissionGuardProps) => {
  const { t } = useTranslation();
  const { hasCapability, permissionsReady } = useRole();
  const { pathname } = useLocation();
  // The open project, read from the one workspace address — `/projects/:id`
  // or `/projects/:id/…`. Requiring the trailing slash missed `/projects/:id`
  // itself (the Projects page's "Open"), so a refusal there fell back to the
  // portfolio dashboard instead of the project (QA 2026-10-22).
  const projectId = pathname.match(/^\/projects\/([^/]+)(?:\/|$)/)?.[1];
  const loadedProjectId = usePermissionStore((state) => state.project?.id);

  /* Inside a project, decide on that project's answer, never the office-wide
     one — and never render the page before it: doing so let the page fire
     requests the server then refused (the 403s on the overview), before the
     redirect caught up. Checked ahead of the office-wide "still loading"
     shortcut below, which on a fresh page load rendered the page anyway.
     Keyed on the URL rather than the store's active project, because the
     page's own effects run before the workspace provider's. The store falls
     back to the office-wide answer if the project's cannot be loaded, so
     this always ends. */
  if (projectId && (!permissionsReady || loadedProjectId !== decodeURIComponent(projectId))) {
    return <div className="p-8 text-center text-sm text-muted-foreground" role="status">{t("common.loading")}</div>;
  }
  if (!permissionsReady) return <Outlet />;

  const allowed = requireAll
    ? permissions.every((code) => hasCapability(code))
    : permissions.some((code) => hasCapability(code));

  if (!allowed) {
    /* Inside a project, to the first page of it this person can open — for an
       administrator who is not on the team that is the team page (QA-06B) —
       rather than out to the portfolio. `projectModulePath` only ever returns
       a module that passes its own check, or the overview when none does. */
    const fallback = projectId
      ? projectModulePath(projectId, "", hasCapability)
      : "/dashboard";
    const target = redirectTo ?? fallback;
    // Never redirect to the page being refused: with nothing openable in the
    // project, the portfolio.
    return <Navigate to={target === pathname ? "/projects" : target} replace />;
  }

  return <Outlet />;
};

export default PermissionGuard;
