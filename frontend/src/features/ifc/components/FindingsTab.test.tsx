// @vitest-environment jsdom
/**
 * The findings tab as a review surface rather than a read-only list.
 *
 * Until now a coordinator could see that a duct may pass through a beam and
 * could do nothing about it: the four review routes existed on the server and
 * nothing in the interface reached them. The assertions here are mostly about
 * what must *not* happen once they do — a decision must not be sent twice, a
 * failed call must not empty the list or invent a status the server refused,
 * and a button must never appear for somebody the endpoint would reject.
 *
 * "Show in 3D" is asserted at the seam it actually crosses: the tab hands
 * database element ids to the focus callback the workspace already owns. The
 * viewer itself is not rendered here — it is the workspace, not this tab, that
 * knows how to reach it, and that wiring is one line of prop plumbing.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import type { IFCFinding } from "../../../types/ifc";

const ifcApi = {
  findings: vi.fn(),
  reviewFinding: vi.fn(),
  ignoreFinding: vi.fn(),
  markFindingFalsePositive: vi.fn(),
  createIssueFromFinding: vi.fn(),
};

vi.mock("../../../services/api", () => ({ default: { ifc: ifcApi } }));

const toast = { success: vi.fn(), error: vi.fn() };
vi.mock("react-hot-toast", () => ({ default: toast }));

/**
 * One stable `t`, deliberately.
 *
 * The tab reloads its findings whenever `t` changes identity — that is how the
 * list re-renders in the newly selected language — so a mock that returned a
 * fresh function on every render would re-run the fetch after every state
 * change and overwrite the reviewed status with the original response.
 */
const translate = (key: string) => key;

