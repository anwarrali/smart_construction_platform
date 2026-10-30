import { describe, expect, it } from "vitest";
import {
  portfolioMilestonesPath,
  canOpenProjectModule,
  portfolioProjectsPath,
  projectEntityPath,
  projectEntryPath,
  projectLandingModule,
  projectModulePath,
  projectWorkspaceBase,
  replaceProjectInPath,
} from "./projectRoutes";
import { sharedWorkspaceUrl } from "../app/router/LegacyProjectPrefixRedirect";

const PROJECT = "11111111-2222-3333-4444-555555555555";
const TASK = "99999999-8888-7777-6666-555555555555";

/** Stand-in for `useRole().hasCapability`. */
const holding = (...codes: string[]) => (code: string) => codes.includes(code);
const holdingNothing = () => false;

const EVERYTHING = holding(
  "task.view", "task.view_all", "document.view", "site_report.view", "issue.view",
  "design_change.view", "schedule.view", "ifc.view", "ai.view_insights",
  "task.review", "field_evidence.verify", "project.manage_members",
  "project.manage_parties",
);

describe("portfolioProjectsPath", () => {
  it("is one address, because there is one workspace", () => {
    expect(portfolioProjectsPath()).toBe("/projects");
  });
});

describe("projectWorkspaceBase", () => {
  it("puts every project under the shared prefix", () => {
    expect(projectWorkspaceBase(PROJECT)).toBe(`/projects/${PROJECT}`);
  });

  it("encodes ids so a malformed id cannot escape the segment", () => {
    expect(projectWorkspaceBase("a/b")).toBe("/projects/a%2Fb");
  });
});

// QA-06B: an administrator who is not on a project holds its team and parties
// pages, not its work. Their links into the project must land on what they can open.
describe("projectLandingModule", () => {
  const registryOnly = (code: string) => ["project.manage_members", "project.manage_parties"].includes(code);

  it("is the overview for anyone who works in the project", () => {
    expect(projectLandingModule(EVERYTHING)).toBe("dashboard");
  });

  it("is the team page for someone who only administers the project", () => {
    expect(projectLandingModule(registryOnly)).toBe("team");
    expect(projectLandingModule((code) => code === "project.manage_parties")).toBe("parties");
    expect(projectModulePath(PROJECT, "tasks", registryOnly)).toBe(`/projects/${PROJECT}/team`);
  });

  it("is the overview while nothing is known", () => {
    expect(projectLandingModule()).toBe("dashboard");
    expect(projectLandingModule(() => false)).toBe("dashboard");
  });
});

// QA 2026-10-22: the Projects page's "Open" went to the bare project address,
// which for an administrator not on the team ended on the portfolio dashboard.
describe("projectEntryPath", () => {
  const ADMIN = holding("task.view", "task.view_all", "project.manage_members", "project.manage_parties");

  it("opens a project whose work you can open on its overview", () => {
    expect(projectEntryPath({ id: PROJECT, canOpenWork: true }, ADMIN)).toBe(`/projects/${PROJECT}/dashboard`);
  });

  it("opens a project you only administer on its team, whatever your office-wide permissions", () => {
    expect(projectEntryPath({ id: PROJECT, canOpenWork: false }, ADMIN)).toBe(`/projects/${PROJECT}/team`);
    expect(projectEntryPath({ id: PROJECT, canOpenWork: false }, holding("project.manage_parties")))
      .toBe(`/projects/${PROJECT}/parties`);
  });

  it("sends somebody who can open nothing of it back to the list", () => {
    expect(projectEntryPath({ id: PROJECT, canOpenWork: false }, holding("task.view"))).toBe("/projects");
  });

  it("treats an older payload without the flag as workable", () => {
    expect(projectEntryPath({ id: PROJECT }, holding("task.view"))).toBe(`/projects/${PROJECT}/my-work`);
  });
});

