import { createContext } from "react";

type Theme = "light" | "dark";
type Dir = "ltr" | "rtl";

export interface ThemeContextType {
  theme: Theme;
  dir: Dir;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
  setDir: (dir: Dir) => void;
}

export const ThemeContext = createContext<ThemeContextType | undefined>(
  undefined,
);
