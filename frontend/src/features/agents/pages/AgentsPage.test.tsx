// @vitest-environment jsdom
/**
 * The screen that finally makes the five agents reachable, and the five things
 * it has to get right.
 *
 * 1. **Every agent is shown, including ones this person cannot run.** Hiding
 *    them would make the catalogue look different to different people with
 *    nobody able to say why. The permission a run needs is stated on the card.
 * 2. **A run button the caller may not use is disabled.** Not hidden, not
 *    optimistically enabled — the server refuses it either way, and an enabled
 *    button that always fails is worse than a disabled one that explains.
 * 3. **A skip is reported as a skip.** The orchestrator distinguishes "ran",
 *    "skipped" and "failed", and collapsing skips into failures would turn a
 *    normal permission outcome into an apparent bug.
 * 4. **Nothing is faked.** The finding count shown comes from the run response;
 *    the page never invents a result or claims an agent ran when it did not.
 * 5. **The automatic-analysis state comes from the server.** Declaring which
 *    events wake an agent is meaningless without saying whether that is
 *    switched on, and the page must not guess.
 */

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import type {
  AgentCatalogue,
  AgentDefinition,
  AgentRunRecord,
  AgentRunResult,
  OrchestrationReport,
} from "../../../types/agent";

const agentsApi = {
  list: vi.fn(),
  runOne: vi.fn(),
  orchestrate: vi.fn(),
  runs: vi.fn(),
  subscriptions: vi.fn(),
};
vi.mock("../../../services/api", () => ({ default: { agents: agentsApi } }));

const toastFn = Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() });
vi.mock("react-hot-toast", () => ({ default: toastFn }));

// Interpolation preserved: several assertions are about the numbers a message
// carries, not merely that some message appeared.
const translate = (key: string, vars?: Record<string, unknown>) => {
  if (vars && "defaultValue" in vars) return String(vars.defaultValue);
  return vars ? `${key} ${Object.values(vars).join(" ")}` : key;
};
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));

const PROJECT = "11111111-2222-3333-4444-555555555555";
const navigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
  useParams: () => ({ projectId: PROJECT }),
}));

vi.mock("../../projects/context/ProjectWorkspaceContext", () => ({
  useProjectWorkspace: () => ({
    projectId: PROJECT,
    path: (module: string) => `/projects/${PROJECT}/${module}`,
  }),
}));

const { AgentsPage } = await import("./AgentsPage");

const definition = (
  name: string,
  overrides: Partial<AgentDefinition> = {},
): AgentDefinition => ({
  name,
  title: name,
  responsibility: `What ${name} is for.`,
  allowedTools: ["get_tasks", "get_project_status"],
  permission: "task.view",
  sourceEngine: `${name.toUpperCase()}_V1`,
  subscribesTo: ["TASK_UPDATED"],
  ...overrides,
});

const FIVE = [
  "site_report_agent",
  "document_consistency_agent",
  "revision_impact_agent",
  "rfi_agent",
  "schedule_risk_agent",
].map((name) => definition(name));

const catalogue = (available: AgentDefinition[]): AgentCatalogue => ({
  available,
  catalogue: FIVE,
});

const runResult = (overrides: Partial<AgentRunResult> = {}): AgentRunResult => ({
  agent: "schedule_risk_agent",
  ok: true,
  findingCount: 3,
  findings: [],
  storedInsightIds: ["insight-1", "insight-2", "insight-3"],
  toolCalls: [{ tool: "get_tasks", ok: true, errorCode: null, arguments: {} }],
  durationMs: 42,
  ...overrides,
});