describe("projectModulePath", () => {
  it("builds module links without asking who is looking", () => {
    expect(projectModulePath(PROJECT, "tasks", EVERYTHING)).toBe(`/projects/${PROJECT}/tasks`);
    expect(projectModulePath(PROJECT, "ifc", EVERYTHING)).toBe(`/projects/${PROJECT}/ifc`);
    expect(projectModulePath(PROJECT, "reviews", EVERYTHING)).toBe(`/projects/${PROJECT}/reviews`);
  });

  it("defaults to the project dashboard", () => {
    expect(projectModulePath(PROJECT, undefined, EVERYTHING)).toBe(`/projects/${PROJECT}/dashboard`);
  });

  it("tolerates a leading slash instead of producing a double slash", () => {
    expect(projectModulePath(PROJECT, "/tasks", EVERYTHING)).toBe(`/projects/${PROJECT}/tasks`);
  });

  it("degrades to the dashboard rather than linking into a guard the reader fails", () => {
    // Somebody without `task.review` must not be handed a review-queue link
    // that immediately bounces them and drops the project id on the way.
    const noReview = holding("task.view", "task.view_all");
    expect(projectModulePath(PROJECT, "review-queue", noReview)).toBe(`/projects/${PROJECT}/dashboard`);
  });

  // QA 2026-10-22: the overview's endpoint requires `task.view_all`. An
  // engineer (assigned work only) was offered it and refused with "Open your
  // own work for assigned-task metrics"; they land on their own work instead.
  it("sends somebody who sees only their own work to it, not to the overview", () => {
    const engineer = holding("task.view", "task.review");
    expect(projectLandingModule(engineer)).toBe("my-work");
    expect(projectModulePath(PROJECT, "dashboard", engineer)).toBe(`/projects/${PROJECT}/my-work`);
    expect(canOpenProjectModule("dashboard", engineer)).toBe(false);
  });

  it("links optimistically while permissions are still loading", () => {
    // No `hasPermission` means the answer has not arrived. Producing the link
    // and letting the router redirect is better than hiding navigation from
    // somebody who does hold the permission.
    expect(projectModulePath(PROJECT, "review-queue")).toBe(`/projects/${PROJECT}/review-queue`);
  });
});

describe("canOpenProjectModule", () => {
  it("asks the permission each route is actually guarded by", () => {
    expect(canOpenProjectModule("tasks", holding("task.view"))).toBe(true);
    expect(canOpenProjectModule("tasks", holdingNothing)).toBe(false);
    expect(canOpenProjectModule("documents", holding("document.view"))).toBe(true);
    expect(canOpenProjectModule("documents", holding("task.view"))).toBe(false);
    expect(canOpenProjectModule("reviews", holding("task.review"))).toBe(true);
    expect(canOpenProjectModule("voice-reports", holding("field_evidence.verify"))).toBe(true);
  });

  it("refuses a module the workspace does not register at all", () => {
    expect(canOpenProjectModule("not-a-module", EVERYTHING)).toBe(false);
  });

  it("evaluates only the module root so deep segments stay allowed", () => {
    expect(canOpenProjectModule("tasks/abc", holding("task.view"))).toBe(true);
  });
});

describe("projectEntityPath", () => {
  it("addresses tasks by path segment", () => {
    expect(projectEntityPath(PROJECT, "TASK", TASK, EVERYTHING))
      .toBe(`/projects/${PROJECT}/tasks/${TASK}`);
  });

  it("uses the query parameter names the destination pages actually read", () => {
    expect(projectEntityPath(PROJECT, "ISSUE", "abc", EVERYTHING))
      .toBe(`/projects/${PROJECT}/issues?issueId=abc`);
    expect(projectEntityPath(PROJECT, "DESIGN_CHANGE", "abc", EVERYTHING))
      .toBe(`/projects/${PROJECT}/design-changes?changeId=abc`);
    expect(projectEntityPath(PROJECT, "SITE_REPORT", "abc", EVERYTHING))
      .toBe(`/projects/${PROJECT}/site-reports?reportId=abc`);
    expect(projectEntityPath(PROJECT, "DOCUMENT", "abc", EVERYTHING))
      .toBe(`/projects/${PROJECT}/documents?documentId=abc`);
  });

  it("accepts lower-case audit-log entity types", () => {
    expect(projectEntityPath(PROJECT, "owner_request", "abc", EVERYTHING))
      .toBe(`/projects/${PROJECT}/requests?requestId=abc`);
  });

  it("keeps an unmapped entity inside its project instead of leaving the workspace", () => {
    expect(projectEntityPath(PROJECT, "SOMETHING_NEW", "abc", EVERYTHING))
      .toBe(`/projects/${PROJECT}/activity`);
  });

  it("falls back to activity when the reader cannot open the entity's module", () => {
    expect(projectEntityPath(PROJECT, "DOCUMENT", "abc", holding("task.view")))
      .toBe(`/projects/${PROJECT}/activity`);
  });

  it("encodes entity ids", () => {
    expect(projectEntityPath(PROJECT, "ISSUE", "a b&c", EVERYTHING))
      .toBe(`/projects/${PROJECT}/issues?issueId=a%20b%26c`);
  });

  it("returns the module itself when no entity id is available", () => {
    expect(projectEntityPath(PROJECT, "ISSUE", "", EVERYTHING)).toBe(`/projects/${PROJECT}/issues`);
  });
});

