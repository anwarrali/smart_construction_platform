import { create } from "zustand";
import { LANGUAGE_STORAGE_KEY, directionOf } from "../../i18n";

type Theme = "light" | "dark";
type Dir = "ltr" | "rtl";

interface ThemeState {
  theme: Theme;
  dir: Dir;

  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
  setDir: (dir: Dir) => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: (() => {
    const stored = localStorage.getItem("scp_theme") as Theme | null;
    if (stored) return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  })(),
  // Direction is a property of the chosen language, not of the theme. Deriving
  // it from the stored language stops a stale "scp_dir" value from overwriting
  // the direction i18n already applied to the document.
  dir: directionOf(localStorage.getItem(LANGUAGE_STORAGE_KEY) || "en"),

  toggleTheme: () =>
    set((state) => {
      const newTheme = state.theme === "light" ? "dark" : "light";
      localStorage.setItem("scp_theme", newTheme);
      document.documentElement.classList.remove("light", "dark");
      document.documentElement.classList.add(newTheme);
      return { theme: newTheme };
    }),

  setTheme: (theme) => {
    localStorage.setItem("scp_theme", theme);
    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(theme);
    set({ theme });
  },

  setDir: (dir) => {
    localStorage.setItem("scp_dir", dir);
    document.documentElement.dir = dir;
    set({ dir });
  },
}));
