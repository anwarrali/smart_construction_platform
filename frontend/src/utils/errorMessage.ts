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
 * sentence, never a crash.
 */
export const errorMessage = (error: unknown, fallback?: string): string => {
  const fallbackText = fallback ?? i18n.t("errors.generic");
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;

  const fromValue = (value: unknown): string | undefined => {
    if (typeof value === "string") return value.trim() || undefined;
    if (Array.isArray(value)) {
      // Pydantic validation errors: keep the human-readable part of each entry.
      const parts = value
        .map((item) => (typeof item === "string" ? item : (item as { msg?: string })?.msg))
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

  return (
    fromValue(detail)
    ?? fromValue((error as { response?: { data?: unknown } })?.response?.data)
    // A network failure never reaches the server, so there is no detail at all.
    ?? (error instanceof Error && error.message ? error.message : undefined)
    ?? fallbackText
  );
};

export default errorMessage;
