import { useCallback, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Sidebar } from "../components/shared/Sidebar/Sidebar";
import { Topbar } from "../components/shared/Topbar/Topbar";
import { ProjectWorkspaceProvider } from "../features/projects/context/ProjectWorkspaceContext";
import { Breadcrumbs } from "../components/shared/Breadcrumbs/Breadcrumbs";
import { useDirection } from "../hooks/useDirection";

export const DashboardLayout = () => {
  // Keeps the direction store in step with the active language. The document
  // attributes are already set during i18n init, so nothing shifts on load.
  useDirection();
  const { t } = useTranslation();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
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
        {/* Permanent rail from `lg` up — the desktop experience is unchanged. */}
        <Sidebar className="hidden lg:flex" />

        {/* Below `lg` the same navigation opens over the page instead of
            permanently occupying two thirds of a phone screen. */}
        {menuOpen && (
          <div className="fixed inset-0 z-50 flex lg:hidden" role="dialog" aria-modal="true" aria-label={t("nav.menu")}>
            <button type="button" aria-label={t("nav.closeMenu")} onClick={closeMenu}
              className="absolute inset-0 h-full w-full cursor-default bg-black/50" />
            <Sidebar className="relative z-10 shadow-2xl" onNavigate={closeMenu} />
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <Topbar onOpenMenu={() => setMenuOpen(true)} />
          {/* The working sheet: content sits on the paper ground with its own
              margin, rather than inside yet another tinted container. */}
          <main className="flex-1 overflow-y-auto bg-background">
            <div className="page-container">
              <Breadcrumbs />
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </ProjectWorkspaceProvider>
  );
};
