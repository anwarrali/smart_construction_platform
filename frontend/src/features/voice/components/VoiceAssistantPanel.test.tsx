// @vitest-environment jsdom
/**
 * The safety properties of the voice panel, as behaviour rather than intent.
 *
 * Everything asserted here is a "must not": must not confirm while a task is
 * ambiguous, must not mutate on cancel, must not claim success the backend did
 * not report, must not lose a recording to a network failure. The happy path
 * is covered too, but it is the cheap half — a voice assistant that sometimes
 * updates the wrong task is worse than one that sometimes asks twice.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { UseVoiceCapture } from "../../../hooks/useVoiceCapture";
import type { VoiceCommand } from "../../../types/voice";

const voiceApi = {
  createCommand: vi.fn(),
  taskCandidates: vi.fn(),
  updateDraft: vi.fn(),
  answerClarification: vi.fn(),
  confirm: vi.fn(),
  execute: vi.fn(),
  cancel: vi.fn(),
  reportReadiness: vi.fn(),
};

vi.mock("../../../services/api", () => ({ default: { voice: voiceApi } }));
vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("react-i18next", async (importOriginal) => ({
  // Render the key itself: the assertions are about which state the panel is
  // in, and the catalogue has its own coverage tests. The rest of the module
  // is kept because `utils/errorMessage` pulls in the real i18n bootstrap.
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}));

const captureResult = {
  audio: new Blob(["audio"], { type: "audio/webm" }),
  filename: "voice-1.webm",
  durationSeconds: 6,
  previewTranscript: "electrical work is finished",
  timings: { micStartMs: 40, recordingMs: 6000, firstPartialTranscriptMs: 300 },
};

type CaptureResult = Awaited<ReturnType<UseVoiceCapture["stop"]>>;

const capture = {
  state: "idle" as const,
  previewTranscript: "",
  elapsedSeconds: 0,
  level: 0,
  supported: true,
  previewSupported: true,
  error: "",
  start: vi.fn(async () => undefined),
  stop: vi.fn(async (): Promise<CaptureResult> => captureResult),
  cancel: vi.fn(),
};

vi.mock("../../../hooks/useVoiceCapture", () => ({
  useVoiceCapture: () => capture,
}));

const { VoiceAssistantPanel } = await import("./VoiceAssistantPanel");

const draft = (overrides: Partial<VoiceCommand["actionDrafts"][number]> = {}) => ({
  id: "draft-1",
  clientActionId: "a1",
  sequence: 0,
  actionType: "UPDATE_TASK_PROGRESS",
  targetEntityId: "task-1",
  extractedPayload: { progressPercentage: 100 },
  confidence: 0.91,
  missingFields: [] as string[],
  warnings: [] as string[],
  riskLevel: "MEDIUM" as const,
  requiredEvidence: [] as string[],
  selectedForExecution: true,
  executionStatus: "DRAFT",
  ...overrides,
});

const command = (overrides: Partial<VoiceCommand> = {}): VoiceCommand => ({
  id: "cmd-1",
  projectId: "project-1",
  userId: "user-1",
  status: "READY_FOR_CONFIRMATION",
  rowVersion: 3,
  rawTranscript: "electrical work is finished",
  structuredResult: { summary: "Electrical work complete" },
  actionDrafts: [draft()],
  clarifications: [],
  createdAt: new Date().toISOString(),
  ...overrides,
});

const ambiguous = (): VoiceCommand =>
  command({
    status: "NEEDS_CLARIFICATION",
    actionDrafts: [draft({ missingFields: ["target.taskId"], targetEntityId: undefined })],
    clarifications: [
      {
        id: "clar-1",
        voiceActionDraftId: "draft-1",
        sequence: 1,
        fieldPath: "target.taskId",
        questionAr: "أي مهمة تقصد؟",
        questionEn: "Which task do you mean?",
        expectedAnswerType: "TASK_SELECTION",
        options: [
          { value: "task-1", label: "EL-101 — First Floor Electrical Installation", score: 0.64, reasons: ["electrical"] },
          { value: "task-2", label: "EL-102 — First Floor Electrical Fixtures", score: 0.63, reasons: ["electrical"] },
          { value: "task-3", label: "EL-103 — First Floor Electrical Inspection", score: 0.62, reasons: ["electrical"] },
        ],
      },
    ],
  });

const speak = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByRole("button", { name: "voiceAssistant.speak" }));
  await user.click(screen.getByRole("button", { name: "voiceAssistant.stop" }));
};

describe("voice assistant panel", () => {
  beforeEach(() => {
    Object.values(voiceApi).forEach((mock) => mock.mockReset());
    capture.start.mockClear();
    capture.stop.mockClear();
    capture.cancel.mockClear();
    capture.stop.mockResolvedValue(captureResult);
    voiceApi.taskCandidates.mockResolvedValue({ confidence: 0, candidates: [] });
  });

  // This project registers no global testing-library setup file, so unmounting
  // between cases is this file's own responsibility. Without it every query
  // below matches the previous test's DOM as well as its own.
  afterEach(cleanup);

  it("shows a short candidate list instead of asking for an exact task name", async () => {
    const user = userEvent.setup();
    voiceApi.createCommand.mockResolvedValue(ambiguous());
    render(<VoiceAssistantPanel projectId="project-1" />);

    await speak(user);

    await waitFor(() => expect(screen.getByText("voiceAssistant.whichTask")).toBeTruthy());
    const options = screen.getAllByRole("button", { pressed: false })
      .filter((node) => node.textContent?.includes("EL-1"));
    expect(options.length).toBe(3);
    expect(options.length).toBeLessThanOrEqual(5);
  });

  it("will not confirm while a task is still ambiguous", async () => {
    const user = userEvent.setup();
    voiceApi.createCommand.mockResolvedValue(ambiguous());
    render(<VoiceAssistantPanel projectId="project-1" />);

    await speak(user);

    const confirm = await screen.findByRole("button", { name: "voiceAssistant.confirmAndApply" });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    expect(voiceApi.confirm).not.toHaveBeenCalled();
    expect(voiceApi.execute).not.toHaveBeenCalled();
  });

  it("resolves the ambiguity through the engineer's own choice", async () => {
    const user = userEvent.setup();
    voiceApi.createCommand.mockResolvedValue(ambiguous());
    voiceApi.answerClarification.mockResolvedValue(command());
    render(<VoiceAssistantPanel projectId="project-1" />);

    await speak(user);
    await user.click(await screen.findByText(/EL-102/));

    expect(voiceApi.answerClarification).toHaveBeenCalledWith("cmd-1", "clar-1", "task-2");
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "voiceAssistant.confirmAndApply" }) as HTMLButtonElement)
          .disabled,
      ).toBe(false),
    );
  });

  it("applies nothing until the engineer confirms", async () => {
    const user = userEvent.setup();
    voiceApi.createCommand.mockResolvedValue(command());
    render(<VoiceAssistantPanel projectId="project-1" />);

    await speak(user);
    await screen.findByRole("button", { name: "voiceAssistant.confirmAndApply" });

    expect(voiceApi.confirm).not.toHaveBeenCalled();
    expect(voiceApi.execute).not.toHaveBeenCalled();
  });

  it("mutates nothing when the engineer cancels", async () => {
    const user = userEvent.setup();
    voiceApi.createCommand.mockResolvedValue(command());
    voiceApi.cancel.mockResolvedValue(command({ status: "CANCELLED" }));
    render(<VoiceAssistantPanel projectId="project-1" />);

    await speak(user);
    await user.click(
      (await screen.findAllByRole("button", { name: "voiceAssistant.cancel" }))[0],
    );

    expect(voiceApi.confirm).not.toHaveBeenCalled();
    expect(voiceApi.execute).not.toHaveBeenCalled();
    await waitFor(() => expect(voiceApi.cancel).toHaveBeenCalledWith("cmd-1"));
  });

  it("reports success only when the backend confirms every action", async () => {
    const user = userEvent.setup();
    voiceApi.createCommand.mockResolvedValue(command());
    voiceApi.confirm.mockResolvedValue(command({ status: "CONFIRMED", rowVersion: 4 }));
    voiceApi.execute.mockResolvedValue(
      command({
        status: "EXECUTED",
        rowVersion: 5,
        actionResults: [
          { type: "UPDATE_TASK_PROGRESS", success: true, status: "EXECUTED", message: "ok" },
        ],
      }),
    );
    render(<VoiceAssistantPanel projectId="project-1" />);

    await speak(user);
    await user.click(await screen.findByRole("button", { name: "voiceAssistant.confirmAndApply" }));

    await waitFor(() => expect(screen.getByText("voiceAssistant.finished")).toBeTruthy());
    expect(voiceApi.execute).toHaveBeenCalledWith("cmd-1", 4);
  });

  it("does not claim success when the backend rejected the action", async () => {
    const user = userEvent.setup();
    voiceApi.createCommand.mockResolvedValue(command());
    voiceApi.confirm.mockResolvedValue(command({ status: "CONFIRMED", rowVersion: 4 }));
    voiceApi.execute.mockResolvedValue(
      command({
        status: "PARTIALLY_EXECUTED",
        rowVersion: 5,
        actionResults: [
          {
            type: "UPDATE_TASK_PROGRESS",
            success: false,
            status: "REJECTED",
            // What the backend raised, for the log.
            message: "Only the assigned engineer can update progress",
            // What it says to the person, classified and phrased server-side.
            errorCode: "PERMISSION_DENIED",
            userMessage: "You do not have permission to make this change.",
          },
        ],
      }),
    );
    render(<VoiceAssistantPanel projectId="project-1" />);

    await speak(user);
    await user.click(await screen.findByRole("button", { name: "voiceAssistant.confirmAndApply" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "You do not have permission",
      ),
    );
    // The backend's internal wording never reaches the screen.
    expect(screen.getByRole("alert").textContent).not.toContain("assigned engineer");
    expect(screen.queryByText("voiceAssistant.finished")).toBeNull();
  });

  it("keeps the recording and offers a retry when the network fails", async () => {
    const user = userEvent.setup();
    voiceApi.createCommand.mockRejectedValueOnce(new Error("Network Error"));
    render(<VoiceAssistantPanel projectId="project-1" />);

    await speak(user);

    const retry = await screen.findByRole("button", { name: "voiceAssistant.retrySend" });
    voiceApi.createCommand.mockResolvedValueOnce(command());
    await user.click(retry);

    await waitFor(() => expect(voiceApi.createCommand).toHaveBeenCalledTimes(2));
    // The same audio, not a demand that the engineer repeat themselves.
    expect(voiceApi.createCommand.mock.calls[1][0].audio).toBe(captureResult.audio);
  });

  it("tells the engineer when nothing was recorded", async () => {
    const user = userEvent.setup();
    capture.stop.mockResolvedValueOnce(null);
    render(<VoiceAssistantPanel projectId="project-1" />);

    await speak(user);

    expect(screen.getByRole("alert").textContent).toContain("voiceAssistant.nothingHeard");
    expect(voiceApi.createCommand).not.toHaveBeenCalled();
  });
});
