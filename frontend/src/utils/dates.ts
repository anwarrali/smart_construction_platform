import i18n from "../i18n";

/**
 * Date and time formatting that follows the language the user selected.
 *
 * The pages previously called `toLocaleDateString()` with no locale, which uses
 * the *browser's* locale. An Arabic reader on an English-configured machine
 * therefore saw "Aug 14" in the middle of an otherwise Arabic page. Routing
 * every call through here ties the format to the application's own language.
 *
 * These are module functions rather than a hook so they can be used from
 * helpers and column definitions that are not React components. Components
 * re-render when the language changes, so the output refreshes with them.
 */
const locale = () => i18n.resolvedLanguage || i18n.language || "en";

const parse = (value: string | number | Date | null | undefined): Date | null => {
  if (value === null || value === undefined || value === "") return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};

/** 14 Aug 2026 */
export const formatDate = (value: string | number | Date | null | undefined, fallback = "—") => {
  const date = parse(value);
  return date ? date.toLocaleDateString(locale(), { day: "numeric", month: "short", year: "numeric" }) : fallback;
};

/** 14 Aug 2026, 09:00 */
export const formatDateTime = (value: string | number | Date | null | undefined, fallback = "—") => {
  const date = parse(value);
  return date
    ? date.toLocaleString(locale(), { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : fallback;
};

/** 09:00 */
export const formatTime = (value: string | number | Date | null | undefined, fallback = "—") => {
  const date = parse(value);
  return date ? date.toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" }) : fallback;
};

/** 14 Aug — no year, for dense lists. */
export const formatDayMonth = (value: string | number | Date | null | undefined, fallback = "—") => {
  const date = parse(value);
  return date ? date.toLocaleDateString(locale(), { day: "numeric", month: "short" }) : fallback;
};

export default formatDate;
