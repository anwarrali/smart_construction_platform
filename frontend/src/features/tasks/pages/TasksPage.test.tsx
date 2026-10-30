// @vitest-environment jsdom
/**
 * QA pass 2026-10-17, defect 2 — task filtering on the managed board.
 *
 * The project board sent the selected status to an endpoint that ignored it,
 * so every filter showed every task. The server now filters; these cases pin
 * the page's side: the filter reaches the request, the board shows exactly
 * what came back, clearing the filter restores the full list, and a slow
 * response for a filter no longer selected never overwrites a newer one.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Task } from "../../../types/task";

const tasksService = { getByProject: vi.fn(), list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() };

vi.mock("../services/tasks.service", () => ({ tasksService }));
vi.mock("react-hot-toast", () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../hooks/useRole", () => ({
  useRole: () => ({ permissionsReady: true, hasCapability: (code: string) => code === "task.edit" || code === "task.view" }),
}));
vi.mock("../../projects/context/ProjectWorkspaceContext", () => ({
  useProjectWorkspace: () => ({ projectId: "project-1", project: { name: "Tower" }, path: (p: string) => p }),
}));
vi.mock("../../../hooks/useRealtimeRefresh", () => ({ useRealtimeRefresh: () => undefined }));
vi.mock("../../../hooks/useDebounce", () => ({ useDebounce: (value: unknown) => value }));
vi.mock("../../../hooks/useDisciplineOptions", () => ({ useDisciplineOptions: () => ({ options: [] }) }));
vi.mock("../../../utils/vocabulary", () => ({
  useVocabulary: () => ({ taskStatus: (v: string) => v, priority: (v: string) => v }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
// The board itself has its own coverage; here only which tasks it was given matters.
vi.mock("../components/TaskBoard", () => ({
  TaskBoard: ({ tasks, isLoading }: { tasks: Task[]; isLoading: boolean }) => (
    <ul data-testid="board" data-loading={String(isLoading)}>
      {tasks.map((task) => <li key={task.id}>{task.taskCode}</li>)}
    </ul>
  ),
}));
vi.mock("../components/TaskForm", () => ({ TaskForm: () => null }));

const { TasksPage } = await import("./TasksPage");

const task = (code: string, status: string) => ({ id: code, taskCode: code, name: code, status }) as unknown as Task;
const ALL = [task("TSK-001", "todo"), task("TSK-002", "in_progress"), task("TSK-003", "done")];
const codes = () => screen.queryAllByRole("listitem").map((node) => node.textContent);
const statusSelect = () => screen.getAllByRole("combobox")[0];

describe("managed task board filtering", () => {
  beforeEach(() => {
    tasksService.getByProject.mockReset();
    tasksService.getByProject.mockImplementation(async (_id: string, filters: { status?: string }) =>
      filters?.status ? ALL.filter((item) => item.status === filters.status) : ALL,
    );
  });
  afterEach(cleanup);

  it("sends the selected status and shows exactly the tasks returned", async () => {
    const user = userEvent.setup();
    render(<TasksPage />);
    await waitFor(() => expect(codes()).toEqual(["TSK-001", "TSK-002", "TSK-003"]));

    await user.selectOptions(statusSelect(), "in_progress");
    await waitFor(() => expect(codes()).toEqual(["TSK-002"]));
    expect(tasksService.getByProject).toHaveBeenLastCalledWith("project-1", expect.objectContaining({ status: "in_progress" }));

    await user.selectOptions(statusSelect(), "under_review");
    await waitFor(() => expect(codes()).toEqual([]));

    await user.selectOptions(statusSelect(), "");
    await waitFor(() => expect(codes()).toEqual(["TSK-001", "TSK-002", "TSK-003"]));
    expect(tasksService.getByProject).toHaveBeenLastCalledWith("project-1", expect.objectContaining({ status: undefined }));
  });

  // QA 2026-10-22: a refused load drew every column as "no tasks".
  it("says access is denied instead of drawing an empty board when the server refuses", async () => {
    tasksService.getByProject.mockRejectedValue({ response: { status: 403, data: { detail: "You do not have access to this project" } } });
    render(<TasksPage />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("tasksPage.access_denied_title");
    expect(screen.queryByTestId("board")).toBeNull();
  });

  it("offers a retry, not an empty board, when loading fails for another reason", async () => {
    tasksService.getByProject.mockRejectedValueOnce(new Error("Network Error"));
    render(<TasksPage />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("tasksPage.unable_to_load_tasks");
    expect(screen.queryByTestId("board")).toBeNull();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "common.retry" }));
    await waitFor(() => expect(codes()).toEqual(["TSK-001", "TSK-002", "TSK-003"]));
  });

  it("ignores a slower response for a filter that is no longer selected", async () => {
    const user = userEvent.setup();
    render(<TasksPage />);
    await waitFor(() => expect(codes()).toHaveLength(3));

    let releaseSlow: () => void = () => undefined;
    tasksService.getByProject.mockImplementationOnce(
      () => new Promise((done) => { releaseSlow = () => done([task("TSK-001", "todo")]); }),
    );
    await user.selectOptions(statusSelect(), "todo");
    await user.selectOptions(statusSelect(), "done");
    await waitFor(() => expect(codes()).toEqual(["TSK-003"]));

    releaseSlow();
    await new Promise((done) => setTimeout(done, 20));
    expect(codes()).toEqual(["TSK-003"]);
    expect(screen.getByTestId("board").dataset.loading).toBe("false");
  });
});
