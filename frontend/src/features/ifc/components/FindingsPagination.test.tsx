// @vitest-environment jsdom
/**
 * Paging the findings queue, and the filters that have to move with it.
 *
 * The endpoint used to return every finding in the project — all revisions,
 * unbounded — and the tab threw away all but the current revision in the
 * browser. Now the revision, the severity and the discipline are all sent to
 * the server, which returns one page.
 *
 * That makes two things load-bearing, and both are asserted here: the filters
 * must reach the server (a browser-side filter would only filter the page in
 * front of it, silently hiding matches on the next one), and the pager must
 * exist (without it every finding past the first page is unreachable).
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
vi.mock("react-hot-toast", () => ({ default: { success: vi.fn(), error: vi.fn() } }));

const translate = (key: string) => key;
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));

const { FindingsTab } = await import("./IFCActionTabs");

const PROJECT = "project-1";
const VERSION = "version-1";

const finding = (index: number): IFCFinding => ({
  id: `finding-${index}`, versionId: VERSION, findingType: "MISSING_MATERIAL",
  severity: "MEDIUM", title: `Finding ${index}`, description: "Material data is missing.",
  discipline: "STRUCTURAL", disciplines: ["STRUCTURAL"], status: "PENDING",
  ifcRule: "IFC_MATERIAL", whyItMatters: "Quantities depend on it.",
  recommendedAction: "Define materials.", affectedElementIds: [`element-${index}`],
  affectedElementCount: 1, createdAt: "2026-01-01T00:00:00Z",
});

/**
 * A page of findings.
 *
 * `count` is how many cards are rendered and `total` how many the server
 * says exist — deliberately independent, because the pager is driven by
 * `total` alone. Keeping `count` small keeps these tests about paging
 * rather than about how long fifty finding cards take to render.
 */
const pageOf = (count: number, total: number, page = 1) => ({
  items: Array.from({ length: count }, (_, index) => finding(index)),
  total, page, pageSize: 50,
});

const show = () =>
  render(
    <FindingsTab
      projectId={PROJECT} versionId={VERSION}
      summary={{ interference: { analysed: true } }}
      canReview canCreateIssue onViewElements={vi.fn()} onFocus3D={vi.fn()}
    />,
  );

/** The arguments of the most recent findings request. */
const lastQuery = () => ifcApi.findings.mock.calls.at(-1)?.[1] as Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  ifcApi.findings.mockResolvedValue(pageOf(1, 1));
});

afterEach(cleanup);

describe("scoping the query to the server", () => {
  it("asks for one revision instead of the whole project", async () => {
    show();
    await waitFor(() => expect(ifcApi.findings).toHaveBeenCalled());
    expect(ifcApi.findings.mock.calls[0][0]).toBe(PROJECT);
    expect(lastQuery()).toMatchObject({ versionId: VERSION, page: 1, pageSize: 50 });
  });

  it("sends a severity filter rather than applying it to the page in hand", async () => {
    show();
    await waitFor(() => expect(ifcApi.findings).toHaveBeenCalledTimes(1));

    await userEvent.selectOptions(
      screen.getByLabelText("ifcActions.finding_severity"), "HIGH",
    );

    await waitFor(() => expect(lastQuery()).toMatchObject({ severity: "HIGH" }));
  });

  it("sends no filter value when the selection is cleared", async () => {
    show();
    const select = screen.getByLabelText("ifcActions.finding_severity");
    await userEvent.selectOptions(select, "HIGH");
    await waitFor(() => expect(lastQuery()).toMatchObject({ severity: "HIGH" }));

    await userEvent.selectOptions(select, "");
    await waitFor(() => expect(lastQuery().severity).toBeUndefined());
  });
});

describe("moving between pages", () => {
  it("hides the pager when everything fits on one page", async () => {
    ifcApi.findings.mockResolvedValue(pageOf(10, 10));
    show();
    await screen.findByText("Finding 0");
    expect(screen.queryByText("ifcActions.findings_page_summary")).toBeNull();
    expect(screen.queryByRole("button", { name: /common\.next/i })).toBeNull();
  });

  it("offers the pager once the result outgrows a page", async () => {
    ifcApi.findings.mockResolvedValue(pageOf(3, 120));
    show();
    await screen.findByText("Finding 0");
    expect(screen.getByText("ifcActions.findings_page_summary")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /common\.next/i })).toBeEnabled();
    // Nothing before page one.
    expect(screen.getByRole("button", { name: /common\.previous/i })).toBeDisabled();
  });

  it("requests the next page and then allows going back", async () => {
    ifcApi.findings.mockResolvedValue(pageOf(3, 120));
    show();
    await screen.findByText("Finding 0");

    await userEvent.click(screen.getByRole("button", { name: /common\.next/i }));
    await waitFor(() => expect(lastQuery()).toMatchObject({ page: 2 }));

    await userEvent.click(screen.getByRole("button", { name: /common\.previous/i }));
    await waitFor(() => expect(lastQuery()).toMatchObject({ page: 1 }));
  });

  it("stops at the last page", async () => {
    // 120 findings at 50 a page is three pages; the third is the end.
    ifcApi.findings.mockResolvedValue(pageOf(3, 120));
    show();
    await screen.findByText("Finding 0");

    await userEvent.click(screen.getByRole("button", { name: /common\.next/i }));
    await waitFor(() => expect(lastQuery()).toMatchObject({ page: 2 }));
    await userEvent.click(screen.getByRole("button", { name: /common\.next/i }));
    await waitFor(() => expect(lastQuery()).toMatchObject({ page: 3 }));

    expect(screen.getByRole("button", { name: /common\.next/i })).toBeDisabled();
  });

  it("returns to the first page when a filter changes", async () => {
    // Staying on page three of the previous result would land on an empty page.
    ifcApi.findings.mockResolvedValue(pageOf(3, 120));
    show();
    await screen.findByText("Finding 0");

    await userEvent.click(screen.getByRole("button", { name: /common\.next/i }));
    await waitFor(() => expect(lastQuery()).toMatchObject({ page: 2 }));

    await userEvent.selectOptions(
      screen.getByLabelText("ifcActions.finding_severity"), "CRITICAL",
    );
    await waitFor(() => expect(lastQuery()).toMatchObject({ page: 1, severity: "CRITICAL" }));
  });
});
