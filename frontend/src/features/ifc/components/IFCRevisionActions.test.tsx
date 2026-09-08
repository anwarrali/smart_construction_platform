// @vitest-environment jsdom
/**
 * The revision lifecycle controls, and the file behind them.
 *
 * Three separate backend capabilities meet in one small header: designating
 * the active revision, designating the baseline, and fetching the original
 * IFC. The assertions worth writing are the ones about not confusing them —
 * activating must not baseline, a failed call must not report success or move
 * the UI, and the download button must not exist for somebody the server would
 * refuse.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import type { IFCVersion } from "../../../types/ifc";

const ifcApi = {
  activateVersion: vi.fn(),
  baselineVersion: vi.fn(),
  downloadVersion: vi.fn(),
};

vi.mock("../../../services/api", () => ({ default: { ifc: ifcApi } }));

const toast = { success: vi.fn(), error: vi.fn() };
vi.mock("react-hot-toast", () => ({ default: toast }));

const translate = (key: string) => key;
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));

const { IFCRevisionActions } = await import("./IFCRevisionActions");

const PROJECT = "project-1";

const version = (overrides: Partial<IFCVersion> = {}): IFCVersion => ({
  id: "version-1", modelGroupId: "group-1", projectId: PROJECT, versionNumber: 2,
  revisionCode: "P02", versionType: "DESIGN", title: "Issued for coordination",
  originalFilename: "tower-architecture.ifc", fileHash: "abc", fileSize: 1024,
  ifcSchema: "IFC4", processingStatus: "READY", processingProgress: 100,
  entityCount: 120, geometryStatus: "GEOMETRY_READY", analysisStatus: "READY",
  modelSummaryJson: {}, isActive: false, isBaseline: false,
  createdAt: "2026-01-01T00:00:00Z", ...overrides,
});

const onVersionUpdated = vi.fn();

const show = (props: {
  version?: IFCVersion; canManageVersions?: boolean; canDownload?: boolean;
} = {}) =>
  render(
    <IFCRevisionActions
      projectId={PROJECT}
      version={props.version ?? version()}
      canManageVersions={props.canManageVersions ?? true}
      canDownload={props.canDownload ?? true}
      onVersionUpdated={onVersionUpdated}
    />,
  );

const button = (key: string) =>
  screen.getByRole("button", { name: new RegExp(key.replace(/\./g, "\\."), "i") });
const maybeButton = (key: string) =>
  screen.queryByRole("button", { name: new RegExp(key.replace(/\./g, "\\."), "i") });

/** jsdom implements neither object URLs nor a real anchor download. */
let anchorClicks: HTMLAnchorElement[];

