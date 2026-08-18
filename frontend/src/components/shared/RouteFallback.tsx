import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

/**
 * Shown while a route-level `React.lazy` chunk is still downloading. Sits
 * inside each layout's `<Outlet/>`, not around the whole router, so the
 * Sidebar/Topbar/navigation chrome around it stays mounted and does not
 * flicker away during a route-to-route navigation — only the content area
 * shows this, matching the loading style already used across the app
 * (see e.g. AdminDashboard's own `Loader2` + `animate-spin` loading state).
 */
export const RouteFallback = () => {
  const { t } = useTranslation();
  return (
    <div className="flex h-64 items-center justify-center text-muted-foreground">
      <Loader2 className="mr-2 h-5 w-5 animate-spin" />
      {t("common.loading")}
    </div>
  );
};