vi.mock("react-i18next", async (importOriginal) => ({
  // The key is rendered verbatim: these assertions are about which controls a
  // person is offered and what they send, and the catalogue has its own
  // coverage tests. The rest of the module stays real because
  // `utils/errorMessage` pulls in the i18n bootstrap.
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));

const { FindingsTab } = await import("./IFCActionTabs");

const PROJECT = "project-1";
const VERSION = "version-1";

const finding = (overrides: Partial<IFCFinding> = {}): IFCFinding => ({
  id: "finding-1",
  versionId: VERSION,
  findingType: "MISSING_MATERIAL",
  severity: "MEDIUM",
  title: "Element materials are missing",
  description: "Material data is not defined for some extracted elements.",
  discipline: "STRUCTURAL",
  disciplines: ["STRUCTURAL"],
  status: "PENDING",
  ifcRule: "IFC_MATERIAL",
  whyItMatters: "Material information supports quantities and specifications.",
  recommendedAction: "Define materials in the source IFC where they are relevant.",
  // Database element ids, which is what `list_findings` puts in
  // `affectedElementIds` and what the viewer's focus mapping matches on.
  affectedElementIds: ["element-1", "element-2"],
  affectedElementCount: 2,
  createdAt: "2026-01-01T00:00:00Z",
  ...overrides,
});

/** The paged envelope `GET /ifc/findings` returns. */
const page = (items: IFCFinding[]) => ({ items, total: items.length, page: 1, pageSize: 50 });
const onViewElements = vi.fn();
const onFocus3D = vi.fn();

const show = (props: { canReview?: boolean; canCreateIssue?: boolean } = {}) =>
  render(
    <FindingsTab
      projectId={PROJECT}
      versionId={VERSION}
      canReview={props.canReview ?? true}
      canCreateIssue={props.canCreateIssue ?? true}
      onViewElements={onViewElements}
      onFocus3D={onFocus3D}
    />,
  );

/** The card, once the list request has resolved. */
const loaded = () => screen.findByText("Element materials are missing");

const button = (key: string) => screen.getByRole("button", { name: new RegExp(key.replace(/\./g, "\\."), "i") });
const maybeButton = (key: string) => screen.queryByRole("button", { name: new RegExp(key.replace(/\./g, "\\."), "i") });

beforeEach(() => {
  vi.clearAllMocks();
  ifcApi.findings.mockResolvedValue(page([finding()]));
  ifcApi.reviewFinding.mockResolvedValue({ status: "ACKNOWLEDGED" });
  ifcApi.ignoreFinding.mockResolvedValue({ status: "IGNORED" });
  ifcApi.markFindingFalsePositive.mockResolvedValue({ status: "FALSE_POSITIVE" });
  ifcApi.createIssueFromFinding.mockResolvedValue({ id: "issue-9", title: "Element materials are missing", status: "open" });
});

afterEach(cleanup);

describe("findings review actions", () => {
  it("offers every review decision to somebody who holds the permissions", async () => {
    show();
    await loaded();
    expect(button("ifcActions.acknowledge_finding")).toBeInTheDocument();
    expect(button("ifcActions.ignore_finding")).toBeInTheDocument();
    expect(button("ifcActions.mark_false_positive")).toBeInTheDocument();
    expect(button("ifcActions.create_issue_from_finding")).toBeInTheDocument();
  });

  it("sends an acknowledgement through the review route with the status the server accepts", async () => {
    show();
    await loaded();
    await userEvent.click(button("ifcActions.acknowledge_finding"));
    await waitFor(() => expect(ifcApi.reviewFinding).toHaveBeenCalledWith(PROJECT, "finding-1", "ACKNOWLEDGED"));
    expect(ifcApi.ignoreFinding).not.toHaveBeenCalled();
    expect(ifcApi.markFindingFalsePositive).not.toHaveBeenCalled();
  });

  it("uses the server's own shortcut route for ignore", async () => {
    show();
    await loaded();
    await userEvent.click(button("ifcActions.ignore_finding"));
    await waitFor(() => expect(ifcApi.ignoreFinding).toHaveBeenCalledWith(PROJECT, "finding-1"));
    expect(ifcApi.reviewFinding).not.toHaveBeenCalled();
  });

  it("uses the server's own shortcut route for a false positive", async () => {
    show();
    await loaded();
    await userEvent.click(button("ifcActions.mark_false_positive"));
    await waitFor(() => expect(ifcApi.markFindingFalsePositive).toHaveBeenCalledWith(PROJECT, "finding-1"));
    expect(ifcApi.reviewFinding).not.toHaveBeenCalled();
  });

  it("creates an issue through the create-issue route and names it in the confirmation", async () => {
    show();
    await loaded();
    await userEvent.click(button("ifcActions.create_issue_from_finding"));
    await waitFor(() => expect(ifcApi.createIssueFromFinding).toHaveBeenCalledWith(PROJECT, "finding-1"));
    expect(toast.success).toHaveBeenCalledWith("ifcActions.issue_created_from_finding");
  });
});

describe("findings state after a decision", () => {
  it("moves the card to the reviewed status without re-fetching the list", async () => {
    show();
    await loaded();
    expect(screen.getByText("PENDING")).toBeInTheDocument();

    await userEvent.click(button("ifcActions.acknowledge_finding"));

    await waitFor(() => expect(screen.getByText("ACKNOWLEDGED")).toBeInTheDocument());
    expect(screen.queryByText("PENDING")).toBeNull();
    // One request on mount and no reload: the severity and discipline filters
    // above the list would otherwise be reset by a refetch.
    expect(ifcApi.findings).toHaveBeenCalledTimes(1);
  });

  it("withdraws the review controls once the finding is no longer pending", async () => {
    show();
    await loaded();
    await userEvent.click(button("ifcActions.acknowledge_finding"));

    await waitFor(() => expect(maybeButton("ifcActions.acknowledge_finding")).toBeNull());
    expect(maybeButton("ifcActions.ignore_finding")).toBeNull();
    expect(maybeButton("ifcActions.create_issue_from_finding")).toBeNull();
  });

  it("records the status the server actually stored rather than the one requested", async () => {
    // The review routes return the ORM row, so the server is the authority on
    // what was written; the requested action is only the fallback.
    ifcApi.reviewFinding.mockResolvedValue({ status: "FALSE_POSITIVE" });
    show();
    await loaded();
    await userEvent.click(button("ifcActions.acknowledge_finding"));
    await waitFor(() => expect(screen.getByText("FALSE POSITIVE")).toBeInTheDocument());
  });

  it("shows a finding the server already reviewed without offering to review it again", async () => {
    ifcApi.findings.mockResolvedValue(page([finding({ status: "ISSUE_CREATED" })]));
    show();
    await loaded();
    expect(screen.getByText("ISSUE CREATED")).toBeInTheDocument();
    expect(maybeButton("ifcActions.acknowledge_finding")).toBeNull();
    expect(maybeButton("ifcActions.create_issue_from_finding")).toBeNull();
  });
});

describe("findings action failures", () => {
  it("reports a rejected action and leaves the finding as it was", async () => {
    ifcApi.reviewFinding.mockRejectedValue(new Error("Request failed"));
    show();
    await loaded();

    await userEvent.click(button("ifcActions.acknowledge_finding"));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Request failed"));
    expect(toast.success).not.toHaveBeenCalled();
    // The card survives, still pending, still reviewable.
    expect(screen.getByText("Element materials are missing")).toBeInTheDocument();
    expect(screen.getByText("PENDING")).toBeInTheDocument();
    expect(button("ifcActions.acknowledge_finding")).toBeEnabled();
  });

  it("keeps the other findings usable when one action fails", async () => {
    ifcApi.findings.mockResolvedValue(page([
      finding(),
      finding({ id: "finding-2", title: "Element names are missing" }),
    ]));
    ifcApi.reviewFinding.mockRejectedValue(new Error("Request failed"));
    show();
    await loaded();

    await userEvent.click(screen.getAllByRole("button", { name: /ifcActions\.acknowledge_finding/i })[0]);

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByText("Element names are missing")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /ifcActions\.acknowledge_finding/i })).toHaveLength(2);
  });

  it("does not send the same decision twice while the first call is still open", async () => {
    let release: (value: { status: string }) => void = () => undefined;
    ifcApi.reviewFinding.mockReturnValue(new Promise((resolve) => { release = resolve; }));
    show();
    await loaded();

    const acknowledge = button("ifcActions.acknowledge_finding");
    await userEvent.click(acknowledge);
    expect(acknowledge).toBeDisabled();
    // Every other decision on the card is closed too: a second one would race
    // the first against the status it is about to set.
    expect(button("ifcActions.create_issue_from_finding")).toBeDisabled();
    await userEvent.click(acknowledge);

    expect(ifcApi.reviewFinding).toHaveBeenCalledTimes(1);
    release({ status: "ACKNOWLEDGED" });
    await waitFor(() => expect(screen.getByText("ACKNOWLEDGED")).toBeInTheDocument());
  });
});

