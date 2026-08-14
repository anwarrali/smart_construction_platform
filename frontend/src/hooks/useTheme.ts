import { useThemeStore } from "../app/store/theme.store";

export const useTheme = () => {
  const { theme, preference, dir, toggleTheme, setTheme, setPreference, setDir } = useThemeStore();

  const isDark = theme === "dark";
  const isRTL = dir === "rtl";

  return {
    theme,
    preference,
    dir,
    isDark,
    isRTL,
    toggleTheme,
    setTheme,
    setPreference,
    setDir,
  };
};
