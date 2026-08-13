import { useTranslation } from "react-i18next";
import { Languages } from "lucide-react";

import { SUPPORTED_LANGUAGES } from "../../i18n";

/**
 * Language toggle. Deliberately reuses the Topbar's existing icon-button
 * classes so it sits in the header as a native control rather than introducing
 * a new visual style.
 */
export const LanguageSwitcher = ({ className = "" }: { className?: string }) => {
  const { t, i18n } = useTranslation();
  const current = i18n.resolvedLanguage || i18n.language || "en";
  const next = SUPPORTED_LANGUAGES.find((item) => item.code !== current) || SUPPORTED_LANGUAGES[0];

  return (
    <button
      type="button"
      onClick={() => void i18n.changeLanguage(next.code)}
      aria-label={t("common.switchTo", { language: next.nativeLabel })}
      title={t("common.switchTo", { language: next.nativeLabel })}
      className={`inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-md px-2 text-foreground/70 transition-colors hover:bg-muted hover:text-foreground cursor-pointer border-none outline-none ${className}`}
      style={{ background: "none" }}
    >
      <Languages size={18} />
      <span className="text-xs font-semibold uppercase">{next.code}</span>
    </button>
  );
};

export default LanguageSwitcher;
