import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useThemeStore } from "../app/store/theme.store";
import { directionOf } from "../i18n";

/**
 * Keeps the theme store's `dir` in step with the active language.
 *
 * The document attributes themselves are set in `src/i18n/index.ts`, so
 * direction is correct on the very first paint even before React mounts.
 */
export const useDirection = () => {
  const { i18n } = useTranslation();
  const language = i18n.resolvedLanguage || i18n.language || "en";
  const dir = directionOf(language);
  const setDir = useThemeStore((state) => state.setDir);

  useEffect(() => {
    setDir(dir);
  }, [dir, setDir]);

  return { isRTL: dir === "rtl", dir, language };
};
