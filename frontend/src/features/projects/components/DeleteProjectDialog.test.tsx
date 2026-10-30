// @vitest-environment jsdom
/**
 * Deleting a project (2026-10-23): the server had `DELETE /projects/{id}` behind
 * `project.delete` and no screen called it. The dialog shows what goes with the
 * project, enables only once the name is typed, sends nothing on cancel, and
 * reports success only after the server agreed.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Project } from "../../../types/project";

const projectsService = { deletionImpact: vi.fn(), delete: vi.fn() };
const toast = { success: vi.fn(), error: vi.fn() };
vi.mock("../services/projects.service", () => ({ projectsService }));
vi.mock("react-hot-toast", () => ({ default: toast }));
const t = (key: string) => key;
const translation = { t, i18n: { language: "en" } };
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => translation,
}));

const { DeleteProjectDialog } = await import("./DeleteProjectDialog");

const project = { id: "p1", name: "Tower A" } as Project;
const IMPACT = { tasks: 4, members: 3, documents: 2, issues: 1, siteReports: 0, models: 1 };

const confirmButton = () => screen.getByRole("button", { name: "projectsPage.delete.confirm" }) as HTMLButtonElement;

describe("DeleteProjectDialog", () => {
  beforeEach(() => {
    projectsService.deletionImpact.mockReset().mockResolvedValue(IMPACT);
    projectsService.delete.mockReset();
    toast.success.mockReset();
    toast.error.mockReset();
  });
  afterEach(cleanup);

  it("shows the impact and needs the name before it will delete", async () => {
    render(<DeleteProjectDialog project={project} onClose={vi.fn()} onDeleted={vi.fn()} />);
    expect((await screen.findByTestId("deletion-impact")).children).toHaveLength(6);
    expect(confirmButton().disabled).toBe(true);
    await userEvent.type(screen.getByRole("textbox"), "Tower");
    expect(confirmButton().disabled).toBe(true);
    await userEvent.type(screen.getByRole("textbox"), " A");
    expect(confirmButton().disabled).toBe(false);
  });

  it("sends nothing when cancelled", async () => {
    const onClose = vi.fn();
    render(<DeleteProjectDialog project={project} onClose={onClose} onDeleted={vi.fn()} />);
    await screen.findByTestId("deletion-impact");
    await userEvent.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(onClose).toHaveBeenCalled();
    expect(projectsService.delete).not.toHaveBeenCalled();
  });

  it("reports success only after the server deleted it", async () => {
    projectsService.delete.mockResolvedValue(undefined);
    const onDeleted = vi.fn();
    render(<DeleteProjectDialog project={project} onClose={vi.fn()} onDeleted={onDeleted} />);
    await screen.findByTestId("deletion-impact");
    await userEvent.type(screen.getByRole("textbox"), "Tower A");
    await userEvent.click(confirmButton());
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("p1"));
    expect(projectsService.delete).toHaveBeenCalledWith("p1");
    expect(toast.success).toHaveBeenCalled();
  });

  it("keeps the project and says so when the server refuses", async () => {
    projectsService.delete.mockRejectedValue(
      Object.assign(new Error("Forbidden"), { response: { status: 403, data: { detail: "You do not have permission to delete a project" } } }));
    const onDeleted = vi.fn();
    render(<DeleteProjectDialog project={project} onClose={vi.fn()} onDeleted={onDeleted} />);
    await screen.findByTestId("deletion-impact");
    await userEvent.type(screen.getByRole("textbox"), "Tower A");
    await userEvent.click(confirmButton());
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(onDeleted).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("does not offer deletion when the impact cannot be loaded", async () => {
    projectsService.deletionImpact.mockRejectedValue(new Error("Forbidden"));
    render(<DeleteProjectDialog project={project} onClose={vi.fn()} onDeleted={vi.fn()} />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    await userEvent.type(screen.getByRole("textbox"), "Tower A");
    expect(confirmButton().disabled).toBe(true);
  });
});
