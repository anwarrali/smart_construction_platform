import { create } from "zustand";
import { LANGUAGE_STORAGE_KEY, directionOf } from "../../i18n";

type Theme = "light" | "dark";
/** What the user asked for. "system" defers to the operating system. */
export type ThemePreference = Theme | "system";
type Dir = "ltr" | "rtl";

const PREFERENCE_KEY = "scp_theme_preference";
const LEGACY_KEY = "scp_theme";

const systemTheme = (): Theme =>
  window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";

const resolve = (preference: ThemePreference): Theme =>
  preference === "system" ? systemTheme() : preference;

const applyTheme = (theme: Theme) => {
  document.documentElement.classList.remove("light", "dark");
  document.documentElement.classList.add(theme);
};

/**
 * Reads the stored preference, migrating the older `scp_theme` key that only
 * ever held a resolved light/dark value. An explicit older choice stays
 * explicit; only a first-time visitor defaults to following the system.
 */
const storedPreference = (): ThemePreference => {
  const stored = localStorage.getItem(PREFERENCE_KEY) as ThemePreference | null;
  if (stored === "light" || stored === "dark" || stored === "system") return stored;
  const legacy = localStorage.getItem(LEGACY_KEY) as Theme | null;
  return legacy === "light" || legacy === "dark" ? legacy : "system";
};

interface ThemeState {
  /** The theme actually being displayed. */
  theme: Theme;
  /** The user's choice, which may be "system". */
  preference: ThemePreference;
  dir: Dir;

  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
  setPreference: (preference: ThemePreference) => void;
  setDir: (dir: Dir) => void;
}

export const useThemeStore = create<ThemeState>((set, get) => {
  const initialPreference = storedPreference();

  // While the preference is "system", the OS switching between light and dark
  // must move the app with it rather than freezing at whatever it was on load.
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (get().preference !== "system") return;
    const theme = systemTheme();
    applyTheme(theme);
    set({ theme });
  });

  return {
    theme: resolve(initialPreference),
    preference: initialPreference,
    // Direction is a property of the chosen language, not of the theme. Deriving
    // it from the stored language stops a stale "scp_dir" value from overwriting
    // the direction i18n already applied to the document.
    dir: directionOf(localStorage.getItem(LANGUAGE_STORAGE_KEY) || "en"),

    setPreference: (preference) => {
      localStorage.setItem(PREFERENCE_KEY, preference);
      const theme = resolve(preference);
      applyTheme(theme);
      set({ preference, theme });
    },

    // Kept so existing callers keep working; an explicit theme is an explicit
    // preference, which stops following the system.
    setTheme: (theme) => get().setPreference(theme),

    toggleTheme: () => get().setPreference(get().theme === "light" ? "dark" : "light"),

    setDir: (dir) => {
      localStorage.setItem("scp_dir", dir);
      document.documentElement.dir = dir;
      set({ dir });
    },
  };
});