describe("replaceProjectInPath", () => {
  it("swaps the project while staying on the same module", () => {
    expect(replaceProjectInPath(`/projects/${PROJECT}/dashboard`, "next"))
      .toBe("/projects/next/dashboard");
  });

  it("rewrites a retired prefix onto the shared one instead of duplicating the id", () => {
    expect(replaceProjectInPath(`/project-manager/projects/${PROJECT}/tasks`, "next"))
      .toBe("/projects/next/tasks");
    expect(replaceProjectInPath(`/engineer/projects/${PROJECT}/ifc`, "next"))
      .toBe("/projects/next/ifc");
    expect(replaceProjectInPath(`/consultant-engineer/projects/${PROJECT}/reviews`, "next"))
      .toBe("/projects/next/reviews");
  });

  it("preserves deep entity segments when switching project", () => {
    expect(replaceProjectInPath(`/projects/${PROJECT}/tasks/${TASK}`, "next"))
      .toBe(`/projects/next/tasks/${TASK}`);
  });
});

/**
 * The deep-link guarantee.
 *
 * Every URL the retired prefixes ever produced is already out in the world —
 * in delivered push notifications, in e-mail, in bookmarks, in history. A 404
 * on any of them is a regression, so the rewrite is asserted here rather than
 * left to be discovered in somebody's notification.
 */
describe("sharedWorkspaceUrl", () => {
  it("rewrites each retired prefix onto the shared workspace", () => {
    expect(sharedWorkspaceUrl(`/project-manager/projects/${PROJECT}/tasks`))
      .toBe(`/projects/${PROJECT}/tasks`);
    expect(sharedWorkspaceUrl(`/engineer/projects/${PROJECT}/site-reports`))
      .toBe(`/projects/${PROJECT}/site-reports`);
    expect(sharedWorkspaceUrl(`/consultant-engineer/projects/${PROJECT}/documents`))
      .toBe(`/projects/${PROJECT}/documents`);
  });

  it("preserves deep segments, query strings and hashes", () => {
    expect(sharedWorkspaceUrl(`/project-manager/projects/${PROJECT}/tasks/${TASK}`))
      .toBe(`/projects/${PROJECT}/tasks/${TASK}`);
    expect(sharedWorkspaceUrl(`/engineer/projects/${PROJECT}/issues`, "?issueId=abc"))
      .toBe(`/projects/${PROJECT}/issues?issueId=abc`);
    expect(sharedWorkspaceUrl(`/consultant-engineer/projects/${PROJECT}/reviews`, "", "#top"))
      .toBe(`/projects/${PROJECT}/reviews#top`);
  });

  it("moves the two module words that meant different pages per prefix", () => {
    // `dashboard` was the project overview, the engineer's own work list, or
    // the review queue, depending on which prefix it hung off. Each keeps its
    // destination.
    expect(sharedWorkspaceUrl(`/engineer/projects/${PROJECT}/dashboard`))
      .toBe(`/projects/${PROJECT}/my-work`);
    expect(sharedWorkspaceUrl(`/consultant-engineer/projects/${PROJECT}/dashboard`))
      .toBe(`/projects/${PROJECT}/review-queue`);
    expect(sharedWorkspaceUrl(`/project-manager/projects/${PROJECT}/dashboard`))
      .toBe(`/projects/${PROJECT}/dashboard`);
  });

  it("sends a bare retired portfolio prefix to the shared portfolio", () => {
    expect(sharedWorkspaceUrl("/engineer/projects")).toBe("/projects");
    expect(sharedWorkspaceUrl("/project-manager/projects")).toBe("/projects");
  });

  it("returns null for a path that was never one of the retired prefixes", () => {
    expect(sharedWorkspaceUrl(`/projects/${PROJECT}/tasks`)).toBeNull();
    expect(sharedWorkspaceUrl("/notifications")).toBeNull();
  });
});

describe("portfolioMilestonesPath", () => {
  // The manager dashboard's milestone entry used `ROUTES.SCHEDULE` ("/schedule"),
  // which is the collaboration site-visit calendar.
  it("opens a project's milestones, never the site-visit calendar", () => {
    const path = portfolioMilestonesPath(["p-1", "p-2"], () => true);
    expect(path).toBe("/projects/p-1/milestones");
    expect(path).not.toBe("/schedule");
  });

  it("falls back to the project overview without schedule.view", () => {
    expect(portfolioMilestonesPath(["p-1"], (code) => code !== "schedule.view")).toBe("/projects/p-1/dashboard");
  });

  it("goes to the project list when the manager has no project yet", () => {
    expect(portfolioMilestonesPath([], () => true)).toBe("/projects");
  });
});
