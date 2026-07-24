import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "../store/auth.store";

export const ConsultantEngineerGuard = () => {
  const user = useAuthStore((state) => state.user);
  const location = useLocation();
  if (!user) return <Navigate to="/auth/login" state={{ from: location }} replace />;
  if (user.role !== "engineer" || user.engineerAffiliation !== "external_consultant" || user.status !== "active") {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
};
