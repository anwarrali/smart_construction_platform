// @vitest-environment jsdom
/**
 * QA 2026-10-22: an office let Engineers create projects. Holding
 * `platform.create_project` alone used to pick the project manager's portfolio
 * dashboard, whose endpoints require `task.view_all` — a dashboard that could
 * only refuse an engineer. Creating projects is reached from Projects; the
 * landing still follows what the person does day to day.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

let held: string[] = [];
vi.mock("../../hooks/useRole", () => ({
  useRole: () => ({ hasCapability: (code: string) => held.includes(code), permissionsReady: true, isInternal: true }),
}));
vi.mock("../../app/store/auth.store", () => ({
  useAuthStore: (select: (state: unknown) => unknown) => select({ user: { id: "u", status: "active" } }),
}));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-router-dom", () => ({ Navigate: ({ to }: { to: string }) => <p>redirect {to}</p> }));
vi.mock("./project-manager/pages/ProjectManagerDashboard", () => ({ ProjectManagerDashboard: () => <p>pm dashboard</p> }));
vi.mock("./consultant/pages/ConsultantDashboard", () => ({ ConsultantDashboard: () => <p>review dashboard</p> }));
vi.mock("../../services/api", () => ({ default: { projects: { list: vi.fn(() => new Promise(() => undefined)) } } }));

const { DashboardSelectorPage } = await import("./DashboardSelectorPage");

describe("dashboard selector", () => {
  afterEach(() => { cleanup(); held = []; });

  it("keeps an engineer who may create projects on their own work", () => {
    held = ["task.view", "task.review", "platform.create_project"];
    render(<DashboardSelectorPage />);
    expect(screen.queryByText("pm dashboard")).toBeNull();
    expect(screen.getByText("review dashboard")).toBeTruthy();
  });

  it("gives the portfolio dashboard to somebody who staffs projects", () => {
    held = ["task.view", "task.view_all", "project.manage_members"];
    render(<DashboardSelectorPage />);
    expect(screen.getByText("pm dashboard")).toBeTruthy();
  });

  it("gives it to a creator who also sees project-wide work", () => {
    held = ["task.view", "task.view_all", "platform.create_project"];
    render(<DashboardSelectorPage />);
    expect(screen.getByText("pm dashboard")).toBeTruthy();
  });
});
