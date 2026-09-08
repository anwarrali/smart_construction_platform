// @vitest-environment jsdom
/**
 * Whether the findings tab tells the truth about what was checked.
 *
 * The interference rule distinguishes "measured and found nothing" from "could
 * not measure", and stores the second as `analysed: false` with a
 * `skippedReason`. The workspace used to throw that away at the last hop: both
 * arrived at the same "No model quality findings" card, so a revision whose
 * geometry was never tessellated read as a clean bill of health.
 *
 * Every assertion here is a variation on one property: **an empty list must
 * never be presented as a clean result unless the rule actually ran.**
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import type { IFCFinding, IFCInterferenceReport, IFCSummary } from "../../../types/ifc";

const ifcApi = {
  findings: vi.fn(),
  reviewFinding: vi.fn(),
  ignoreFinding: vi.fn(),
  markFindingFalsePositive: vi.fn(),
  createIssueFromFinding: vi.fn(),
};

vi.mock("../../../services/api", () => ({ default: { ifc: ifcApi } }));
vi.mock("react-hot-toast", () => ({ default: { success: vi.fn(), error: vi.fn() } }));

// Stable across renders: the tab reloads its findings whenever `t` changes
// identity, so a fresh function each render would refetch on every state change.
const translate = (key: string) => key;
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));

const { FindingsTab } = await import("./IFCActionTabs");

const PROJECT = "project-1";
const VERSION = "version-1";

const finding = (overrides: Partial<IFCFinding> = {}): IFCFinding => ({
  id: "finding-1", versionId: VERSION, findingType: "MISSING_MATERIAL", severity: "MEDIUM",
  title: "Element materials are missing",
  description: "Material data is not defined for some extracted elements.",
  discipline: "STRUCTURAL", disciplines: ["STRUCTURAL"], status: "PENDING",
  ifcRule: "IFC_MATERIAL", whyItMatters: "Material information supports quantities.",
  recommendedAction: "Define materials in the source IFC.",
  affectedElementIds: ["element-1"], affectedElementCount: 1,
  createdAt: "2026-01-01T00:00:00Z", ...overrides,
});

const summaryWith = (interference?: IFCInterferenceReport): IFCSummary =>
  interference ? { interference } : {};

/** The paged envelope `GET /ifc/findings` returns. */
const page = (items: IFCFinding[]) => ({ items, total: items.length, page: 1, pageSize: 50 });
const show = (summary?: IFCSummary) =>
  render(
    <FindingsTab
      projectId={PROJECT} versionId={VERSION} summary={summary}
      canReview canCreateIssue onViewElements={vi.fn()} onFocus3D={vi.fn()}
    />,
  );

/** Resolved once the tab has finished its initial load. */
const settled = () => screen.findByText("ifcActions.model_quality_findings");

beforeEach(() => {
  vi.clearAllMocks();
  ifcApi.findings.mockResolvedValue(page([]));
});

afterEach(cleanup);

describe("analysis completed", () => {
  it("confirms the rule ran and says what it measured", async () => {
    show(summaryWith({ analysed: true, structuralElements: 12, serviceElements: 30, findingCount: 0 }));
    await settled();
    expect(screen.getByText("ifcActions.analysis_completed")).toBeInTheDocument();
    expect(screen.getByText("ifcActions.analysis_completed_detail")).toBeInTheDocument();
  });

  it("only then presents an empty list as a clean result", async () => {
    show(summaryWith({ analysed: true, structuralElements: 12, serviceElements: 30 }));
    await settled();
    expect(screen.getByText("ifcActions.no_model_quality_findings")).toBeInTheDocument();
    expect(screen.queryByText("ifcActions.no_findings_recorded")).toBeNull();
    expect(screen.queryByText("ifcActions.absence_is_not_a_clean_result")).toBeNull();
  });

  it("says so when the result was capped rather than complete", async () => {
    show(summaryWith({ analysed: true, truncated: true, findingCount: 500 }));
    await settled();
    expect(screen.getByText("ifcActions.analysis_result_truncated")).toBeInTheDocument();
  });

  it("does not warn about truncation on an ordinary complete run", async () => {
    show(summaryWith({ analysed: true, truncated: false }));
    await settled();
    expect(screen.queryByText("ifcActions.analysis_result_truncated")).toBeNull();
  });
});

