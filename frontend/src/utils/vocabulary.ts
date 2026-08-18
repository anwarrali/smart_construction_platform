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

export const useVocabulary = () => {
  const { t } = useTranslation();

  const lookup = (namespace: string, value: unknown, lowercase = true): string => {
    if (value === null || value === undefined || value === "") return "";
    const raw = String(value);
    const key = lowercase ? raw.toLowerCase() : raw;
    return t(`${namespace}.${key}`, { defaultValue: humanize(raw) });
  };

  return {
    /** Platform role: admin, project_manager, engineer, consultant, owner, worker. */
    role: (value: unknown) => lookup("roles", value),
    /** Role held on one project; the same vocabulary as platform roles. */
    projectRole: (value: unknown) => lookup("roles", value),
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
