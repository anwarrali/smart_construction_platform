// @vitest-environment jsdom
/**
 * Whether a file's text is searchable, shown only as the server reports it.
 *
 * NOT_INDEXED renders nothing on purpose: most such files can never be indexed
 * (drawings, images, models), and a label on each would read as a fault.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

const translate = (key: string) => key;
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));

const { IndexStatusBadge } = await import("./IndexStatusBadge");
import {
  INDEX_PICKUP_GRACE_MS,
  awaitsIndexing,
  type IngestedFile,
} from "../../../types/ingestion";

afterEach(cleanup);

describe("IndexStatusBadge", () => {
  it("names each reported state through a translation key", () => {
    const expected = {
      INDEXING: "ingestion.index.indexing",
      READY: "ingestion.index.ready",
      FAILED: "ingestion.index.failed",
    } as const;
    for (const [status, key] of Object.entries(expected)) {
      cleanup();
      render(<IndexStatusBadge status={status as keyof typeof expected} />);
      expect(screen.getByTestId("index-status")).toHaveTextContent(key);
    }
  });

  it("renders nothing for a file that is not indexed, or an older server", () => {
    const { container, rerender } = render(<IndexStatusBadge status="NOT_INDEXED" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<IndexStatusBadge />);
    expect(container).toBeEmptyDOMElement();
  });

  it("marks a failure as one and carries the server's reason", () => {
    render(<IndexStatusBadge status="FAILED" error="The embedding provider is unreachable" />);
    const badge = screen.getByTestId("index-status");
    expect(badge).toHaveAttribute("title", "The embedding provider is unreachable");
    expect(badge.querySelector(".badge-danger")).toBeTruthy();
  });

  it("marks a searchable file as a success, with no tooltip", () => {
    render(<IndexStatusBadge status="READY" error="stale reason" />);
    const badge = screen.getByTestId("index-status");
    expect(badge).not.toHaveAttribute("title");
    expect(badge.querySelector(".badge-success")).toBeTruthy();
  });
});

describe("awaitsIndexing", () => {
  const NOW = Date.parse("2026-10-09T12:00:00Z");
  const settled = (overrides: Partial<IngestedFile> = {}): IngestedFile => ({
    id: "f", projectId: "p", uploadedById: "u", originalFilename: "spec.pdf",
    fileCategory: "PDF", fileSizeBytes: 1, status: "READY", progress: 100,
    classificationJson: {}, metadataJson: { extraction: "TEXT" },
    processingCompletedAt: new Date(NOW - 5_000).toISOString(),
    indexStatus: "NOT_INDEXED",
    createdAt: "", updatedAt: "", ...overrides,
  });

  it("waits while indexing runs", () => {
    expect(awaitsIndexing(settled({ indexStatus: "INDEXING" }), NOW)).toBe(true);
  });

  it("waits briefly for a text file that just settled", () => {
    expect(awaitsIndexing(settled(), NOW)).toBe(true);
    expect(awaitsIndexing(settled({ status: "PARTIAL" }), NOW)).toBe(true);
  });

  it("stops once the pickup window has passed", () => {
    const old = new Date(NOW - INDEX_PICKUP_GRACE_MS - 1).toISOString();
    expect(awaitsIndexing(settled({ processingCompletedAt: old }), NOW)).toBe(false);
  });

  it("never waits for a file nothing will index", () => {
    expect(awaitsIndexing(settled({ metadataJson: { extraction: "NONE" } }), NOW)).toBe(false);
    expect(awaitsIndexing(settled({ status: "FAILED" }), NOW)).toBe(false);
    expect(awaitsIndexing(settled({ duplicateOfId: "earlier" }), NOW)).toBe(false);
    expect(awaitsIndexing(settled({ indexStatus: "READY" }), NOW)).toBe(false);
    expect(awaitsIndexing(settled({ indexStatus: "FAILED" }), NOW)).toBe(false);
  });
});
