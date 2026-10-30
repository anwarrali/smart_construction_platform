// @vitest-environment jsdom
/**
 * The task form's discipline list comes from the office catalogue, not a
 * hard-coded four. Create and edit read the same hook.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const disciplines = vi.fn();
vi.mock("../features/admin/services/organization.service", () => ({
  default: { disciplines: () => disciplines() },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en", resolvedLanguage: "en" } }),
}));
vi.mock("../utils/vocabulary", () => ({
  useVocabulary: () => ({ discipline: (code: string) => `label:${code}` }),
}));

const { useDisciplineOptions } = await import("./useDisciplineOptions");

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
);

const row = (code: string, nameEn: string, rank: number, isActive = true) =>
  ({ id: code, code, nameEn, nameAr: null, ifcDisciplines: [], rank, isActive });

afterEach(() => disciplines.mockReset());

describe("useDisciplineOptions", () => {
  it("offers every active catalogue discipline in catalogue order", async () => {
    disciplines.mockResolvedValue([
      row("qa_qc", "QA/QC", 160), row("structural", "Structural", 20), row("architectural", "Architectural", 10),
      row("bim", "BIM", 110), row("retired", "Retired", 5, false),
    ]);
    const { result } = renderHook(() => useDisciplineOptions(), { wrapper });
    await waitFor(() => expect(result.current.isFallback).toBe(false));
    expect(result.current.options.map((option) => option.value)).toEqual(["architectural", "structural", "bim", "qa_qc"]);
  });

  it("keeps a task's saved discipline selectable after it leaves the catalogue", async () => {
    disciplines.mockResolvedValue([row("civil", "Civil", 30)]);
    const { result } = renderHook(() => useDisciplineOptions("legacy_trade"), { wrapper });
    await waitFor(() => expect(result.current.isFallback).toBe(false));
    expect(result.current.options).toContainEqual({ value: "legacy_trade", label: "label:legacy_trade" });
  });

  it("still offers the four long-standing disciplines if the catalogue cannot be read", async () => {
    disciplines.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useDisciplineOptions(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.options.map((option) => option.value)).toEqual(["architectural", "civil", "electrical", "mechanical"]);
  });
});
