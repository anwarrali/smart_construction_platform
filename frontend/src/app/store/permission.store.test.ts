// @vitest-environment jsdom
/**
 * QA-06B: inside a project the interface asks what the person may do *there*.
 * An administrator who is not on the team holds the project's team and
 * parties pages, not its tasks; the office-wide list said otherwise.
 */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mine = vi.fn();
vi.mock("../../features/admin/services/accessControl.service", () => ({ default: { mine } }));
vi.mock("./auth.store", () => ({
  useAuthStore: (select: (state: unknown) => unknown) =>
    select({ user: { id: "admin-1" }, isAuthenticated: true }),
}));

const { usePermissionStore } = await import("./permission.store");
const { usePermissions } = await import("../../hooks/usePermissions");

const OFFICE_WIDE = ["platform.manage_users", "project.manage_members", "task.view", "document.view"];
const IN_PROJECT = ["platform.manage_users", "project.manage_members"];

describe("project-scoped permissions", () => {
  beforeEach(() => {
    mine.mockReset();
    mine.mockImplementation(async (projectId?: string) => (projectId ? IN_PROJECT : OFFICE_WIDE));
    usePermissionStore.getState().clear();
  });
  afterEach(() => usePermissionStore.getState().clear());

  it("answers with the open project's permissions once they arrive", async () => {
    const { result } = renderHook(() => usePermissions());
    await act(async () => { await usePermissionStore.getState().fetch("admin-1"); });
    expect(result.current.hasPermission("task.view")).toBe(true);

    await act(async () => { await usePermissionStore.getState().enterProject("project-1"); });
    expect(mine).toHaveBeenLastCalledWith("project-1");
    expect(result.current.hasPermission("task.view")).toBe(false);
    expect(result.current.hasPermission("project.manage_members")).toBe(true);
    expect(result.current.isReady).toBe(true);

    act(() => usePermissionStore.getState().leaveProject());
    expect(result.current.hasPermission("task.view")).toBe(true);
  });

  it("is not ready until the open project's answer has arrived", async () => {
    let release: (codes: string[]) => void = () => undefined;
    const { result } = renderHook(() => usePermissions());
    await act(async () => { await usePermissionStore.getState().fetch("admin-1"); });
    mine.mockImplementationOnce(() => new Promise((done) => { release = done; }));

    let entering: Promise<void> = Promise.resolve();
    act(() => { entering = usePermissionStore.getState().enterProject("project-1"); });
    expect(result.current.isReady).toBe(false);

    await act(async () => { release(IN_PROJECT); await entering; });
    expect(result.current.isReady).toBe(true);
  });

  it("falls back to the office-wide answer if the project's cannot be loaded", async () => {
    const { result } = renderHook(() => usePermissions());
    await act(async () => { await usePermissionStore.getState().fetch("admin-1"); });
    mine.mockRejectedValueOnce(new Error("Network Error"));
    await act(async () => { await usePermissionStore.getState().enterProject("project-1"); });
    expect(result.current.isReady).toBe(true);
    expect(result.current.hasPermission("task.view")).toBe(true);
  });
});

/* 2026-10-23: a grant or revocation made while somebody is signed in reached
   their tab only after a reload. The snapshot is re-read on focus and on 403. */
describe("revalidation after a permission change", () => {
  beforeEach(() => {
    cleanup();
    usePermissionStore.getState().clear();
    mine.mockReset();
  });
  afterEach(() => { cleanup(); usePermissionStore.getState().clear(); });

  it("drops a revoked permission when the server answers 403", async () => {
    mine.mockResolvedValueOnce(["platform.create_project", "task.view"]);
    const { result } = renderHook(() => usePermissions());
    await act(async () => { await usePermissionStore.getState().fetch("admin-1"); });
    expect(result.current.hasPermission("platform.create_project")).toBe(true);

    mine.mockResolvedValue(["task.view"]);
    await act(async () => { window.dispatchEvent(new Event("permissions:stale")); });
    await vi.waitFor(() => expect(result.current.hasPermission("platform.create_project")).toBe(false));
    expect(result.current.hasPermission("task.view")).toBe(true);
  });

  it("shows a new grant when the tab regains focus, and keeps the old answer while it loads", async () => {
    mine.mockResolvedValueOnce(["task.view"]);
    const { result } = renderHook(() => usePermissions());
    await act(async () => { await usePermissionStore.getState().fetch("admin-1"); });

    let release: (codes: string[]) => void = () => undefined;
    mine.mockImplementationOnce(() => new Promise((done) => { release = done; }));
    act(() => { window.dispatchEvent(new Event("focus")); });
    // No blank state while the re-read is in flight.
    expect(result.current.isReady).toBe(true);
    expect(result.current.hasPermission("task.view")).toBe(true);

    await act(async () => { release(["task.view", "platform.create_project"]); });
    await vi.waitFor(() => expect(result.current.hasPermission("platform.create_project")).toBe(true));
  });

  it("keeps the previous answer if the re-read fails", async () => {
    mine.mockResolvedValueOnce(["task.view"]);
    const { result } = renderHook(() => usePermissions());
    await act(async () => { await usePermissionStore.getState().fetch("admin-1"); });
    mine.mockRejectedValueOnce(new Error("Network Error"));
    await act(async () => { await usePermissionStore.getState().revalidate(); });
    expect(result.current.hasPermission("task.view")).toBe(true);
  });

  it("does nothing before anybody has signed in", async () => {
    const before = mine.mock.calls.length;
    await usePermissionStore.getState().revalidate();
    expect(mine.mock.calls.length).toBe(before);
  });
});
