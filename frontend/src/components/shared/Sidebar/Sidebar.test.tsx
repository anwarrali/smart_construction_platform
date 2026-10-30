// @vitest-environment jsdom
/**
 * The rail as drawn: it shows what the person's permissions allow, marks the
 * current destination, and keeps every entry named when narrowed to icons.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

const PROJECT = "3563ff46-fb97-47b7-a5ae-2eeb8bafbe34";

let granted: string[] = [];
vi.mock("../../../hooks/useRole", () => ({
  useRole: () => ({
    permissionsReady: true,
    hasCapability: (code: string) => granted.includes(code),
    orgRoleLabel: "Contractor representative",
    isInternal: false,
  }),
}));

const workspace = {
  isProjectWorkspace: true,
  projectId: PROJECT as string | undefined,
  project: { id: PROJECT, name: "Residential Complex C", status: "active" },
  assignedProjects: [{ id: PROJECT, name: "Residential Complex C" }],
  portfolioPath: "/projects",
  path: (module: string) => `/projects/${PROJECT}/${module || "dashboard"}`,
};
vi.mock("../../../features/projects/context/ProjectWorkspaceContext", () => ({
  useProjectWorkspace: () => workspace,
}));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const { Sidebar } = await import("./Sidebar");

const at = (path: string, collapsed = false) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar collapsed={collapsed} />
    </MemoryRouter>,
  );

beforeEach(() => {
  granted = ["task.view", "document.view", "issue.view"];
  workspace.isProjectWorkspace = true;
});
afterEach(cleanup);

describe("Sidebar", () => {
  it("offers only the destinations the person's permissions allow", () => {
    at(`/projects/${PROJECT}/tasks`);
    expect(screen.getByRole("link", { name: "nav.tasks" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "nav.documents" })).toBeInTheDocument();
    // Guarded by task.review, schedule.view and project.manage_members.
    expect(screen.queryByRole("link", { name: "nav.pendingReviews" })).toBeNull();
    expect(screen.queryByRole("link", { name: "nav.schedule" })).toBeNull();
    expect(screen.queryByRole("link", { name: "nav.team" })).toBeNull();
  });

  it("marks the current destination, including on a tab route it owns", () => {
    at(`/projects/${PROJECT}/requests`);
    expect(screen.getByRole("link", { name: "nav.coordination" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "nav.tasks" })).not.toHaveAttribute("aria-current");
  });

  it("keeps every entry named when the rail is narrowed to icons", () => {
    at(`/projects/${PROJECT}/tasks`, true);
    const tasks = screen.getByRole("link", { name: "nav.tasks" });
    expect(tasks).toHaveAttribute("title", "nav.tasks");
    expect(tasks).toHaveAttribute("aria-current", "page");
  });

  it("shows no administration to someone without it", () => {
    workspace.isProjectWorkspace = false;
    at("/projects");
    expect(screen.queryByText("nav.administration")).toBeNull();
    expect(screen.queryByRole("link", { name: "nav.peopleAndAccess" })).toBeNull();
  });
});
