import i18next from "i18next";
import { useTranslation } from "react-i18next";

/**
 * Translates the controlled vocabulary the API returns.
 *
 * Values such as `project_manager`, `in_progress` or `critical` are system
 * concepts, not user-written text, so rendering them straight from the response
 * left English words inside an Arabic page. Everything here maps an enum value
 * onto the catalogue and falls back to a humanized form when a value is new, so
 * an unmapped status degrades to "In progress" rather than disappearing.
 *
 * This is deliberately *not* used for user-generated content — project names,
 * notes, messages and uploaded file names are shown exactly as entered.
 */
const humanize = (value: string) =>
  value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

/** An office role as the API returns it on a user. */
type RoleName = { nameEn: string; nameAr?: string | null } | null | undefined;

/** An office role's name in the current language. Roles are office data, not vocabulary. */
export const orgRoleName = (role: RoleName, language: string = i18next.language || "en"): string =>
  role ? (language.startsWith("ar") ? role.nameAr || role.nameEn : role.nameEn) : "";

export const useVocabulary = () => {
  const { t, i18n } = useTranslation();
  const arabic = (i18n.resolvedLanguage || i18n.language || "en").startsWith("ar");

  const lookup = (namespace: string, value: unknown, lowercase = true): string => {
    if (value === null || value === undefined || value === "") return "";
    const raw = String(value);
    const key = lowercase ? raw.toLowerCase() : raw;
    return t(`${namespace}.${key}`, { defaultValue: humanize(raw) });
  };

  return {
    /** An office role's name, in the reader's language. Roles are office data, not vocabulary. */
    orgRole: (role: RoleName) => orgRoleName(role, arabic ? "ar" : "en"),
    taskStatus: (value: unknown) => lookup("task.status", value),
    priority: (value: unknown) => lookup("task.priority", value),
    projectStatus: (value: unknown) => lookup("project.status", value),
    projectHealth: (value: unknown) => lookup("project.health", value),
    issueStatus: (value: unknown) => lookup("issue.status", value),
    issueCategory: (value: unknown) => lookup("issue.category", value),
    severity: (value: unknown) => lookup("issue.severityLevel", value),
    discipline: (value: unknown) => lookup("discipline", value),
    reviewStatus: (value: unknown) => lookup("review.status", value),
    designChangeStatus: (value: unknown) => lookup("designChange.status", value),
    siteVisitType: (value: unknown) => lookup("siteVisit.type", value, false),
    milestoneStatus: (value: unknown) => lookup("milestone.status", value),
    /** Anything else that is system vocabulary without a dedicated namespace. */
    term: (value: unknown) => (value ? humanize(String(value)) : ""),
  };
};

export default useVocabulary;
