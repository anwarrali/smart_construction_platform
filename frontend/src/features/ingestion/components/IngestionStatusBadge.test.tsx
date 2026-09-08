// @vitest-environment jsdom
/**
 * The one distinction this badge exists to make.
 *
 * "Partially processed" and "Failed" both mean "you did not get everything",
 * and they call for opposite actions. A failed file may work on a retry; a
 * partial one is finished — a scanned PDF has no text layer and never will.
 * Rendering them alike would send people to retry something that cannot
 * improve, or hide that their specification is not searchable.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

const translate = (key: string) => key;
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));

const { IngestionStatusBadge } = await import("./IngestionStatusBadge");

import type { IngestionStatus } from "../../../types/ingestion";

afterEach(cleanup);

const show = (status: IngestionStatus, error = null) =>
  render(<IngestionStatusBadge status={status} error={error} />);

describe("IngestionStatusBadge", () => {
  it("names every lifecycle state through a translation key", () => {
    const expected: Record<IngestionStatus, string> = {
      UPLOADED: "ingestion.status.uploading",
      VALIDATING: "ingestion.status.validating",
      CLASSIFIED: "ingestion.status.classified",
      QUEUED: "ingestion.status.queued",
      PROCESSING: "ingestion.status.processing",
      READY: "ingestion.status.ready",
      PARTIAL: "ingestion.status.partial",
      FAILED: "ingestion.status.failed",
    };
    for (const [status, key] of Object.entries(expected)) {
      cleanup();
      show(status as IngestionStatus);
      expect(screen.getByTestId("ingestion-status")).toHaveTextContent(key);
    }
  });

  it("does not render a raw enum name", () => {
    show("PARTIAL");
    expect(screen.queryByText("PARTIAL")).not.toBeInTheDocument();
  });

  it("distinguishes a finished-but-incomplete file from a failed one", () => {
    show("PARTIAL");
    const partial = screen.getByTestId("ingestion-status");
    expect(partial).toHaveTextContent("ingestion.status.partial");
    expect(partial.querySelector(".badge-warning")).toBeTruthy();
    expect(partial.querySelector(".badge-danger")).toBeNull();

    cleanup();
    show("FAILED");
    const failed = screen.getByTestId("ingestion-status");
    expect(failed.querySelector(".badge-danger")).toBeTruthy();
  });

  it("treats a ready file as a success and a working one as neutral progress", () => {
    show("READY");
    expect(
      screen.getByTestId("ingestion-status").querySelector(".badge-success"),
    ).toBeTruthy();

    cleanup();
    show("PROCESSING");
    expect(
      screen.getByTestId("ingestion-status").querySelector(".badge-info"),
    ).toBeTruthy();
  });

  it("carries the reason and the suggested action as a tooltip", () => {
    render(
      <IngestionStatusBadge
        status="PARTIAL"
        error={{
          code: "NO_TEXT_LAYER",
          title: "No readable text in this document",
          description: "The pages carry no text layer.",
          retryable: false,
          suggestedAction: "Upload a text PDF",
        }}
      />,
    );
    expect(screen.getByTestId("ingestion-status")).toHaveAttribute(
      "title",
      "No readable text in this document — Upload a text PDF",
    );
  });

  it("has no tooltip when there is nothing to explain", () => {
    show("READY");
    expect(screen.getByTestId("ingestion-status")).not.toHaveAttribute("title");
  });

  it("falls back rather than crashing on a status it does not know", () => {
    // Rows outlive code: a status added on the server before a client deploy
    // must render as something, not blank the page.
    show("SOMETHING_NEW" as IngestionStatus);
    expect(screen.getByTestId("ingestion-status")).toHaveTextContent(
      "ingestion.status.unknown",
    );
  });
});
