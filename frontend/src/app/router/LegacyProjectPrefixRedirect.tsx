import { Navigate, useLocation } from "react-router-dom";

/**
 * Keeps every URL the per-role prefixes ever produced working.
 *
 * The workspace used to live at four addresses — `/project-manager/projects/:id/…`,
 * `/engineer/projects/:id/…`, `/consultant-engineer/projects/:id/…` and
 * `/projects/:id/…` — selected by who you were rather than by what you were
 * looking at. They are one address now. That is only safe because these are
 * not new links: they are in push notifications already delivered, in e-mails,
 * in browser history and in whatever anybody bookmarked, and a 404 on any of
 * them is a regression regardless of how much cleaner the route table looks.
 *
 * So each retired prefix stays registered and redirects, preserving the module
 * path, the search string and the hash. `replace` is deliberate: the old URL
 * should not sit in history, because pressing Back would bounce through the
 * redirect again.
 *
 * Two module paths move rather than survive, because the same word meant a
 * different page depending on the prefix it hung off:
 *
 *  * `/engineer/projects/:id/dashboard` was the engineer's own work list,
 *    which is now `/projects/:id/my-work`;
 *  * `/consultant-engineer/projects/:id/dashboard` was the review queue, which
 *    is now `/projects/:id/review-queue`.
 *
 * Everything else keeps its module word exactly.
 */

/** Retired prefix → the module renames that prefix needs. */
const MODULE_RENAMES: Record<string, Record<string, string>> = {
  "/engineer/projects": { dashboard: "my-work" },
  "/consultant-engineer/projects": { dashboard: "review-queue" },
  "/project-manager/projects": {},
};

export const LEGACY_PROJECT_PREFIXES = Object.keys(MODULE_RENAMES);

/**
 * Rewrite one retired workspace URL onto the shared one.
 *
 * Exported and pure so it can be tested without a router: the deep-link
 * guarantee is the kind of thing that should fail in a unit test rather than
 * in somebody's notification.
 */
export const sharedWorkspaceUrl = (
  pathname: string,
  search = "",
  hash = "",
): string | null => {
  const prefix = LEGACY_PROJECT_PREFIXES.find(
    (candidate) => pathname === candidate || pathname.startsWith(`${candidate}/`),
  );
  if (!prefix) return null;

  const rest = pathname.slice(prefix.length).replace(/^\/+/, "");
  // `/engineer/projects` with no id is the portfolio list, which is `/projects`.
  if (!rest) return `/projects${search}${hash}`;

  const [projectId, module, ...tail] = rest.split("/");
  if (!module) return `/projects/${projectId}${search}${hash}`;

  const renamed = MODULE_RENAMES[prefix][module] || module;
  const segments = [projectId, renamed, ...tail].filter(Boolean);
  return `/projects/${segments.join("/")}${search}${hash}`;
};

export const LegacyProjectPrefixRedirect = () => {
  const location = useLocation();
  const target = sharedWorkspaceUrl(location.pathname, location.search, location.hash);
  return <Navigate to={target || "/projects"} replace />;
};

export default LegacyProjectPrefixRedirect;