const runRecord = (overrides: Partial<AgentRunRecord> = {}): AgentRunRecord => ({
  id: "run-1",
  agent: "schedule_risk_agent",
  status: "SUCCEEDED",
  triggerType: "MANUAL",
  triggerReason: "Requested directly",
  findingCount: 2,
  findingCodes: ["SCHEDULE_TASKS_OVERDUE"],
  highestConfidence: 0.9,
  toolCalls: [
    { tool: "get_tasks", ok: true, errorCode: null, arguments: {} },
    { tool: "search_documents", ok: false, errorCode: "TOOL_NOT_GRANTED", arguments: {} },
  ],
  insightIds: ["insight-1"],
  durationMs: 120,
  errorCode: null,
  error: null,
  createdAt: "2026-01-01T00:00:00Z",
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
  agentsApi.list.mockResolvedValue(catalogue(FIVE));
  agentsApi.runs.mockResolvedValue([]);
  agentsApi.subscriptions.mockResolvedValue({
    subscriptions: { TASK_UPDATED: ["schedule_risk_agent"] },
    automaticAnalysisEnabled: false,
    note: "Automatic analysis is switched off.",
  });
});

afterEach(cleanup);

const openPage = async () => {
  render(<AgentsPage />);
  await waitFor(() => expect(agentsApi.list).toHaveBeenCalledWith(PROJECT));
  await screen.findByText("agents.runHistory");
};

describe("the agent catalogue", () => {
  it("shows all five agents, not only the runnable ones", async () => {
    agentsApi.list.mockResolvedValue(catalogue([FIVE[0]]));
    await openPage();

    for (const agent of FIVE) {
      expect(screen.getByText(agent.name)).toBeInTheDocument();
    }
  });

  it("disables the run button for an agent this caller may not run", async () => {
    agentsApi.list.mockResolvedValue(catalogue([FIVE[0]]));
    await openPage();

    expect(
      within(screen.getByTestId(`agent-${FIVE[0].name}`)).getByRole("button"),
    ).toBeEnabled();
    expect(
      within(screen.getByTestId(`agent-${FIVE[1].name}`)).getByRole("button"),
    ).toBeDisabled();
  });

  it("names the permission a blocked agent would need", async () => {
    agentsApi.list.mockResolvedValue(
      catalogue([]) as AgentCatalogue,
    );
    await openPage();

    expect(screen.getAllByText(/agents.requiresPermission task.view/).length).toBe(5);
  });

  it("states the tools an agent is allowed to call", async () => {
    await openPage();
    expect(screen.getAllByText("get_tasks").length).toBeGreaterThan(0);
  });
});

describe("running an agent", () => {
  it("runs one agent and reports the findings the server returned", async () => {
    agentsApi.runOne.mockResolvedValue(runResult({ agent: FIVE[0].name, findingCount: 3 }));
    await openPage();

    const card = screen.getByTestId(`agent-${FIVE[0].name}`);
    await userEvent.click(within(card).getByRole("button"));

    await waitFor(() =>
      expect(agentsApi.runOne).toHaveBeenCalledWith(PROJECT, FIVE[0].name),
    );
    expect(toastFn.success).toHaveBeenCalledWith(
      expect.stringContaining("3"),
    );
  });

  it("surfaces a failed run instead of reporting success", async () => {
    agentsApi.runOne.mockRejectedValue(new Error("boom"));
    await openPage();

    const card = screen.getByTestId(`agent-${FIVE[0].name}`);
    await userEvent.click(within(card).getByRole("button"));

    await waitFor(() => expect(toastFn.error).toHaveBeenCalled());
    expect(toastFn.success).not.toHaveBeenCalled();
  });

  it("reports skipped agents as skips, separately from failures", async () => {
    const report: OrchestrationReport = {
      projectId: PROJECT,
      trigger: { type: "MANUAL", reason: "Requested directly" },
      ran: [runResult({ agent: FIVE[0].name, findingCount: 1 })],
      skipped: [
        {
          agent: FIVE[1].name,
          shouldRun: false,
          reason: "The caller does not hold task.view.",
          skipCode: "FORBIDDEN",
        },
      ],
      failed: [],
      agentsRun: 1,
      agentsSkipped: 1,
      agentsFailed: 0,
      findingCount: 1,
    };
    agentsApi.orchestrate.mockResolvedValue(report);
    await openPage();

    await userEvent.click(screen.getByText(/agents.runAll/).closest("button")!);

    await waitFor(() => expect(agentsApi.orchestrate).toHaveBeenCalledWith(PROJECT));
    // The skip is announced with its reason, not folded into an error toast.
    expect(toastFn).toHaveBeenCalledWith(
      expect.stringContaining("does not hold task.view"),
      expect.anything(),
    );
    expect(toastFn.error).not.toHaveBeenCalled();
  });

  it("does not offer a pass when there is nothing this caller may run", async () => {
    agentsApi.list.mockResolvedValue(catalogue([]));
    await openPage();

    expect(screen.getByText(/agents.runAll/).closest("button")).toBeDisabled();
    expect(screen.getByText("agents.noneRunnable")).toBeInTheDocument();
  });
});

