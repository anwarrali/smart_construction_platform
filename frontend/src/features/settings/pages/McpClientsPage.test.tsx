// @vitest-environment jsdom
/**
 * The screen that hands somebody a credential, and the four things it must
 * get right.
 *
 * 1. **The secret is shown once, with the configuration around it.** The
 *    server keeps only a hash, so this is not the last convenient moment to
 *    copy the token — it is the only moment it exists outside the client that
 *    will hold it. What is offered has to be pasteable as it stands: the URL
 *    and the `Bearer` header, not the bare secret.
 * 2. **Nothing else can show a secret.** The list has no such field, and the
 *    dialog must not still be holding the previous one when it reopens.
 * 3. **A disabled surface is explained, not failed.** `MCP_ENABLED=false`
 *    answers 503, which as a red toast would read like a bug.
 * 4. **Revoking asks first, and names what it is about to disconnect.**
 */

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import type { McpToken } from "../../../types/mcp";

const mcpApi = { list: vi.fn(), create: vi.fn(), revoke: vi.fn() };
const projectsApi = { list: vi.fn() };
vi.mock("../../../services/api", () => ({
  default: { mcpTokens: mcpApi, projects: projectsApi },
}));

const toast = { success: vi.fn(), error: vi.fn() };
vi.mock("react-hot-toast", () => ({ default: toast }));

// Interpolation is kept — `revokeConfirm` naming the client is the assertion.
const translate = (key: string, vars?: Record<string, unknown>) =>
  vars ? `${key} ${Object.values(vars).join(" ")}` : key;
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));

const role = { isAdmin: false };
vi.mock("../../../hooks/useRole", () => ({ useRole: () => role }));

const { McpClientsPage } = await import("./McpClientsPage");

const PROJECT = "11111111-2222-3333-4444-555555555555";

const token = (overrides: Partial<McpToken> = {}): McpToken => ({
  id: "token-1",
  name: "Claude Desktop",
  projectId: PROJECT,
  prefix: "cpmcp_A1b2C3d4",
  scopes: ["mcp:read"],
  createdAt: "2026-01-01T00:00:00Z",
  expiresAt: "2026-04-01T00:00:00Z",
  lastUsedAt: null,
  revokedAt: null,
  active: true,
  ownerId: "user-1",
  ownerName: "Sam",
  ...overrides,
});

const refused = (status: number, detail: string) => {
  const error = new Error("request failed") as Error & {
    response: { status: number; data: { detail: string } };
  };
  error.response = { status, data: { detail } };
  return error;
};

beforeEach(() => {
  vi.clearAllMocks();
  role.isAdmin = false;
  mcpApi.list.mockResolvedValue([token()]);
  projectsApi.list.mockResolvedValue({
    items: [{ id: PROJECT, name: "Marina Tower" }],
    data: [],
    total: 1,
    page: 1,
    limit: 200,
    totalPages: 1,
  });
});

afterEach(cleanup);