beforeEach(() => {
  vi.clearAllMocks();
  ifcApi.activateVersion.mockResolvedValue(version({ isActive: true }));
  ifcApi.baselineVersion.mockResolvedValue(version({ isBaseline: true }));
  ifcApi.downloadVersion.mockResolvedValue({
    blob: new Blob(["ISO-10303-21;"], { type: "application/x-step" }),
    filename: undefined,
  });

  anchorClicks = [];
  URL.createObjectURL = vi.fn(() => "blob:mock-url");
  URL.revokeObjectURL = vi.fn();
  const createElement = document.createElement.bind(document);
  vi.spyOn(document, "createElement").mockImplementation((tag: string, options?: ElementCreationOptions) => {
    const element = createElement(tag, options);
    if (tag === "a") {
      const anchor = element as HTMLAnchorElement;
      anchor.click = () => { anchorClicks.push(anchor); };
    }
    return element;
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  cleanup();
});

describe("showing which revision is which", () => {
  it("marks the active revision and offers only the other designation", async () => {
    show({ version: version({ isActive: true }) });
    expect(screen.getByText("ifcWorkspace.active_revision")).toBeInTheDocument();
    expect(maybeButton("ifcWorkspace.set_as_active")).toBeNull();
    expect(button("ifcWorkspace.set_as_baseline")).toBeInTheDocument();
  });

  it("marks the baseline revision independently of the active one", async () => {
    show({ version: version({ isBaseline: true }) });
    expect(screen.getByText("ifcWorkspace.baseline_revision")).toBeInTheDocument();
    expect(screen.queryByText("ifcWorkspace.active_revision")).toBeNull();
    expect(maybeButton("ifcWorkspace.set_as_baseline")).toBeNull();
    expect(button("ifcWorkspace.set_as_active")).toBeInTheDocument();
  });

  it("can show a revision that is both, with neither action left to offer", async () => {
    show({ version: version({ isActive: true, isBaseline: true }) });
    expect(screen.getByText("ifcWorkspace.active_revision")).toBeInTheDocument();
    expect(screen.getByText("ifcWorkspace.baseline_revision")).toBeInTheDocument();
    expect(maybeButton("ifcWorkspace.set_as_active")).toBeNull();
    expect(maybeButton("ifcWorkspace.set_as_baseline")).toBeNull();
  });

  it("marks neither on a revision holding no designation", async () => {
    show();
    expect(screen.queryByText("ifcWorkspace.active_revision")).toBeNull();
    expect(screen.queryByText("ifcWorkspace.baseline_revision")).toBeNull();
  });
});

describe("setting the active revision", () => {
  it("calls the activate route and reports which designation moved", async () => {
    show();
    await userEvent.click(button("ifcWorkspace.set_as_active"));

    await waitFor(() => expect(ifcApi.activateVersion).toHaveBeenCalledWith(PROJECT, "version-1"));
    // Activating must not baseline: they are separate designations.
    expect(ifcApi.baselineVersion).not.toHaveBeenCalled();
    expect(onVersionUpdated).toHaveBeenCalledWith(
      expect.objectContaining({ id: "version-1", isActive: true }), "active",
    );
    expect(toast.success).toHaveBeenCalledWith("ifcWorkspace.revision_is_now_active");
  });

  it("reports a refusal and moves nothing", async () => {
    ifcApi.activateVersion.mockRejectedValue(new Error("Only processed IFC versions can be activated"));
    show();
    await userEvent.click(button("ifcWorkspace.set_as_active"));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Only processed IFC versions can be activated"));
    expect(onVersionUpdated).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
    expect(button("ifcWorkspace.set_as_active")).toBeEnabled();
  });
});

describe("setting the baseline revision", () => {
  it("calls the baseline route and reports which designation moved", async () => {
    show();
    await userEvent.click(button("ifcWorkspace.set_as_baseline"));

    await waitFor(() => expect(ifcApi.baselineVersion).toHaveBeenCalledWith(PROJECT, "version-1"));
    expect(ifcApi.activateVersion).not.toHaveBeenCalled();
    expect(onVersionUpdated).toHaveBeenCalledWith(
      expect.objectContaining({ id: "version-1", isBaseline: true }), "baseline",
    );
    expect(toast.success).toHaveBeenCalledWith("ifcWorkspace.revision_is_now_baseline");
  });

  it("reports a refusal and moves nothing", async () => {
    ifcApi.baselineVersion.mockRejectedValue(new Error("Only processed IFC versions can be baselines"));
    show();
    await userEvent.click(button("ifcWorkspace.set_as_baseline"));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(onVersionUpdated).not.toHaveBeenCalled();
  });
});

describe("downloading the original IFC", () => {
  it("fetches the file through the authenticated client and saves it", async () => {
    show();
    await userEvent.click(button("ifcWorkspace.download_ifc"));

    await waitFor(() => expect(ifcApi.downloadVersion).toHaveBeenCalledWith(PROJECT, "version-1"));
    await waitFor(() => expect(anchorClicks).toHaveLength(1));
    // Falls back to the revision's stored name when the browser does not
    // expose Content-Disposition; never a name invented by the client.
    expect(anchorClicks[0].download).toBe("tower-architecture.ifc");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });

  it("prefers the name the server put on the response", async () => {
    ifcApi.downloadVersion.mockResolvedValue({
      blob: new Blob(["ISO-10303-21;"]), filename: "server-named%20model.ifc",
    });
    show();
    await userEvent.click(button("ifcWorkspace.download_ifc"));

    await waitFor(() => expect(anchorClicks).toHaveLength(1));
    expect(anchorClicks[0].download).toBe("server-named model.ifc");
  });

  it("reports a failure instead of saving an empty file", async () => {
    ifcApi.downloadVersion.mockRejectedValue(new Error("Stored IFC file is unavailable"));
    show();
    await userEvent.click(button("ifcWorkspace.download_ifc"));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Stored IFC file is unavailable"));
    expect(anchorClicks).toHaveLength(0);
    expect(toast.success).not.toHaveBeenCalled();
  });
});

describe("permissions", () => {
  it("offers no designation control without ifc.manage_version", async () => {
    show({ canManageVersions: false });
    expect(maybeButton("ifcWorkspace.set_as_active")).toBeNull();
    expect(maybeButton("ifcWorkspace.set_as_baseline")).toBeNull();
  });

  it("still shows which revision is active to somebody who cannot change it", async () => {
    // Read access to the designation is `ifc.view`; only changing it is gated.
    show({ canManageVersions: false, version: version({ isActive: true }) });
    expect(screen.getByText("ifcWorkspace.active_revision")).toBeInTheDocument();
  });

  it("offers no download without ifc.download", async () => {
    show({ canDownload: false });
    expect(maybeButton("ifcWorkspace.download_ifc")).toBeNull();
  });

  it("gates download separately from revision management", async () => {
    show({ canManageVersions: false, canDownload: true });
    expect(button("ifcWorkspace.download_ifc")).toBeInTheDocument();
    expect(maybeButton("ifcWorkspace.set_as_active")).toBeNull();
  });
});

describe("one action at a time", () => {
  it("closes every control while a call is open", async () => {
    let release: (value: IFCVersion) => void = () => undefined;
    ifcApi.activateVersion.mockReturnValue(new Promise((resolve) => { release = resolve; }));
    show();

    const activate = button("ifcWorkspace.set_as_active");
    await userEvent.click(activate);

    expect(activate).toBeDisabled();
    expect(button("ifcWorkspace.set_as_baseline")).toBeDisabled();
    expect(button("ifcWorkspace.download_ifc")).toBeDisabled();

    await userEvent.click(activate);
    expect(ifcApi.activateVersion).toHaveBeenCalledTimes(1);

    release(version({ isActive: true }));
    await waitFor(() => expect(onVersionUpdated).toHaveBeenCalled());
  });
});
