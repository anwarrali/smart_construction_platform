/**
 * The navigation model: which destinations a person is offered, and which one
 * is lit. The rail draws exactly this, so these cases are the menu each kind
 * of participant actually sees.
 */

import { describe, expect, it } from "vitest";

import { dashboardRoute, isItemActive, portfolioNavigation, projectNavigation, type NavGroup } from "./navigation";

const t = (key: string) => key;
const PROJECT = "3563ff46-fb97-47b7-a5ae-2eeb8bafbe34";
const path = (module: string) => `/projects/${PROJECT}/${module}`;
const holding = (...codes: string[]) => (code?: string) => !code || codes.includes(code);
const ids = (groups: NavGroup[]) => groups.flatMap((group) => group.items.map((item) => item.id));

// Default grants of the seeded role templates (see docs/RBAC). The model never
// sees these names — only the permission codes.
const ADMIN = holding(
  "platform.manage_users", "platform.manage_permissions", "org.manage_roles", "client_portal.view",
  "project.manage_members", "task.view", "task.view_all", "task.review", "document.view", "schedule.view",
  "issue.view", "design_change.view", "site_report.view", "ifc.view", "ai.view_insights",
);
const CONTRACTOR = holding("task.view", "document.view", "issue.view", "design_change.view", "site_report.view", "ifc.view");
const CLIENT = holding("task.view", "task.view_all", "document.view", "schedule.view", "client_portal.view", "ifc.view");

describe("portfolio navigation", () => {
  it("gives an administrator the administration group and one dashboard", () => {
    const groups = portfolioNavigation(t, ADMIN, true);
    expect(ids(groups)).toEqual([
      "dashboard", "projects", "tasks", "coordination", "documents", "messages",
      "executive", "people", "teams", "permissions", "roles",
    ]);
    expect(groups[0].items[0].to).toBe("/admin");
  });

  it("offers a contractor no administration at all", () => {
    const groups = portfolioNavigation(t, CONTRACTOR, false);
    expect(groups.map((group) => group.id)).toEqual(["work"]);
    expect(ids(groups)).not.toContain("people");
  });

  // QA 2026-10-22: an administrator on no project team was offered pages that
  // gather project work and could only come back empty or refused.
  it("offers portfolio work pages only to somebody who works in a project", () => {
    const working = ids(portfolioNavigation(t, ADMIN, true, true));
    expect(working).toEqual(expect.arrayContaining(["tasks", "coordination", "documents", "messages", "executive"]));
    const administering = ids(portfolioNavigation(t, ADMIN, true, false));
    for (const id of ["tasks", "coordination", "documents", "messages", "executive"]) {
      expect(administering).not.toContain(id);
    }
    // Administration and the project registry stay.
    expect(administering).toEqual(expect.arrayContaining(["dashboard", "projects", "people", "teams", "permissions", "roles"]));
  });

  it("sends an external client's dashboard to the owner overview", () => {
    expect(dashboardRoute(CLIENT, false)).toBe("/owner-dashboard");
    // …and does not list that overview a second time under administration.
    expect(ids(portfolioNavigation(t, CLIENT, false))).not.toContain("executive");
  });

  it("keeps an internal person without client access on the work dashboard", () => {
    expect(dashboardRoute(CONTRACTOR, true)).toBe("/dashboard");
  });
});

describe("project navigation", () => {
  it("shows a contractor its work but not review, schedule or team management", () => {
    const visible = ids(projectNavigation(t, CONTRACTOR, path));
    expect(visible).toEqual(expect.arrayContaining(["my-work", "tasks", "issues", "documents", "ifc", "coordination"]));
    // The overview is project-wide metrics (`task.view_all`); a contractor
    // sees only its own work, and the overview's endpoint refuses it.
    expect(visible).not.toContain("overview");
    expect(visible).not.toContain("reviews");
    expect(visible).not.toContain("schedule");
    expect(visible).not.toContain("team");
    expect(visible).not.toContain("parties");
  });

  it("lists Milestones under Work, next to Tasks, for whoever may read the schedule", () => {
    const work = projectNavigation(t, ADMIN, path).find((group) => group.id === "work")!;
    const ids = work.items.map((item) => item.id);
    expect(ids.indexOf("milestones")).toBe(ids.indexOf("tasks") + 1);
    expect(work.items.find((item) => item.id === "milestones")!.to).toBe(path("milestones"));
    // The route is guarded by schedule.view; the entry follows the same rule.
    expect(ids).not.toContain(undefined);
    const contractorWork = projectNavigation(t, CONTRACTOR, path).flatMap((group) => group.items.map((item) => item.id));
    expect(contractorWork).not.toContain("milestones");
  });

  it("drops a group entirely when none of its entries are allowed", () => {
    const groups = projectNavigation(t, holding("task.view"), path);
    expect(groups.map((group) => group.id)).not.toContain("control");
    expect(groups.map((group) => group.id)).not.toContain("documents");
  });

  // QA pass 2026-10-17, defect 7: Agents used to follow task.view, so every
  // engineer saw it. It is granted explicitly now; the route and API agree.
  it("offers Agents only to someone granted agents.view", () => {
    expect(ids(projectNavigation(t, holding("task.view", "ai.view_insights"), path))).not.toContain("agents");
    expect(ids(projectNavigation(t, CONTRACTOR, path))).not.toContain("agents");
    const granted = projectNavigation(t, holding("task.view", "agents.view"), path).flatMap((group) => group.items);
    expect(granted.find((item) => item.id === "agents")?.to).toBe(path("agents"));
  });

  it("lists every destination once — tab routes are not separate entries", () => {
    const visible = ids(projectNavigation(t, ADMIN, path));
    expect(new Set(visible).size).toBe(visible.length);
    for (const tab of ["requests", "site-visits", "activity", "collaboration"]) {
      expect(visible).not.toContain(tab);
    }
  });
});

describe("isItemActive", () => {
  const groups = projectNavigation(t, ADMIN, path);
  const item = (id: string) => groups.flatMap((group) => group.items).find((entry) => entry.id === id)!;

  it("lights Coordination on each of its tab routes", () => {
    for (const module of ["collaboration", "requests", "site-visits", "activity"]) {
      expect(isItemActive(item("coordination"), path(module), PROJECT)).toBe(true);
    }
  });

  it("lights an entry on its record pages", () => {
    expect(isItemActive(item("tasks"), `${path("tasks")}/abc`, PROJECT)).toBe(true);
    expect(isItemActive(item("reviews"), path("history"), PROJECT)).toBe(true);
  });

  it("does not light the overview everywhere beneath it", () => {
    expect(isItemActive(item("overview"), path("dashboard"), PROJECT)).toBe(true);
    expect(isItemActive(item("overview"), path("tasks"), PROJECT)).toBe(false);
  });

  it("matches portfolio tab routes by full path", () => {
    const coordination = portfolioNavigation(t, ADMIN, true)[0].items.find((entry) => entry.id === "coordination")!;
    expect(isItemActive(coordination, "/requests", undefined)).toBe(true);
    expect(isItemActive(coordination, "/projects", undefined)).toBe(false);
  });
});
