// @vitest-environment jsdom
/**
 * QA pass 2026-10-17, defect 8 — task progress on the managed detail page.
 *
 * Observed: progress was offered on To Do work and the server refused it
 * ("Start the task before updating progress"); repeated clicks sent the same
 * save several times; and a save that committed was reported as a failure
 * when the refresh after it failed. These pin the corrected behaviour.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const tasksApi = {
  getById: vi.fn(),
  comments: vi.fn(),
  reviews: vi.fn(),
  getByProject: vi.fn(),
  updateProgress: vi.fn(),
  start: vi.fn(),
  submitReview: vi.fn(),
};
const toast = { success: vi.fn(), error: vi.fn() };

vi.mock("../../../services/api", () => ({ default: { tasks: tasksApi } }));
vi.mock("react-hot-toast", () => ({ default: toast }));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn(), useParams: () => ({ taskId: "task-1" }) }));
vi.mock("../../../hooks/useAuth", () => ({ useAuth: () => ({ user: { id: "user-1" } }) }));
// A site lead who both edits tasks and executes the ones assigned to them.
vi.mock("../../../hooks/useRole", () => ({
  useRole: () => ({
    permissionsReady: true,
    hasCapability: (code: string) => ["task.edit", "task.update_progress", "task.view"].includes(code),
  }),
}));
vi.mock("../../projects/context/ProjectWorkspaceContext", () => ({
  useProjectWorkspace: () => ({ projectId: "project-1", isProjectWorkspace: true, path: (p: string) => p }),
}));
vi.mock("../../messages/components/ContextDiscussion", () => ({ ContextDiscussion: () => null }));
vi.mock("../../../components/shared/CommunicationActions", () => ({ CommunicationActions: () => null }));
vi.mock("./EngineerTaskDetailPage", () => ({ EngineerTaskDetailPage: () => null }));

const { TaskDetailPage } = await import("./TaskDetailPage");

const task = (status: string, progressPercentage = 20) => ({
  id: "task-1",
  projectId: "project-1",
  taskCode: "TSK-001",
  name: "Electrical rough-in",
  status,
  progressPercentage,
  priority: "medium",
  assigneeIds: ["user-1"],
  assignees: [],
  dependencies: [],
});

describe("managed task detail — progress", () => {
  beforeEach(() => {
    Object.values(tasksApi).forEach((mock) => mock.mockReset());
    toast.success.mockReset();
    tasksApi.comments.mockResolvedValue([]);
    tasksApi.reviews.mockResolvedValue([]);
    tasksApi.getByProject.mockResolvedValue([]);
  });
  afterEach(cleanup);

  it("offers Start, not a progress box, on work that has not started", async () => {
    const user = userEvent.setup();
    tasksApi.getById.mockResolvedValueOnce(task("todo", 0)).mockResolvedValue(task("in_progress", 0));
    tasksApi.start.mockResolvedValue({});
    render(<TaskDetailPage />);

    await screen.findByText("taskDetail.start_before_progress");
    expect(screen.queryByRole("button", { name: "taskDetail.save_progress" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "engineerTask.start_task" }));
    expect(tasksApi.start).toHaveBeenCalledWith("task-1");
    await screen.findByRole("button", { name: "taskDetail.save_progress" });
  });

  it("sends one save however many times the button is clicked", async () => {
    const user = userEvent.setup();
    tasksApi.getById.mockResolvedValue(task("in_progress"));
    let finish: () => void = () => undefined;
    tasksApi.updateProgress.mockReturnValue(new Promise<void>((done) => { finish = done; }));
    render(<TaskDetailPage />);

    const save = await screen.findByRole("button", { name: "taskDetail.save_progress" });
    await user.click(save);
    await user.click(save);
    await user.click(save);
    finish();

    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
    expect(tasksApi.updateProgress).toHaveBeenCalledTimes(1);
  });

  it("reports a committed save as saved even if the refresh afterwards fails", async () => {
    const user = userEvent.setup();
    tasksApi.getById.mockResolvedValueOnce(task("in_progress")).mockRejectedValue(new Error("Network Error"));
    tasksApi.updateProgress.mockResolvedValue({});
    render(<TaskDetailPage />);

    await user.click(await screen.findByRole("button", { name: "taskDetail.save_progress" }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("taskDetail.saved"));
    // The task stays on screen; nothing claims the save itself failed.
    expect(screen.getByText("Electrical rough-in")).toBeTruthy();
    expect(screen.queryByText("Action failed")).toBeNull();
  });
});
