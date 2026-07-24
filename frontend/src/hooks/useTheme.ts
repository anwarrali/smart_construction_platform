import { useThemeStore } from "../app/store/theme.store";

export const useTheme = () => {
  const { theme, dir, toggleTheme, setTheme, setDir } = useThemeStore();

  const isDark = theme === "dark";
  const isRTL = dir === "rtl";

  return {
    theme,
    dir,
    isDark,
    isRTL,
    toggleTheme,
    setTheme,
    setDir,
  };
};
