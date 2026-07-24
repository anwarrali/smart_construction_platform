import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useThemeStore } from "../app/store/theme.store";

export const useDirection = () => {
  const { i18n } = useTranslation();
  const setDir = useThemeStore((state) => state.setDir);

  useEffect(() => {
    const dir = i18n.language === "ar" ? "rtl" : "ltr";
    setDir(dir);
  }, [i18n.language, setDir]);

  const isRTL = i18n.language === "ar";

  return { isRTL, dir: isRTL ? "rtl" : "ltr" };
};
