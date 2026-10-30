// @vitest-environment jsdom
/**
 * QA 2026-10-22: engineers who may review land on this dashboard from the
 * portfolio, where no project is open. It returned early without ever
 * clearing `loading`, so "Loading supervision workspace" stayed on screen for
 * good. Every path must end in data, an empty state or an error.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const dashboard = vi.fn();
let projectId: string | undefined;

vi.mock("../../../../services/api", () => ({ default: { consultant: { dashboard } } }));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("../../../../utils/vocabulary", () => ({ useVocabulary: () => new Proxy({}, { get: () => (v: string) => v }) }));
vi.mock("../../../projects/context/ProjectWorkspaceContext", () => ({
  useProjectWorkspace: () => ({ projectId, isLoading: false, error: "", path: (p: string) => p }),
}));

const { ConsultantDashboard } = await import("./ConsultantDashboard");

describe("supervision dashboard loading", () => {
  afterEach(() => { cleanup(); dashboard.mockReset(); projectId = undefined; });

  it("settles on the choose-a-project state when no project is open", async () => {
    render(<ConsultantDashboard />);
    await screen.findByText("consultantDash.select_an_assigned_project_to_open_its");
    expect(screen.queryByText("consultantDash.loading_supervision_workspace")).toBeNull();
    expect(dashboard).not.toHaveBeenCalled();
  });

  it("settles on an error with a retry when the request fails", async () => {
    projectId = "p1";
    dashboard.mockRejectedValue(new Error("Network Error"));
    render(<ConsultantDashboard />);
    await screen.findByRole("button", { name: "consultantDash.try_again" });
    expect(screen.queryByText("consultantDash.loading_supervision_workspace")).toBeNull();
  });

  it("asks for the open project's data", async () => {
    projectId = "p1";
    dashboard.mockReturnValue(new Promise(() => undefined));
    render(<ConsultantDashboard />);
    await waitFor(() => expect(dashboard).toHaveBeenCalledWith("p1"));
    expect(screen.getByText("consultantDash.loading_supervision_workspace")).toBeTruthy();
  });
});
