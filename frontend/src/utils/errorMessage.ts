import i18n from "../i18n";

/**
 * Turn any thrown request failure into a string that is safe to render.
 *
 * FastAPI does not return one shape. A raised `HTTPException` gives
 * `detail: "text"`, a validation failure gives `detail: [{ loc, msg, type }]`,
 * and some endpoints raise a structured detail such as
 * `{ message, conflicts }`. Callers used to pass `response.data.detail`
 * straight into `toast.error(...)` or into JSX, so the array and object shapes
 * crashed the render with "Objects are not valid as a React child" and took the
 * whole page down with them.
 *
 * Everything funnels through here so a failed request always produces a
 * sentence, never a crash. Three things are added on top of the server's text:
 *
 * - a validation error names the field it is about;
 * - an authorization refusal says so, so it is not mistaken for bad input;
 * - a server-side failure carries its support ID, so it can be found in the
 *   log (the server never returns the technical detail itself).
 */

type FailedRequest = {
  response?: {
    status?: number;
    data?: { detail?: unknown };
    headers?: Record<string, unknown>;
  };
};

/** `["body", "planned_end_date"]` → "Planned end date". */
const fieldLabel = (loc: unknown): string | undefined => {
  if (!Array.isArray(loc)) return undefined;
  const field = [...loc].reverse().find((part) => typeof part === "string" && !["body", "query", "path"].includes(part));
  if (typeof field !== "string") return undefined;
  const words = field.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/_/g, " ").trim().toLowerCase();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : undefined;
};

const supportIdOf = (error: FailedRequest): string | undefined => {
  const detail = error.response?.data?.detail as Record<string, unknown> | undefined;
  const fromBody = detail && typeof detail === "object" && !Array.isArray(detail)
    ? (detail.supportId ?? detail.supportLogId)
    : undefined;
  if (typeof fromBody === "string" && fromBody) return fromBody;
  // Only a server-side failure is worth quoting; a 400 already says what to fix.
  const status = error.response?.status ?? 0;
  const header = error.response?.headers?.["x-request-id"];
  return status >= 500 && typeof header === "string" && header ? header : undefined;
};

export const errorMessage = (error: unknown, fallback?: string): string => {
  const fallbackText = fallback ?? i18n.t("errors.generic");
  const failed = (error ?? {}) as FailedRequest;
  const detail = failed.response?.data?.detail;
  const status = failed.response?.status;

  const fromValue = (value: unknown): string | undefined => {
    if (typeof value === "string") return value.trim() || undefined;
    if (Array.isArray(value)) {
      // Pydantic validation errors: the readable part of each entry, with the
      // field it concerns.
      const parts = value
        .map((item) => {
          if (typeof item === "string") return item;
          const entry = item as { msg?: string; loc?: unknown };
          if (!entry?.msg) return undefined;
          const text = entry.msg.replace(/^Value error,\s*/i, "");
          const field = fieldLabel(entry.loc);
          return field ? `${field}: ${text}` : text;
        })
        .filter((item): item is string => Boolean(item));
      return parts.length ? parts.join(". ") : undefined;
    }
    if (value && typeof value === "object") {
      const record = value as Record<string, unknown>;
      for (const key of ["message", "description", "title", "detail", "error"]) {
        const nested = fromValue(record[key]);
        if (nested) return nested;
      }
    }
    return undefined;
  };

  let message =
    fromValue(detail)
    ?? fromValue(failed.response?.data)
    // A network failure never reaches the server, so there is no detail at all.
    ?? (error instanceof Error && error.message ? error.message : undefined)
    ?? fallbackText;

  if (status === 403) {
    const prefix = i18n.t("errors.notPermittedPrefix");
    if (!message.startsWith(prefix)) message = `${prefix} ${message}`;
  }
  const supportId = supportIdOf(failed);
  if (supportId) message = `${message} (${i18n.t("errors.supportId", { id: supportId })})`;
  return message;
};

export default errorMessage;
