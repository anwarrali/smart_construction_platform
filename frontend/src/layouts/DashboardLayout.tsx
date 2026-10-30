import { Suspense, useCallback, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Sidebar } from "../components/shared/Sidebar/Sidebar";
import { Topbar } from "../components/shared/Topbar/Topbar";
import { ProjectWorkspaceProvider } from "../features/projects/context/ProjectWorkspaceContext";
import { RouteFallback } from "../components/shared/RouteFallback";
import { useDirection } from "../hooks/useDirection";
import { useLayoutStore } from "../app/store/layout.store";

export const DashboardLayout = () => {
  // Keeps the direction store in step with the active language. The document
  // attributes are already set during i18n init, so nothing shifts on load.
  useDirection();
  const { t } = useTranslation();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const railCollapsed = useLayoutStore((state) => state.railCollapsed);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  // A drawer left open across a navigation would cover the page it opened.
  useEffect(closeMenu, [location.pathname, closeMenu]);

  // Escape is the expected way out of an overlay, and the page behind it must
  // not scroll while the drawer has the screen.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") closeMenu(); };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [menuOpen, closeMenu]);

  return (
    <ProjectWorkspaceProvider>
      <div className="flex h-screen overflow-hidden">
        <a href="#main-content" className="sr-only z-[60] bg-primary px-3 py-2 text-sm text-primary-foreground focus:not-sr-only focus:fixed focus:start-2 focus:top-2">
          {t("nav.skipToContent")}
        </a>
        {/* Permanent rail from `lg` up, optionally narrowed to icons. */}
        <Sidebar className="hidden lg:flex" collapsed={railCollapsed} />

        {/* Below `lg` the same navigation opens over the page instead of
            permanently occupying two thirds of a phone screen. */}
        {menuOpen && (
          <div className="fixed inset-0 z-50 flex lg:hidden" role="dialog" aria-modal="true" aria-label={t("nav.menu")}>
            <button type="button" aria-label={t("nav.closeMenu")} onClick={closeMenu}
              className="absolute inset-0 h-full w-full cursor-default border-none bg-black/55" />
            <Sidebar className="relative z-10" onNavigate={closeMenu} />
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <Topbar onOpenMenu={() => setMenuOpen(true)} />
          {/* The working sheet. Location now lives in the top bar, so the page
              starts with its own title. */}
          <main id="main-content" className="flex-1 overflow-y-auto bg-background">
            <div className="page-container">
              {/* Only the routed page itself lazy-loads; this boundary is scoped
                  to the Outlet alone so the Sidebar/Topbar above never unmount
                  or flicker while a route's chunk is still downloading. */}
              <Suspense fallback={<RouteFallback />}>
                <Outlet />
              </Suspense>
            </div>
          </main>
        </div>
      </div>
    </ProjectWorkspaceProvider>
  );
};
