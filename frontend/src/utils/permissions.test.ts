import { describe, expect, it } from "vitest";

import { resolvePermission } from "./permissions";

/**
 * `resolvePermission` is the hybrid decision `useRole().checkPermission`
 * makes: prefer the backend's effective-permission list once it has loaded
 * for anything the catalogue maps, otherwise fall back to the static role
 * table. These pin the properties that matter for P1 of the platform
 * improvement pass — the frontend must reflect what an administrator has
 * actually configured, not just the role someone was born into.
 */
describe("resolvePermission", () => {
  it("denies everything when there is no authenticated role", () => {
    expect(resolvePermission(undefined, "create_project", null)).toBe(false);
    expect(resolvePermission(undefined, "create_project", ["platform.create_project"])).toBe(false);
  });

  it("falls back to the static role table before the backend list has loaded", () => {
    // effectivePermissions === null means "not fetched yet", not "loaded, empty".
    expect(resolvePermission("admin", "create_project", null)).toBe(true);
    expect(resolvePermission("engineer", "create_project", null)).toBe(false);
  });

  it("a revoked permission disappears once the backend list has loaded, even for a role that defaults to it", () => {
    // Static table grants admins create_project; an administrator revoking
    // platform.create_project from the Admin role must be reflected here.
    expect(resolvePermission("admin", "create_project", [])).toBe(false);
  });

  it("a granted permission becomes available once the backend list has loaded, even for a role that defaults away from it", () => {
    // Static table does not grant Engineers create_task; a per-user or
    // per-role grant of task.create must surface here regardless.
    expect(resolvePermission("engineer", "create_task", ["task.create"])).toBe(true);
  });

  it("backend remains authoritative in both directions for the same mapped action", () => {
    expect(resolvePermission("project_manager", "manage_issues", ["issue.resolve"])).toBe(true);
    expect(resolvePermission("project_manager", "manage_issues", [])).toBe(false);
  });

  it("keeps the static, ownership-aware answer for actions the catalogue does not model with a plain role check", () => {
    // edit_task/update_task_status are PM-of-this-project-or-assignee checks
    // on the server, not role checks — BACKEND_PERMISSION_CODE deliberately
    // has no entry for them, so an empty (loaded) backend list must not
    // suppress the static answer the way it does for a genuinely mapped code.
    expect(resolvePermission("project_manager", "edit_task", [])).toBe(true);
    expect(resolvePermission("worker", "edit_task", [])).toBe(false);
  });
});