describe("McpClientsPage", () => {
  it("lists a token by name, prefix, project and access", async () => {
    render(<McpClientsPage />);
    expect(await screen.findByText("Claude Desktop")).toBeInTheDocument();
    expect(screen.getByText(/cpmcp_A1b2C3d4/)).toBeInTheDocument();
    expect(screen.getByText("Marina Tower")).toBeInTheDocument();
    expect(screen.getByText("mcpClients.scopeRead")).toBeInTheDocument();
    expect(mcpApi.list).toHaveBeenCalledWith(false);
  });

  it("distinguishes a token that may propose from one that may only read", async () => {
    mcpApi.list.mockResolvedValue([token({ scopes: ["mcp:read", "mcp:propose"] })]);
    render(<McpClientsPage />);
    expect(await screen.findByText("mcpClients.scopePropose")).toBeInTheDocument();
  });

  it("never renders a secret in the listing, because there is not one to render", async () => {
    render(<McpClientsPage />);
    await screen.findByText("Claude Desktop");
    // The prefix is not the credential: it is a fragment kept for recognition.
    expect(document.body.textContent).not.toMatch(/cpmcp_[A-Za-z0-9_-]{20,}/);
  });

  it("explains a switched-off surface instead of failing", async () => {
    mcpApi.list.mockRejectedValue(
      refused(503, "The MCP tool surface is not enabled on this server"),
    );
    render(<McpClientsPage />);
    expect(await screen.findByText("mcpClients.disabledTitle")).toBeInTheDocument();
    expect(
      screen.getByText("The MCP tool surface is not enabled on this server"),
    ).toBeInTheDocument();
    // A red toast for a deliberate deployment choice would read like a bug.
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("reports a real failure as a failure", async () => {
    mcpApi.list.mockRejectedValue(refused(500, "boom"));
    render(<McpClientsPage />);
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.queryByText("mcpClients.disabledTitle")).not.toBeInTheDocument();
  });

  it("asks before revoking, and names the client and its project", async () => {
    render(<McpClientsPage />);
    await userEvent.click(await screen.findByRole("button", { name: /mcpClients.revoke/ }));

    expect(
      screen.getByText(/mcpClients.revokeConfirm Claude Desktop Marina Tower/),
    ).toBeInTheDocument();
    expect(mcpApi.revoke).not.toHaveBeenCalled();

    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "mcpClients.revoke" }));
    await waitFor(() => expect(mcpApi.revoke).toHaveBeenCalledWith("token-1"));
    // Re-read afterwards, so the row's new status comes from the server.
    await waitFor(() => expect(mcpApi.list).toHaveBeenCalledTimes(2));
  });

  it("offers no revoke on a token that is already gone", async () => {
    mcpApi.list.mockResolvedValue([
      token({ active: false, revokedAt: "2026-02-01T00:00:00Z" }),
    ]);
    render(<McpClientsPage />);
    await screen.findByText("mcpClients.statusRevoked");
    expect(
      screen.queryByRole("button", { name: /mcpClients.revoke/ }),
    ).not.toBeInTheDocument();
  });

  it("asks the server for inactive tokens rather than filtering them here", async () => {
    render(<McpClientsPage />);
    await screen.findByText("Claude Desktop");
    await userEvent.click(screen.getByLabelText("mcpClients.showInactive"));
    await waitFor(() => expect(mcpApi.list).toHaveBeenCalledWith(true));
  });

  it("shows the secret once, inside a configuration a client can use as it stands", async () => {
    const secret = "cpmcp_thisIsTheOnlyTimeItExists0123456789";
    mcpApi.create.mockResolvedValue({
      token: secret,
      record: token({ id: "token-2", name: "Laptop" }),
      warning: "This is the only time the token is shown.",
    });

    render(<McpClientsPage />);
    await screen.findByText("Claude Desktop");
    await userEvent.click(screen.getByRole("button", { name: /mcpClients.new/ }));

    await userEvent.type(screen.getByLabelText("mcpClients.nameLabel"), "Laptop");
    await userEvent.selectOptions(screen.getByLabelText("mcpClients.projectLabel"), PROJECT);
    await userEvent.click(screen.getByRole("button", { name: "mcpClients.create" }));

    await waitFor(() =>
      expect(mcpApi.create).toHaveBeenCalledWith({
        name: "Laptop",
        projectId: PROJECT,
        // Read-only unless asked otherwise: a proposal is an AI suggesting a
        // change to somebody's project.
        scopes: ["mcp:read"],
      }),
    );

    // Translated, not the server's English `warning` — an Arabic reader being
    // told in English that they will never see their token again is the worst
    // possible moment for the interface to change language.
    expect(await screen.findByText("mcpClients.secretWarning")).toBeInTheDocument();
    const config = screen.getByText(/mcpServers/);
    expect(config).toHaveTextContent(`Bearer ${secret}`);
    expect(config).toHaveTextContent(`/mcp/projects/${PROJECT}`);
  });

  it("asks for the propose scope only when it was ticked", async () => {
    mcpApi.create.mockResolvedValue({
      token: "cpmcp_x",
      record: token(),
      warning: "once",
    });
    render(<McpClientsPage />);
    await screen.findByText("Claude Desktop");
    await userEvent.click(screen.getByRole("button", { name: /mcpClients.new/ }));

    await userEvent.type(screen.getByLabelText("mcpClients.nameLabel"), "Laptop");
    await userEvent.selectOptions(screen.getByLabelText("mcpClients.projectLabel"), PROJECT);
    await userEvent.click(screen.getByLabelText(/mcpClients.allowPropose/));
    await userEvent.click(screen.getByRole("button", { name: "mcpClients.create" }));

    await waitFor(() =>
      expect(mcpApi.create).toHaveBeenCalledWith(
        expect.objectContaining({ scopes: ["mcp:read", "mcp:propose"] }),
      ),
    );
  });

  it("is not still holding the last secret when the dialog reopens", async () => {
    const secret = "cpmcp_previousSecretShouldNotComeBack";
    mcpApi.create.mockResolvedValue({
      token: secret,
      record: token(),
      warning: "once",
    });
    render(<McpClientsPage />);
    await screen.findByText("Claude Desktop");

    await userEvent.click(screen.getByRole("button", { name: /mcpClients.new/ }));
    await userEvent.type(screen.getByLabelText("mcpClients.nameLabel"), "Laptop");
    await userEvent.selectOptions(screen.getByLabelText("mcpClients.projectLabel"), PROJECT);
    await userEvent.click(screen.getByRole("button", { name: "mcpClients.create" }));
    await screen.findByText(/mcpServers/);

    await userEvent.click(screen.getByRole("button", { name: "mcpClients.doneCopying" }));
    await userEvent.click(screen.getByRole("button", { name: /mcpClients.new/ }));

    expect(screen.queryByText(new RegExp(secret))).not.toBeInTheDocument();
    expect(screen.getByLabelText("mcpClients.nameLabel")).toHaveValue("");
  });

  it("leaves the lifetime to the server when the field is empty", async () => {
    mcpApi.create.mockResolvedValue({
      token: "cpmcp_x",
      record: token(),
      warning: "once",
    });
    render(<McpClientsPage />);
    await screen.findByText("Claude Desktop");
    await userEvent.click(screen.getByRole("button", { name: /mcpClients.new/ }));
    await userEvent.type(screen.getByLabelText("mcpClients.nameLabel"), "Laptop");
    await userEvent.selectOptions(screen.getByLabelText("mcpClients.projectLabel"), PROJECT);
    await userEvent.click(screen.getByRole("button", { name: "mcpClients.create" }));

    await waitFor(() => expect(mcpApi.create).toHaveBeenCalled());
    expect(mcpApi.create.mock.calls[0][0]).not.toHaveProperty("lifetimeDays");
  });

  it("names the owner only for an administrator looking at other people's", async () => {
    render(<McpClientsPage />);
    await screen.findByText("Claude Desktop");
    expect(screen.queryByText("mcpClients.columnOwner")).not.toBeInTheDocument();

    cleanup();
    role.isAdmin = true;
    render(<McpClientsPage />);
    expect(await screen.findByText("mcpClients.columnOwner")).toBeInTheDocument();
    expect(screen.getByText("Sam")).toBeInTheDocument();
  });
});
