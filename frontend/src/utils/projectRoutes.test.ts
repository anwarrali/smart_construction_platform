import { describe, expect, it } from "vitest";
import {
  canOpenProjectModule,
  portfolioProjectsPath,
  projectEntityPath,
  projectModulePath,
  projectWorkspaceBase,
  replaceProjectInPath,
} from "./projectRoutes";

const PROJECT = "11111111-2222-3333-4444-555555555555";
const TASK = "99999999-8888-7777-6666-555555555555";

describe("portfolioProjectsPath", () => {
  it("returns the workspace root that each role's guard actually serves", () => {
    expect(portfolioProjectsPath("project_manager")).toBe("/project-manager/projects");
    expect(portfolioProjectsPath("engineer")).toBe("/engineer/projects");
    expect(portfolioProjectsPath("engineer", "external_consultant")).toBe("/consultant-engineer/projects");
    expect(portfolioProjectsPath("owner")).toBe("/projects");
    expect(portfolioProjectsPath("admin")).toBe("/projects");
    expect(portfolioProjectsPath(undefined)).toBe("/projects");
  });
});

describe("projectWorkspaceBase", () => {
  it("keeps the project id inside the role-owned prefix", () => {
    expect(projectWorkspaceBase(PROJECT, "project_manager")).toBe(`/project-manager/projects/${PROJECT}`);
  });

  it("encodes ids so a malformed id cannot escape the segment", () => {
    expect(projectWorkspaceBase("a/b", "admin")).toBe("/projects/a%2Fb");
  });
});

describe("projectModulePath", () => {
  it("builds module links per role", () => {
    expect(projectModulePath(PROJECT, "tasks", "project_manager")).toBe(`/project-manager/projects/${PROJECT}/tasks`);
    expect(projectModulePath(PROJECT, "ifc", "engineer")).toBe(`/engineer/projects/${PROJECT}/ifc`);
    expect(projectModulePath(PROJECT, "reviews", "engineer", "external_consultant"))
      .toBe(`/consultant-engineer/projects/${PROJECT}/reviews`);
  });

  it("defaults to the project dashboard", () => {
    expect(projectModulePath(PROJECT, undefined, "owner")).toBe(`/projects/${PROJECT}/dashboard`);
  });

  it("tolerates a leading slash instead of producing a double slash", () => {
    expect(projectModulePath(PROJECT, "/tasks", "project_manager")).toBe(`/project-manager/projects/${PROJECT}/tasks`);
  });

  it("degrades to the dashboard rather than linking a role into a guard it fails", () => {
    // An owner has no task board; the old behaviour produced a redirect that
    // dropped the project id entirely.
    expect(projectModulePath(PROJECT, "tasks", "owner")).toBe(`/projects/${PROJECT}/dashboard`);
    expect(projectModulePath(PROJECT, "design-changes", "engineer")).toBe(`/engineer/projects/${PROJECT}/dashboard`);
  });
});

describe("canOpenProjectModule", () => {
  it("reflects the guards registered in the router", () => {
    expect(canOpenProjectModule("tasks", "project_manager")).toBe(true);
    expect(canOpenProjectModule("tasks", "owner")).toBe(false);
    expect(canOpenProjectModule("voice-reports", "engineer")).toBe(true);
    expect(canOpenProjectModule("voice-reports", "engineer", "external_consultant")).toBe(false);
    expect(canOpenProjectModule("reviews", "engineer", "external_consultant")).toBe(true);
    expect(canOpenProjectModule("design-changes", "owner")).toBe(true);
  });

  it("evaluates only the module root so deep segments stay allowed", () => {
    expect(canOpenProjectModule("tasks/abc", "project_manager")).toBe(true);
  });
});

describe("projectEntityPath", () => {
  it("addresses tasks by path segment", () => {
    expect(projectEntityPath(PROJECT, "TASK", TASK, "project_manager"))
      .toBe(`/project-manager/projects/${PROJECT}/tasks/${TASK}`);
  });

  it("uses the query parameter names the destination pages actually read", () => {
    expect(projectEntityPath(PROJECT, "ISSUE", "abc", "project_manager"))
      .toBe(`/project-manager/projects/${PROJECT}/issues?issueId=abc`);
    expect(projectEntityPath(PROJECT, "DESIGN_CHANGE", "abc", "project_manager"))
      .toBe(`/project-manager/projects/${PROJECT}/design-changes?changeId=abc`);
    expect(projectEntityPath(PROJECT, "SITE_REPORT", "abc", "project_manager"))
      .toBe(`/project-manager/projects/${PROJECT}/site-reports?reportId=abc`);
    expect(projectEntityPath(PROJECT, "DOCUMENT", "abc", "project_manager"))
      .toBe(`/project-manager/projects/${PROJECT}/documents?documentId=abc`);
  });

  it("accepts lower-case audit-log entity types", () => {
    expect(projectEntityPath(PROJECT, "owner_request", "abc", "project_manager"))
      .toBe(`/project-manager/projects/${PROJECT}/requests?requestId=abc`);
  });

  it("keeps an unmapped entity inside its project instead of leaving the workspace", () => {
    expect(projectEntityPath(PROJECT, "SOMETHING_NEW", "abc", "engineer"))
      .toBe(`/engineer/projects/${PROJECT}/activity`);
  });

  it("falls back to activity when the role cannot open the entity's module", () => {
    expect(projectEntityPath(PROJECT, "TASK", TASK, "engineer", "external_consultant"))
      .toBe(`/consultant-engineer/projects/${PROJECT}/activity`);
  });

  it("encodes entity ids", () => {
    expect(projectEntityPath(PROJECT, "ISSUE", "a b&c", "admin"))
      .toBe(`/projects/${PROJECT}/issues?issueId=a%20b%26c`);
  });

  it("returns the module itself when no entity id is available", () => {
    expect(projectEntityPath(PROJECT, "ISSUE", "", "admin")).toBe(`/projects/${PROJECT}/issues`);
  });
});

describe("replaceProjectInPath", () => {
  it("swaps the project while staying on the same module", () => {
    expect(replaceProjectInPath(`/project-manager/projects/${PROJECT}/tasks`, "next"))
      .toBe("/project-manager/projects/next/tasks");
    expect(replaceProjectInPath(`/engineer/projects/${PROJECT}/ifc`, "next"))
      .toBe("/engineer/projects/next/ifc");
    expect(replaceProjectInPath(`/consultant-engineer/projects/${PROJECT}/reviews`, "next"))
      .toBe("/consultant-engineer/projects/next/reviews");
    expect(replaceProjectInPath(`/projects/${PROJECT}/dashboard`, "next"))
      .toBe("/projects/next/dashboard");
  });

  it("preserves deep entity segments when switching project", () => {
    expect(replaceProjectInPath(`/project-manager/projects/${PROJECT}/tasks/${TASK}`, "next"))
      .toBe(`/project-manager/projects/next/tasks/${TASK}`);
  });
});