describe("analysis skipped", () => {
  it("states plainly that the rule could not run", async () => {
    show(summaryWith({ analysed: false, skippedReason: "NO_ELEMENT_GEOMETRY_AVAILABLE" }));
    await settled();
    expect(screen.getByText("ifcActions.analysis_could_not_run")).toBeInTheDocument();
    expect(screen.queryByText("ifcActions.analysis_completed")).toBeNull();
  });

  it("never lets an empty list read as a clean model", async () => {
    show(summaryWith({ analysed: false, skippedReason: "NO_ELEMENT_GEOMETRY_AVAILABLE" }));
    await settled();
    expect(screen.getByText("ifcActions.absence_is_not_a_clean_result")).toBeInTheDocument();
    expect(screen.getByText("ifcActions.no_findings_recorded")).toBeInTheDocument();
    // The reassuring wording must be absent, not merely accompanied.
    expect(screen.queryByText("ifcActions.no_model_quality_findings")).toBeNull();
  });

  it("explains that the metadata-quality checks are unaffected", async () => {
    // Otherwise the warning reads as "nothing was checked at all", which would
    // be its own false statement — the rules below it did run.
    show(summaryWith({ analysed: false, skippedReason: "UNKNOWN_LENGTH_UNIT" }));
    await settled();
    expect(screen.getByText("ifcActions.metadata_checks_still_ran")).toBeInTheDocument();
  });

  it.each([
    ["UNKNOWN_LENGTH_UNIT", "ifcActions.analysis_skipped_unknown_length_unit"],
    ["NO_ELEMENT_GEOMETRY_AVAILABLE", "ifcActions.analysis_skipped_no_element_geometry"],
    ["NO_STRUCTURAL_AND_SERVICE_PAIR_AVAILABLE", "ifcActions.analysis_skipped_no_structural_service_pair"],
    ["DISABLED_OR_MISSING_VERSION", "ifcActions.analysis_skipped_checks_disabled"],
  ])("gives %s its own explanation", async (reason, key) => {
    show(summaryWith({ analysed: false, skippedReason: reason }));
    await settled();
    expect(screen.getByText(key)).toBeInTheDocument();
  });

  it("still reports a reason code it does not recognise", async () => {
    // A reason this client has never heard of is still a reason the model was
    // not checked, so it must surface rather than silently degrade to "clean".
    show(summaryWith({ analysed: false, skippedReason: "SOME_FUTURE_REASON" }));
    await settled();
    expect(screen.getByText("ifcActions.analysis_skipped_unspecified")).toBeInTheDocument();
    expect(screen.getByText("ifcActions.absence_is_not_a_clean_result")).toBeInTheDocument();
  });

  it("warns even when the reason itself was not recorded", async () => {
    show(summaryWith({ analysed: false }));
    await settled();
    expect(screen.getByText("ifcActions.analysis_could_not_run")).toBeInTheDocument();
    expect(screen.getByText("ifcActions.analysis_skipped_no_reason_given")).toBeInTheDocument();
  });

  it("keeps listing the findings that were produced", async () => {
    // Skipped interference does not hide the metadata-quality results; the
    // warning is about what is *missing* from the list, not the list itself.
    ifcApi.findings.mockResolvedValue(page([finding()]));
    show(summaryWith({ analysed: false, skippedReason: "UNKNOWN_LENGTH_UNIT" }));
    await settled();
    expect(await screen.findByText("Element materials are missing")).toBeInTheDocument();
    expect(screen.getByText("ifcActions.analysis_could_not_run")).toBeInTheDocument();
  });
});

describe("analysis not recorded", () => {
  it("distinguishes a revision with no analysis from one that was skipped", async () => {
    show(summaryWith(undefined));
    await settled();
    expect(screen.getByText("ifcActions.analysis_not_recorded")).toBeInTheDocument();
    expect(screen.queryByText("ifcActions.analysis_could_not_run")).toBeNull();
    expect(screen.queryByText("ifcActions.analysis_completed")).toBeNull();
  });

  it("is reached when the summary is absent altogether", async () => {
    show(undefined);
    await settled();
    expect(screen.getByText("ifcActions.analysis_not_recorded")).toBeInTheDocument();
  });

  it("withholds the clean-result wording just as a skip does", async () => {
    show(summaryWith(undefined));
    await settled();
    expect(screen.getByText("ifcActions.absence_is_not_a_clean_result")).toBeInTheDocument();
    expect(screen.queryByText("ifcActions.no_model_quality_findings")).toBeNull();
  });
});