describe("the run history", () => {
  it("shows what a run called, including the tools it was refused", async () => {
    agentsApi.runs.mockResolvedValue([runRecord()]);
    await openPage();

    expect(screen.getByText(/agents.toolCallsMade 2 1/)).toBeInTheDocument();
    expect(screen.getByText("TOOL_NOT_GRANTED")).toBeInTheDocument();
  });

  it("distinguishes an automatic run from a requested one", async () => {
    agentsApi.runs.mockResolvedValue([
      runRecord({ id: "a", triggerType: "EVENT" }),
      runRecord({ id: "b", triggerType: "MANUAL" }),
    ]);
    await openPage();

    // The mocked `t` resolves to the key's defaultValue, which for these badges
    // is the raw trigger type — the assertion is that the two render distinctly.
    expect(screen.getByText("EVENT")).toBeInTheDocument();
    expect(screen.getByText("MANUAL")).toBeInTheDocument();
  });

  it("says so plainly when nothing has run yet", async () => {
    await openPage();
    expect(screen.getByText("agents.noRunsYet")).toBeInTheDocument();
  });
});

describe("automatic analysis", () => {
  it("reports the server's state rather than assuming it", async () => {
    await openPage();
    expect(screen.getByText("agents.automaticOff")).toBeInTheDocument();
    expect(screen.getByText("Automatic analysis is switched off.")).toBeInTheDocument();
  });

  it("says it is on when the server says so", async () => {
    agentsApi.subscriptions.mockResolvedValue({
      subscriptions: {},
      automaticAnalysisEnabled: true,
      note: "These events trigger analysis automatically on this server.",
    });
    await openPage();
    expect(screen.getByText("agents.automaticOn")).toBeInTheDocument();
  });

  it("still renders the agents when the subscription call fails", async () => {
    agentsApi.subscriptions.mockRejectedValue(new Error("503"));
    await openPage();

    expect(screen.getByText(FIVE[0].name)).toBeInTheDocument();
    expect(screen.queryByText("agents.automaticOff")).not.toBeInTheDocument();
  });
});

describe("failure to load", () => {
  it("offers a retry rather than an empty page", async () => {
    agentsApi.list.mockRejectedValueOnce(new Error("nope"));
    render(<AgentsPage />);

    const retry = await screen.findByText(/Retry/);
    agentsApi.list.mockResolvedValue(catalogue(FIVE));
    await userEvent.click(retry);

    await waitFor(() => expect(screen.getByText(FIVE[0].name)).toBeInTheDocument());
  });
});

describe("navigation wiring", () => {
  it("resolves the agents module rather than silently falling back", async () => {
    // `canOpenProjectModule` answers false for any module missing from
    // MODULE_PERMISSIONS, and `projectModulePath` then quietly substitutes the
    // fallback — so a sidebar entry for an unregistered module points at the
    // wrong page with no error anywhere. This caught exactly that.
    const { canOpenProjectModule, projectModulePath } = await import(
      "../../../utils/projectRoutes"
    );
    expect(canOpenProjectModule("agents", () => true)).toBe(true);
    expect(projectModulePath(PROJECT, "agents", () => true)).toBe(
      `/projects/${PROJECT}/agents`,
    );
  });

  it("keeps somebody without task.view off the agents module", async () => {
    const { canOpenProjectModule } = await import("../../../utils/projectRoutes");
    expect(canOpenProjectModule("agents", (code) => code !== "task.view")).toBe(false);
  });
});
