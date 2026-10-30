// @vitest-environment jsdom
/**
 * The per-person permission editor shows the server's truth (2026-10-23).
 *
 * Each row separates three things an administrator kept confusing: the
 * effective answer (the server's resolved set), the explicit decision for this
 * person (allow / deny / inherits), and *why* — granted by the role, directly,
 * denied by an override, blocked because they are not on the project. After
 * a save the row shows what the server returned, and a failed save leaves the
 * previous state with an error rather than a success message.
 */

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { UserPermissionSummary } from "../services/accessControl.service";

const accessControlService = {
  permissions: vi.fn(), user: vi.fn(), setUserPermission: vi.fn(),
  consultants: vi.fn(), setConsultantScope: vi.fn(), mine: vi.fn(),
};
const toast = { success: vi.fn(), error: vi.fn() };

vi.mock("../services/accessControl.service", () => ({ accessControlService, default: accessControlService }));
vi.mock("react-hot-toast", () => ({ default: toast }));
// One stable `t`, as react-i18next provides: the page's loaders depend on it,
// so a new function per render would reload forever.
const t = (key: string, values?: Record<string, unknown>) =>
  values && "role" in values ? `${key}:${values.role}` : values && "name" in values ? `${key}:${values.name}` : key;
const translation = { t, i18n: { language: "en" } };
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => translation,
}));
vi.mock("../../../services/api", () => ({
  default: {
    users: { list: vi.fn(async () => [{ id: "rana", fullName: "Rana", email: "rana@x.io", status: "active" }]) },
    projects: { list: vi.fn(async () => ({ data: [] })), getMembers: vi.fn(), getEligibleMembers: vi.fn() },
  },
}));
const role = { refreshPermissions: vi.fn() };
vi.mock("../../../hooks/useRole", () => ({ useRole: () => role }));
// No step-up in this environment: the call goes straight through.
vi.mock("../../../hooks/useStepUp", () => ({ useStepUp: () => ({ run: (action: () => unknown) => action(), dialog: null }) }));
vi.mock("../../../utils/vocabulary", () => ({ useVocabulary: () => ({ orgRole: () => "Engineer" }) }));
vi.mock("../../../app/store/auth.store", () => ({
  useAuthStore: (select: (state: unknown) => unknown) => select({ user: { id: "admin" } }),
}));
vi.mock("react-router-dom", () => ({ Link: ({ children }: { children: unknown }) => children }));

const { AccessControlPage } = await import("./AccessControlPage");

const PERMISSIONS = [
  { code: "platform.create_project", group: "platform", label: "Create projects", description: "",
    projectScoped: false, adminLocked: false, officeOnly: false, neverExternal: false },
  { code: "issue.create", group: "issues", label: "Raise issues", description: "",
    projectScoped: true, adminLocked: false, officeOnly: false, neverExternal: false },
];

const summary = (overrides: Partial<UserPermissionSummary> = {}): UserPermissionSummary => ({
  userId: "rana", fullName: "Rana", email: "rana@x.io", roleName: "Engineer",
  governingRoleName: "Engineer", governedByOfficeCopy: true, status: "active",
  effectivePermissions: ["issue.create"], overrides: [],
  decisions: [
    { code: "platform.create_project", held: false, reason: "not_granted", roleGrants: false, override: null },
    { code: "issue.create", held: true, reason: "granted_by_role", roleGrants: true, override: null },
  ],
  ...overrides,
});

const openPerson = async () => {
  render(<AccessControlPage />);
  await userEvent.click(await screen.findByRole("tab", { name: "accessControl.tabs.people" }));
  const select = screen.getAllByRole("combobox")[0];
  await userEvent.selectOptions(select, "rana");
  await screen.findByTestId("reason-issue.create");
};

describe("per-person permission editor", () => {
  beforeEach(() => {
    Object.values(accessControlService).forEach((fn) => fn.mockReset());
    toast.success.mockReset();
    toast.error.mockReset();
    accessControlService.permissions.mockResolvedValue(PERMISSIONS);
    accessControlService.user.mockResolvedValue(summary());
  });
  afterEach(cleanup);

  it("explains each answer and names the office copy that governs", async () => {
    await openPerson();
    expect(screen.getByTestId("governing-role").textContent).toBe("accessControl.governedByOfficeCopy:Engineer");
    expect(screen.getByTestId("reason-issue.create").textContent).toBe("accessControl.reason.granted_by_role:Engineer");
    expect(screen.getByTestId("effective-issue.create").dataset.held).toBe("true");
    expect(screen.getByTestId("effective-platform.create_project").dataset.held).toBe("false");
    expect(within(screen.getByTestId("effective-issue.create")).getByText("accessControl.overrideInherit")).toBeTruthy();
  });

  it("shows the server's answer after a grant", async () => {
    accessControlService.setUserPermission.mockResolvedValue(summary({
      effectivePermissions: ["issue.create", "platform.create_project"],
      overrides: [{ id: "o1", userId: "rana", permissionCode: "platform.create_project", allowed: true }],
      decisions: [
        { code: "platform.create_project", held: true, reason: "granted_to_user", roleGrants: false, override: true },
        { code: "issue.create", held: true, reason: "granted_by_role", roleGrants: true, override: null },
      ],
    }));
    await openPerson();
    const row = screen.getByTestId("effective-platform.create_project").parentElement as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "accessControl.grant" }));

    expect(accessControlService.setUserPermission).toHaveBeenCalledWith("rana", "platform.create_project", true, null);
    await waitFor(() => expect(screen.getByTestId("effective-platform.create_project").dataset.held).toBe("true"));
    expect(screen.getByTestId("reason-platform.create_project").textContent)
      .toBe("accessControl.reason.granted_to_user:Engineer");
    expect(toast.success).toHaveBeenCalledWith("accessControl.personUpdated");
  });

  it("keeps the previous state and reports the error when a save fails", async () => {
    accessControlService.setUserPermission.mockRejectedValue(
      Object.assign(new Error("Forbidden"), { response: { status: 403, data: { detail: "Not allowed" } } }));
    await openPerson();
    const row = screen.getByTestId("effective-issue.create").parentElement as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "accessControl.revoke" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
    expect(screen.getByTestId("effective-issue.create").dataset.held).toBe("true");
  });

  it("explains a denial by a person-specific override", async () => {
    accessControlService.user.mockResolvedValue(summary({
      effectivePermissions: [],
      overrides: [{ id: "o2", userId: "rana", permissionCode: "issue.create", allowed: false }],
      decisions: [
        { code: "platform.create_project", held: false, reason: "not_granted", roleGrants: false, override: null },
        { code: "issue.create", held: false, reason: "denied_for_user", roleGrants: true, override: false },
      ],
    }));
    await openPerson();
    expect(screen.getByTestId("reason-issue.create").textContent).toBe("accessControl.reason.denied_for_user:Engineer");
    expect(within(screen.getByTestId("effective-issue.create")).getByText("accessControl.overrideDeny")).toBeTruthy();
  });
});
