// @vitest-environment jsdom
/**
 * The panel, and the three judgements it makes on the user's behalf.
 *
 * 1. **Retry is offered only where it can help.** The server says whether a
 *    failure is retryable. A scanned PDF and an unparsed DWG are finished, and
 *    a button that cannot change the outcome is worse than no button.
 * 2. **Upload is offered only to somebody the server would accept.** The same
 *    `document.upload` code the endpoint checks.
 * 3. **It stops polling once everything has settled.** An idle Files tab must
 *    not keep a request loop running.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import type { IngestedFile } from "../../../types/ingestion";

const ingestionApi = {
  list: vi.fn(),
  constraints: vi.fn(),
  upload: vi.fn(),
  retry: vi.fn(),
  download: vi.fn(),
};
vi.mock("../../../services/api", () => ({
  default: { ingestion: ingestionApi },
}));

const toast = { success: vi.fn(), error: vi.fn() };
vi.mock("react-hot-toast", () => ({ default: toast }));

const translate = (key: string) => key;
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));

const role = { permissionsReady: true, hasCapability: vi.fn(() => true) };
vi.mock("../../../hooks/useRole", () => ({ useRole: () => role }));

const { ProjectFilesPanel } = await import("./ProjectFilesPanel");

const PROJECT = "project-1";

const file = (overrides: Partial<IngestedFile> = {}): IngestedFile => ({
  id: "file-1",
  projectId: PROJECT,
  uploadedById: "user-1",
  originalFilename: "specification.pdf",
  fileCategory: "PDF",
  fileSizeBytes: 2048,
  status: "READY",
  progress: 100,
  classificationJson: {},
  metadataJson: {},
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  ...overrides,
});

const page = (items: IngestedFile[]) => ({
  items,
  total: items.length,
  limit: 100,
  offset: 0,
});

const constraints = {
  maxFileBytes: 1024 * 1024,
  maxFileMb: 1,
  acceptedExtensions: [".pdf", ".zip"],
  maxPackageEntries: 500,
  maxPackageTotalBytes: 1024,
  maxPackageDepth: 1,
  categories: ["PDF" as const],
};

beforeEach(() => {
  vi.clearAllMocks();
  role.permissionsReady = true;
  role.hasCapability = vi.fn(() => true);
  ingestionApi.constraints.mockResolvedValue(constraints);
  ingestionApi.list.mockResolvedValue(page([file()]));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ProjectFilesPanel", () => {
  it("lists what the project has ingested, with its category and status", async () => {
    render(<ProjectFilesPanel projectId={PROJECT} />);
    expect(await screen.findByText("specification.pdf")).toBeInTheDocument();
    expect(screen.getByTestId("ingestion-status")).toHaveTextContent(
      "ingestion.status.ready",
    );
    expect(ingestionApi.list).toHaveBeenCalledWith(PROJECT, { limit: 100 });
  });

  it("marks a file that came out of a design package", async () => {
    ingestionApi.list.mockResolvedValue(
      page([file({ parentFileId: "package-1", originalFilename: "plan-01.pdf" })]),
    );
    render(<ProjectFilesPanel projectId={PROJECT} />);
    expect(await screen.findByText(/ingestion.fromPackage/)).toBeInTheDocument();
  });

  it("marks a file whose bytes the project already had", async () => {
    ingestionApi.list.mockResolvedValue(page([file({ duplicateOfId: "file-0" })]));
    render(<ProjectFilesPanel projectId={PROJECT} />);
    expect(await screen.findByText(/ingestion.duplicate/)).toBeInTheDocument();
  });

  it("offers a retry for a failure that can actually be retried", async () => {
    ingestionApi.list.mockResolvedValue(
      page([
        file({
          status: "FAILED",
          error: {
            code: "PROCESSING_FAILED",
            title: "Processing did not complete",
            description: "The file is unchanged.",
            retryable: true,
            suggestedAction: "Retry processing",
          },
        }),
      ]),
    );
    ingestionApi.retry.mockResolvedValue({ file: file(), queued: true });
    render(<ProjectFilesPanel projectId={PROJECT} />);

    const retry = await screen.findByRole("button", { name: "ingestion.retry" });
    await userEvent.click(retry);
    await waitFor(() =>
      expect(ingestionApi.retry).toHaveBeenCalledWith(PROJECT, "file-1"),
    );
    expect(toast.success).toHaveBeenCalledWith("ingestion.retryQueued");
  });

  it("does not offer a retry for a limitation that will never change", async () => {
    ingestionApi.list.mockResolvedValue(
      page([
        file({
          status: "PARTIAL",
          error: {
            code: "NO_TEXT_LAYER",
            title: "No readable text in this document",
            description: "The pages carry no text layer.",
            retryable: false,
            suggestedAction: "Upload a text PDF",
          },
        }),
      ]),
    );
    render(<ProjectFilesPanel projectId={PROJECT} />);
    await screen.findByText("specification.pdf");
    expect(
      screen.queryByRole("button", { name: "ingestion.retry" }),
    ).not.toBeInTheDocument();
    // The reason is still shown — the file is not broken, it is limited.
    expect(
      screen.getByText("The pages carry no text layer."),
    ).toBeInTheDocument();
  });

  it("withholds upload from somebody the server would refuse", async () => {
    role.hasCapability = vi.fn(() => false);
    render(<ProjectFilesPanel projectId={PROJECT} />);
    await screen.findByText("specification.pdf");
    expect(
      screen.queryByRole("button", { name: "ingestion.upload" }),
    ).not.toBeInTheDocument();
  });

  it("uploads a chosen file and refreshes the list", async () => {
    ingestionApi.upload.mockResolvedValue(file({ id: "file-2" }));
    render(<ProjectFilesPanel projectId={PROJECT} />);
    await screen.findByText("specification.pdf");

    const chosen = new File(["%PDF-1.7"], "plan.pdf", { type: "application/pdf" });
    await userEvent.upload(
      screen.getByLabelText("ingestion.chooseFile"),
      chosen,
    );
    await waitFor(() =>
      expect(ingestionApi.upload).toHaveBeenCalledWith(PROJECT, chosen),
    );
    expect(toast.success).toHaveBeenCalledWith("ingestion.uploadAccepted");
    expect(ingestionApi.list).toHaveBeenCalledTimes(2);
  });

  it("refuses an oversized file before spending the upload", async () => {
    render(<ProjectFilesPanel projectId={PROJECT} />);
    await screen.findByText("specification.pdf");

    const huge = new File([new Uint8Array(2 * 1024 * 1024)], "huge.pdf", {
      type: "application/pdf",
    });
    await userEvent.upload(screen.getByLabelText("ingestion.chooseFile"), huge);
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(ingestionApi.upload).not.toHaveBeenCalled();
  });

  it("reports a failed upload rather than pretending it worked", async () => {
    ingestionApi.upload.mockRejectedValue({
      response: { data: { detail: "Unsupported file type for ingest" } },
    });
    render(<ProjectFilesPanel projectId={PROJECT} />);
    await screen.findByText("specification.pdf");

    await userEvent.upload(
      screen.getByLabelText("ingestion.chooseFile"),
      new File(["x"], "a.pdf", { type: "application/pdf" }),
    );
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Unsupported file type for ingest"),
    );
  });

  it("keeps refreshing while a file is still being processed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    ingestionApi.list.mockResolvedValue(page([file({ status: "PROCESSING" })]));
    render(<ProjectFilesPanel projectId={PROJECT} />);
    await waitFor(() => expect(ingestionApi.list).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(4000);
    await waitFor(() =>
      expect(ingestionApi.list.mock.calls.length).toBeGreaterThan(1),
    );
  });

  it("stops refreshing once everything has settled", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<ProjectFilesPanel projectId={PROJECT} />);
    await waitFor(() => expect(ingestionApi.list).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(20000);
    expect(ingestionApi.list).toHaveBeenCalledTimes(1);
  });

  it("still works when the constraints call fails", async () => {
    ingestionApi.constraints.mockRejectedValue(new Error("offline"));
    render(<ProjectFilesPanel projectId={PROJECT} />);
    expect(await screen.findByText("specification.pdf")).toBeInTheDocument();
    // A convenience call failing is not worth a toast in the user's face.
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("says so when the project has no files yet", async () => {
    ingestionApi.list.mockResolvedValue(page([]));
    render(<ProjectFilesPanel projectId={PROJECT} />);
    expect(await screen.findByText("ingestion.empty")).toBeInTheDocument();
  });
});
