// @vitest-environment jsdom
/**
 * Which module the breadcrumb thinks you are looking at.
 *
 * This shipped wrong on every project page and nothing caught it, because the
 * failure is quiet: the trail still renders, it just names the wrong thing.
 * `base` was built from `workspace.path("")`, which cannot return a bare base
 * and is not meant to — an empty module resolves to the `dashboard` fallback,
 * so `base` was ten characters (`/dashboard`) too long. Slicing the pathname
 * by that length ate the module name:
 *
 *   * a name shorter than "/dashboard" sliced away to nothing and fell through
 *     to `"dashboard"` — the Tasks page announced itself as Project overview;
 *   * a longer one left a tail — `/site-visits` displayed as "ts".
 *
 * The cases below are that arithmetic's whole failure surface: shorter than
 * the fallback, exactly its length, and longer.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

const location = { pathname: "/" };
vi.mock("react-router-dom", () => ({
  useLocation: () => location,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

const PROJECT = "3563ff46-fb97-47b7-a5ae-2eeb8bafbe34";
const workspace = {
  isProjectWorkspace: true,
  projectId: PROJECT as string | undefined,
  project: { name: "Residential Complex C" },
  portfolioPath: "/projects",
  // Exactly what the real one does: an empty module is resolved to the
  // fallback, which is what made length arithmetic against it wrong.
  path: (module: string) => `/projects/${PROJECT}/${module || "dashboard"}`,
};
vi.mock("../../../features/projects/context/ProjectWorkspaceContext", () => ({
  useProjectWorkspace: () => workspace,
}));

const translate = (key: string) => key;
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: translate }) }));

const { Breadcrumbs } = await import("./Breadcrumbs");

const at = (pathname: string) => {
  location.pathname = pathname;
  render(<Breadcrumbs />);
  const nav = screen.getByRole("navigation");
  // The module is the last non-empty line of the trail.
  return nav.textContent?.trim() ?? "";
};

afterEach(() => {
  cleanup();
  workspace.projectId = PROJECT;
  workspace.isProjectWorkspace = true;
});

describe("Breadcrumbs", () => {
  it("names a module longer than the fallback", () => {
    // Displayed as "ts" before the fix.
    expect(at(`/projects/${PROJECT}/site-visits`)).toContain("nav.siteVisits");
  });

  it("names a module shorter than the fallback", () => {
    // Displayed as Project overview before the fix.
    const trail = at(`/projects/${PROJECT}/tasks`);
    expect(trail).toContain("nav.tasks");
    expect(trail).not.toContain("nav.projectOverview");
  });

  it("names a module exactly the fallback's length", () => {
    expect(at(`/projects/${PROJECT}/milestones`)).toContain("task.milestone");
  });

  it("still names the dashboard on the dashboard", () => {
    expect(at(`/projects/${PROJECT}/dashboard`)).toContain("nav.projectOverview");
  });

  it("falls back to the dashboard at the workspace root", () => {
    expect(at(`/projects/${PROJECT}`)).toContain("nav.projectOverview");
  });

  it("shows the record id on a deep link", () => {
    // Unreachable before the fix: the second segment never survived the slice.
    expect(at(`/projects/${PROJECT}/tasks/abcd1234-5678`)).toContain("abcd1234-567");
  });

  it("survives a retired role-prefixed URL", () => {
    // This provider runs once on the pre-redirect pathname, where a base of
    // `/projects/:id` would not match the start of the path at all.
    expect(at(`/project-manager/projects/${PROJECT}/site-reports`))
      .toContain("nav.siteReports");
  });

  it("renders an unmapped module by its own name rather than a wrong one", () => {
    expect(at(`/projects/${PROJECT}/something-new`)).toContain("something new");
  });

  it("renders nothing outside a project workspace", () => {
    workspace.isProjectWorkspace = false;
    location.pathname = "/projects";
    const { container } = render(<Breadcrumbs />);
    expect(container).toBeEmptyDOMElement();
  });
});
