import { Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { EngineeringBackdrop } from "../components/shared/EngineeringBackdrop";
import { LanguageSwitcher } from "../components/shared/LanguageSwitcher";

/**
 * Full-screen authentication ground.
 *
 * Deliberately not a split screen: the only thing asked of someone here is to
 * sign in, so the page gives that one task the centre of the sheet and puts
 * everything else — language, legal line — at the margins where a title block
 * would sit.
 */
export const AuthLayout = () => {
  const { t } = useTranslation();
  return (
    <div className="relative flex min-h-screen flex-col bg-background">
      <EngineeringBackdrop />

      <header className="relative flex items-center justify-end px-5 py-4 md:px-8">
        <LanguageSwitcher />
      </header>

      <main className="relative flex flex-1 items-center justify-center px-5 pb-16">
        <div className="w-full max-w-[26rem]">
          <Outlet />
        </div>
      </main>

      <footer className="relative px-5 pb-6 text-center md:px-8">
        <p className="text-[11px] text-muted-foreground/70">
          © {new Date().getFullYear()} {t("brand.copyright")}
        </p>
      </footer>
    </div>
  );
};
