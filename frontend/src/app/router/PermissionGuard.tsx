import { Navigate, Outlet } from "react-router-dom";
import { useRole } from "../../hooks/useRole";

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
  redirectTo = "/dashboard",
}: PermissionGuardProps) => {
  const { hasCapability, permissionsReady } = useRole();

  if (!permissionsReady) return <Outlet />;

  const allowed = requireAll
    ? permissions.every((code) => hasCapability(code))
    : permissions.some((code) => hasCapability(code));

  if (!allowed) return <Navigate to={redirectTo} replace />;

  return <Outlet />;
};

export default PermissionGuard;
