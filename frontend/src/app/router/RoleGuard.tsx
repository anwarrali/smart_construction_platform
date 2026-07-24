import { Navigate, Outlet } from "react-router-dom";
import { useRole } from "../../hooks/useRole";
import type { UserRole } from "../../types/auth";

interface RoleGuardProps {
  allowedRoles: UserRole[];
  redirectTo?: string;
}

export const RoleGuard = ({
  allowedRoles,
  redirectTo = "/dashboard",
}: RoleGuardProps) => {
  const { role } = useRole();

  if (!role || !allowedRoles.includes(role)) {
    return <Navigate to={redirectTo} replace />;
  }

  return <Outlet />;
};
