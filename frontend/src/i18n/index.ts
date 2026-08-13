import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import en from "./locales/en/translation.json";
import ar from "./locales/ar/translation.json";

export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English", nativeLabel: "English", dir: "ltr" as const },
  { code: "ar", label: "Arabic", nativeLabel: "العربية", dir: "rtl" as const },
];

export const LANGUAGE_STORAGE_KEY = "scp_language";

/**
 * Direction for a language tag. Region subtags are ignored, so a browser
 * reporting "ar-SA" or "ar-EG" still reads right-to-left.
 */
export const directionOf = (language: string): "ltr" | "rtl" => {
  const base = String(language || "").toLowerCase().split(/[-_]/)[0];
  return SUPPORTED_LANGUAGES.find((item) => item.code === base)?.dir ?? "ltr";
};

/**
 * Apply the language to the document itself. `dir` drives every direction-aware
 * behaviour the browser gives us for free (flex order, text alignment, caret
 * movement, scrollbars), and `lang` drives font selection and screen readers.
 */
export const applyDocumentLanguage = (language: string) => {
  // Guarded so the module can be imported outside a browser (tests, SSR).
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.lang = language;
  root.dir = directionOf(language);
};

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      ar: { translation: ar },
    },
    supportedLngs: SUPPORTED_LANGUAGES.map((item) => item.code),
    fallbackLng: "en",
    // Treat "en-GB" and friends as "en" rather than falling back to the default.
    load: "languageOnly",
    nonExplicitSupportedLngs: true,
    detection: {
      order: ["localStorage", "navigator", "htmlTag"],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      caches: ["localStorage"],
    },
    interpolation: {
      // React already escapes interpolated values.
      escapeValue: false,
    },
    returnEmptyString: false,
  });

// Keep the document in step with the active language, including the very first
// render and any later switch.
applyDocumentLanguage(i18n.resolvedLanguage || i18n.language || "en");
i18n.on("languageChanged", applyDocumentLanguage);

export default i18n;
