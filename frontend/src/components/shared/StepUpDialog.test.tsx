// @vitest-environment jsdom
/**
 * The development code echo (QA 2026-10-22). A backend started with
 * OTP_DEV_ECHO_ENABLED in a declared development environment returns the code
 * so local QA can run without email; anywhere else it refuses to boot. The
 * dialog fills the code in and says so — and shows nothing extra otherwise.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const request = vi.fn();
vi.mock("../../services/api", () => ({ default: { stepUp: { request, verify: vi.fn() } } }));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) => (values?.code ? `${key}:${values.code}` : key),
    i18n: { language: "en" },
  }),
}));

const { StepUpDialog } = await import("./StepUpDialog");

const challenge = (extra: Record<string, unknown> = {}) => ({
  purpose: "admin.change_permissions", label: "Change roles and permissions",
  expiresAt: new Date(Date.now() + 600_000).toISOString(), maxAttempts: 5,
  resendAfterSeconds: 60, delivered: false, ...extra,
});

describe("StepUpDialog development code", () => {
  afterEach(() => { cleanup(); request.mockReset(); });

  it("fills in and announces an echoed development code", async () => {
    request.mockResolvedValue(challenge({ devCode: "482913" }));
    render(<StepUpDialog purpose="admin.change_permissions" label="Change" onVerified={vi.fn()} onCancel={vi.fn()} />);
    expect((await screen.findByRole("note")).textContent).toBe("stepUp.devCode:482913");
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("482913");
  });

  it("leaves the code empty and shows no development note without an echo", async () => {
    request.mockResolvedValue(challenge());
    render(<StepUpDialog purpose="admin.change_permissions" label="Change" onVerified={vi.fn()} onCancel={vi.fn()} />);
    await screen.findByText("stepUp.deliveryUnavailable");
    expect(screen.queryByRole("note")).toBeNull();
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("");
  });
});
