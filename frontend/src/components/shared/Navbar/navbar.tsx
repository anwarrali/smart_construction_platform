import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Menu, X } from "lucide-react";

import { Button } from "../../ui/Button";
import { LanguageSwitcher } from "../LanguageSwitcher";
import { ThemeSwitcher } from "../ThemeSwitcher";
import { ROUTES } from "../../../utils/constants";
import { StructIQLogo } from "../../brand/StructIQLogo";

/** Anchors into the landing page; the labels come from the catalogue. */
const NAV_LINKS = [
  { to: ROUTES.HOME, labelKey: "landing.nav.home" },
  { to: "#architecture", labelKey: "landing.nav.architecture" },
  { to: "#workflow", labelKey: "landing.nav.workflow" },
  { to: "#mobile-ai", labelKey: "landing.nav.mobileAi" },
  { to: "#example", labelKey: "landing.nav.example" },
];

export const Navbar = () => {
  const { t } = useTranslation();
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const location = useLocation();

  const isActive = (path: string) => {
    if (path.startsWith("#")) return false;
    return location.pathname === path;
  };

  return (
    <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-16 items-center justify-between gap-3 px-4">
        <Link to={ROUTES.HOME} aria-label={t("landing.nav.homeAria")}>
          <StructIQLogo variant="compact" size={30} />
        </Link>

        <nav className="hidden items-center gap-6 md:flex">
          {NAV_LINKS.map((link) => (
            <a
              key={link.to}
              href={link.to}
              className={`text-sm font-medium transition-colors hover:text-primary ${
                isActive(link.to) ? "text-primary" : "text-muted-foreground"
              }`}
            >
              {t(link.labelKey)}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3">
          <LanguageSwitcher />
          {/* The same Light / Dark / System control the application uses. */}
          <ThemeSwitcher compact />

          <div className="hidden items-center gap-2 md:flex">
            <Link to={ROUTES.LOGIN}>
              <Button size="sm">{t("landing.nav.signIn")}</Button>
            </Link>
          </div>

          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label={isMobileOpen ? t("nav.closeMenu") : t("nav.openMenu")}
            onClick={() => setIsMobileOpen(!isMobileOpen)}
          >
            {isMobileOpen ? <X size={18} /> : <Menu size={18} />}
          </Button>
        </div>
      </div>

      {isMobileOpen && (
        <div className="space-y-3 border-t bg-background p-4 md:hidden">
          {NAV_LINKS.map((link) => (
            <a
              key={link.to}
              href={link.to}
              className="block py-2 text-sm font-medium text-muted-foreground hover:text-primary"
              onClick={() => setIsMobileOpen(false)}
            >
              {t(link.labelKey)}
            </a>
          ))}
          <div className="space-y-2 border-t pt-3">
            <Link to={ROUTES.LOGIN} onClick={() => setIsMobileOpen(false)}>
              <Button fullWidth size="sm">{t("landing.nav.signIn")}</Button>
            </Link>
          </div>
        </div>
      )}
    </header>
  );
};
