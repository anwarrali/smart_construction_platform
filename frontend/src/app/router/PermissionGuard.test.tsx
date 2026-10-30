// @vitest-environment jsdom
/**
 * Route guards inside and outside a project.
 *
 * QA-06B: a refused page inside a project leads to the first page of that
 * project the person can open — the team page for an administrator who is not
 * on the team — instead of out to the portfolio.
 *
 * QA 2026-10-22: the Projects page's "Open" goes to the bare `/projects/:id`,
 * which the guard did not recognise as a project, so the administrator ended
 * on the portfolio dashboard; and the guard rendered the page on the
 * office-wide answer before the project's arrived, so the page fired requests
 * the server refused.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let held: string[] = [];
let ready = true;
vi.mock("../../hooks/useRole", () => ({
  useRole: () => ({ permissionsReady: ready, hasCapability: (code: string) => held.includes(code) }),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const { usePermissionStore } = await import("../store/permission.store");
const { PermissionGuard } = await import("./PermissionGuard");

const page = vi.fn(() => <p>project page</p>);
const ProjectPage = () => page();

const at = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<PermissionGuard permissions={["task.view_all"]} />}>
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="/projects/:id/dashboard" element={<ProjectPage />} />
        </Route>
        <Route element={<PermissionGuard permissions={["task.view"]} />}>
          <Route path="/projects/:id/tasks" element={<p>tasks page</p>} />
          <Route path="/reports" element={<p>reports page</p>} />
        </Route>
        <Route path="/projects/:id/team" element={<p>team page</p>} />
        <Route path="/dashboard" element={<p>portfolio dashboard</p>} />
      </Routes>
    </MemoryRouter>,
  );

const loadProject = (id: string, codes: string[]) =>
  usePermissionStore.setState({ activeProjectId: id, project: { id, codes } });

describe("PermissionGuard inside a project", () => {
  beforeEach(() => { page.mockClear(); });
  afterEach(() => {
    cleanup();
    held = [];
    ready = true;
    usePermissionStore.setState({ activeProjectId: null, project: null });
  });

  it("sends a registry-only administrator to the project's team page", () => {
    held = ["project.manage_members"];
    loadProject("p1", held);
    at("/projects/p1/tasks");
    expect(screen.getByText("team page")).toBeTruthy();
  });

  it("recognises the bare project address, not only /projects/:id/…", () => {
    held = ["project.manage_members"];
    loadProject("p1", held);
    at("/projects/p1");
    expect(screen.getByText("team page")).toBeTruthy();
    expect(screen.queryByText("portfolio dashboard")).toBeNull();
  });

  it("does not render the page until the project's own permissions have arrived", () => {
    // Office-wide, this person would pass; in this project they do not. The
    // page must not mount — and fire its requests — on the office-wide answer.
    held = ["task.view_all", "project.manage_members"];
    at("/projects/p1/dashboard");
    expect(page).not.toHaveBeenCalled();
    expect(screen.getByRole("status").textContent).toBe("common.loading");
  });

  it("does not render a project page on a fresh load before any permissions have arrived", () => {
    // A full page load starts with nothing known. Outside a project the guard
    // renders optimistically; inside one that let the overview fire requests
    // the server refused before the redirect caught up.
    ready = false;
    at("/projects/p1/dashboard");
    expect(page).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("lets a team member through once the project's answer is in", () => {
    held = ["task.view"];
    loadProject("p1", held);
    at("/projects/p1/tasks");
    expect(screen.getByText("tasks page")).toBeTruthy();
  });

  it("still sends a refusal outside a project to the dashboard", () => {
    at("/reports");
    expect(screen.getByText("portfolio dashboard")).toBeTruthy();
  });
});
