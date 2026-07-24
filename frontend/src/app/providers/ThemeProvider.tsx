import { useEffect, type ReactNode } from "react";
import { useThemeStore } from "../store/theme.store";

export const ThemeProvider = ({ children }: { children: ReactNode }) => {
  const { theme, dir } = useThemeStore();

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.dir = dir;
  }, [dir]);

  return <>{children}</>;
};