describe("showing a finding in 3D", () => {
  it("hands the workspace the finding's element ids so the existing viewer focus can select them", async () => {
    show();
    await loaded();
    await userEvent.click(button("ifcActions.show_in_3d"));
    expect(onFocus3D).toHaveBeenCalledWith(["element-1", "element-2"]);
  });

  it("stays available after the finding has been reviewed", async () => {
    // Deciding a finding is not a reason to stop being able to look at it.
    show();
    await loaded();
    await userEvent.click(button("ifcActions.acknowledge_finding"));
    await waitFor(() => expect(screen.getByText("ACKNOWLEDGED")).toBeInTheDocument());
    expect(button("ifcActions.show_in_3d")).toBeInTheDocument();
  });

  it("explains itself instead of offering a dead button when the finding names no element", async () => {
    ifcApi.findings.mockResolvedValue(page([finding({ affectedElementIds: [], affectedElementCount: 0 })]));
    show();
    await loaded();
    expect(maybeButton("ifcActions.show_in_3d")).toBeNull();
    expect(screen.getByText("ifcActions.finding_has_no_model_element")).toBeInTheDocument();
  });

  it("ignores blank element ids rather than focusing on nothing", async () => {
    ifcApi.findings.mockResolvedValue(page([finding({ affectedElementIds: ["", ""], affectedElementCount: 2 })]));
    show();
    await loaded();
    expect(maybeButton("ifcActions.show_in_3d")).toBeNull();
    expect(screen.getByText("ifcActions.finding_has_no_model_element")).toBeInTheDocument();
  });
});

describe("findings permissions", () => {
  it("offers no review decision at all without ifc.review_finding", async () => {
    show({ canReview: false });
    await loaded();
    expect(maybeButton("ifcActions.acknowledge_finding")).toBeNull();
    expect(maybeButton("ifcActions.ignore_finding")).toBeNull();
    expect(maybeButton("ifcActions.mark_false_positive")).toBeNull();
    expect(maybeButton("ifcActions.create_issue_from_finding")).toBeNull();
  });

  it("still lets a viewer read the finding and open it in 3D", async () => {
    show({ canReview: false, canCreateIssue: false });
    await loaded();
    expect(button("ifcActions.show_in_3d")).toBeInTheDocument();
    expect(button("ifcActions.view_affected_elements")).toBeInTheDocument();
  });

  it("withholds only the issue button when the caller cannot raise issues", async () => {
    // `finding_to_issue` checks `issue.create` on top of the IFC verb, so the
    // two permissions have to be offered independently.
    show({ canReview: true, canCreateIssue: false });
    await loaded();
    expect(maybeButton("ifcActions.create_issue_from_finding")).toBeNull();
    expect(button("ifcActions.acknowledge_finding")).toBeInTheDocument();
    expect(button("ifcActions.ignore_finding")).toBeInTheDocument();
    expect(button("ifcActions.mark_false_positive")).toBeInTheDocument();
  });
});
