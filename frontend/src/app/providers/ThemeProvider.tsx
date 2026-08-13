import { useEffect, type ReactNode } from "react";
import { useThemeStore } from "../store/theme.store";
import { useDirection } from "../../hooks/useDirection";

export const ThemeProvider = ({ children }: { children: ReactNode }) => {
  // Runs app-wide so direction is correct on public and auth pages too, not
  // only inside the authenticated dashboard shell.
  useDirection();
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
