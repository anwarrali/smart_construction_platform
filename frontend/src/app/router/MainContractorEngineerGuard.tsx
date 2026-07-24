import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "../store/auth.store";
import { ROUTES } from "../../utils/constants";

export const MainContractorEngineerGuard = () => {
  const user = useAuthStore((state) => state.user);
  const location = useLocation();

  if (!user) return <Navigate to={ROUTES.LOGIN} replace state={{ from: location }} />;
  if (
    user.role !== "engineer"
    || user.engineerAffiliation !== "main_contractor"
    || user.status !== "active"
  ) {
    return <Navigate to={ROUTES.NOT_FOUND} replace />;
  }
  return <Outlet />;
};
