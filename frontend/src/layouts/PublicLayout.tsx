import { Suspense } from "react";
import { Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Navbar } from "../components/shared/Navbar";
import { StructIQLogo } from "../components/brand/StructIQLogo";
import { RouteFallback } from "../components/shared/RouteFallback";

export const PublicLayout = () => {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main>
        <Suspense fallback={<RouteFallback />}>
          <Outlet />
        </Suspense>
      </main>
      <footer className="border-t py-8">
        <div className="container mx-auto flex flex-col items-center gap-3 px-4 text-center">
          <StructIQLogo variant="full" size={26} />
          <p className="text-sm text-muted-foreground">
            &copy; {t("landing.footer.rights", { year: new Date().getFullYear() })}
          </p>
        </div>
      </footer>
    </div>
  );
};
