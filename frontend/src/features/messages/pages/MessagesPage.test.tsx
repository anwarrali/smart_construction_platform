// @vitest-environment jsdom
/**
 * Sending, and why it is unavailable (QA 2026-10-22).
 *
 * The announcement group list displayed "All Project Members" while its value
 * stayed empty, so Send never enabled — for an authorised project manager as
 * much as anyone. And a project the person may not message on answered 403,
 * which was swallowed into empty recipient lists: a Send button that could
 * never enable, with no reason given.
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const messages = {
  conversations: vi.fn(),
  recipientOptions: vi.fn(),
  conversation: vi.fn(),
  markConversationRead: vi.fn(),
  announce: vi.fn(),
  createConversation: vi.fn(),
};
let held = ["message.send", "message.broadcast"];

vi.mock("../../../services/api", () => ({ default: { messages, projects: { list: vi.fn(async () => ({ data: [] })) } } }));
vi.mock("react-hot-toast", () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));
vi.mock("../../../hooks/useAuth", () => ({ useAuth: () => ({ user: { id: "me" } }) }));
vi.mock("../../../hooks/useRole", () => ({ useRole: () => ({ hasCapability: (code: string) => held.includes(code) }) }));
vi.mock("../../../hooks/useRealtimeRefresh", () => ({ useRealtimeRefresh: () => undefined }));
vi.mock("../../projects/context/ProjectWorkspaceContext", () => ({
  useProjectWorkspace: () => ({ projectId: "p1", project: { name: "Villa" } }),
}));

const { MessagesPage } = await import("./MessagesPage");

const refused = { response: { status: 403, data: { detail: "You do not have access to this project" } } };

describe("messages — sending", () => {
  beforeEach(() => {
    held = ["message.send", "message.broadcast"];
    messages.conversations.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 100 });
    messages.recipientOptions.mockResolvedValue({ users: [{ id: "u2", fullName: "Rana" }], groups: [] });
    messages.announce.mockResolvedValue({ id: "c1" });
  });
  afterEach(() => { cleanup(); Object.values(messages).forEach((mock) => mock.mockReset()); });

  it("enables Send for an announcement as soon as there is a message", async () => {
    const user = userEvent.setup();
    render(<MessagesPage />);
    await user.click(await screen.findByRole("button", { name: "messagesPage.new_conversation" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("checkbox"));
    await user.type(within(dialog).getByRole("textbox", { name: "messagesPage.message" }), "Site closed Friday");

    const send = within(dialog).getByRole("button", { name: "messagesPage.send" }) as HTMLButtonElement;
    expect(send.disabled).toBe(false);
    await user.click(send);
    await waitFor(() => expect(messages.announce).toHaveBeenCalledWith("p1", "Site closed Friday", undefined, "ALL_PROJECT_MEMBERS"));
  });

  it("says why Send is unavailable instead of only disabling it", async () => {
    const user = userEvent.setup();
    render(<MessagesPage />);
    await user.click(await screen.findByRole("button", { name: "messagesPage.new_conversation" }));
    const dialog = await screen.findByRole("dialog");
    expect((within(dialog).getByRole("button", { name: "messagesPage.send" }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(dialog).getByRole("status").textContent).toBe("messagesPage.blocker_message");

    await user.type(within(dialog).getByRole("textbox", { name: "messagesPage.message" }), "Hello");
    expect(within(dialog).getByRole("status").textContent).toBe("messagesPage.blocker_recipient");
  });

  it("explains a refused project and offers no compose button", async () => {
    messages.recipientOptions.mockRejectedValue(refused);
    messages.conversations.mockRejectedValue(refused);
    render(<MessagesPage />);
    expect((await screen.findByRole("alert")).textContent).toBe("messagesPage.not_on_project_team");
    expect(screen.queryByRole("button", { name: "messagesPage.new_conversation" })).toBeNull();
  });
});
