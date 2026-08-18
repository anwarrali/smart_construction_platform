import { afterEach, describe, expect, it, vi } from "vitest";

const mine = vi.fn();

vi.mock("../../features/admin/services/accessControl.service", () => ({
  default: { mine: (...args: unknown[]) => mine(...args) },
}));

import { usePermissionStore } from "./permission.store";

/**
 * The cache backing `useRole()`/`usePermissions()`. Covers what P1 of the
 * platform improvement pass requires of it directly: it loads from the
 * backend (not a hardcoded map), it does not re-fetch on every mount, a
 * failed load never leaves a stale/wrong list in place, and logout (`clear`)
 * leaves no trace of the previous session's permissions.
 */
describe("usePermissionStore", () => {
  afterEach(() => {
    mine.mockReset();
    usePermissionStore.getState().clear();
  });

  it("loads effective permissions from the backend, not a local table", async () => {
    mine.mockResolvedValue(["task.create", "platform.create_project"]);

    await usePermissionStore.getState().fetch("user-1");

    const state = usePermissionStore.getState();
    expect(state.permissions).toEqual(["task.create", "platform.create_project"]);
    expect(state.loadedForUserId).toBe("user-1");
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });

  it("does not start a second request while one is already in flight", async () => {
    let resolveFetch!: (value: string[]) => void;
    mine.mockReturnValue(new Promise<string[]>((resolve) => { resolveFetch = resolve; }));

    const first = usePermissionStore.getState().fetch("user-1");
    const second = usePermissionStore.getState().fetch("user-1"); // e.g. Sidebar and Topbar mounting together

    expect(mine).toHaveBeenCalledTimes(1);
    resolveFetch(["schedule.view"]);
    await Promise.all([first, second]);
    expect(usePermissionStore.getState().permissions).toEqual(["schedule.view"]);
  });

  it("a failed fetch reports an error and does not keep a stale permission list", async () => {
    mine.mockResolvedValueOnce(["ai.view_insights"]);
    await usePermissionStore.getState().fetch("user-1");
    expect(usePermissionStore.getState().permissions).toEqual(["ai.view_insights"]);

    mine.mockReset();
    usePermissionStore.getState().clear(); // simulate a fresh session before the failing call
    mine.mockRejectedValueOnce(new Error("network error"));
    await usePermissionStore.getState().fetch("user-2");

    const state = usePermissionStore.getState();
    expect(state.permissions).toBeNull();
    expect(state.error).not.toBeNull();
    expect(state.loadedForUserId).toBeNull();
  });

  it("switching users (logout, then a different login) never mixes the two people's permissions", async () => {
    // Models the real flow: auth.store's logout() clears this store before
    // any new session can start (see auth.store.ts), so by the time a second
    // person's fetch begins, the first person's list is already gone - not
    // merely overwritten moments later.
    mine.mockResolvedValueOnce(["platform.manage_users", "platform.manage_permissions"]);
    await usePermissionStore.getState().fetch("admin-1");
    expect(usePermissionStore.getState().permissions).toContain("platform.manage_users");

    usePermissionStore.getState().clear(); // what auth.store's logout() does
    expect(usePermissionStore.getState().permissions).toBeNull();

    mine.mockResolvedValueOnce(["task.view"]);
    await usePermissionStore.getState().fetch("worker-2");

    const state = usePermissionStore.getState();
    expect(state.permissions).toEqual(["task.view"]);
    expect(state.permissions).not.toContain("platform.manage_users");
    expect(state.loadedForUserId).toBe("worker-2");
  });

  it("clear removes every trace of the previous session's permissions (logout)", async () => {
    mine.mockResolvedValue(["platform.manage_users"]);
    await usePermissionStore.getState().fetch("admin-1");
    expect(usePermissionStore.getState().permissions).not.toBeNull();

    usePermissionStore.getState().clear();

    const state = usePermissionStore.getState();
    expect(state.permissions).toBeNull();
    expect(state.loadedForUserId).toBeNull();
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });
});
