import { useTranslation } from "react-i18next";
import { Monitor, Moon, Sun } from "lucide-react";

import { useTheme } from "../../hooks/useTheme";
import type { ThemePreference } from "../../app/store/theme.store";

const OPTIONS: { value: ThemePreference; icon: typeof Sun; labelKey: string }[] = [
  { value: "light", icon: Sun, labelKey: "theme.light" },
  { value: "dark", icon: Moon, labelKey: "theme.dark" },
  { value: "system", icon: Monitor, labelKey: "theme.system" },
];

/**
 * The single Light / Dark / System control, used by both the landing page and
 * the authenticated shell so the two never drift apart. It is a segmented pill
 * rather than a lone moon/sun button because "follow the system" is a third
 * state that a two-way toggle cannot express.
 *
 * `compact` drops the text labels and keeps the icons, for the dense header.
 */
export const ThemeSwitcher = ({ compact = false, className = "" }: { compact?: boolean; className?: string }) => {
  const { t } = useTranslation();
  const { preference, setPreference } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label={t("theme.label")}
      className={`inline-flex shrink-0 items-center gap-0.5 rounded-control border bg-muted/50 p-0.5 ${className}`}
    >
      {OPTIONS.map(({ value, icon: Icon, labelKey }) => {
        const active = preference === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={t(labelKey)}
            title={t(labelKey)}
            onClick={() => setPreference(value)}
            className={`inline-flex h-7 cursor-pointer items-center justify-center gap-1.5 rounded-[calc(var(--radius-control)-2px)] border-none px-2 text-xs font-medium outline-none transition-colors ${
              active
                ? "bg-card text-foreground shadow-sm"
                : "bg-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icon size={14} />
            {!compact && <span className="hidden sm:inline">{t(labelKey)}</span>}
          </button>
        );
      })}
    </div>
  );
};

export default ThemeSwitcher;
