import { describe, expect, it } from "vitest";

import en from "./locales/en/translation.json";
import ar from "./locales/ar/translation.json";
import { SUPPORTED_LANGUAGES, directionOf } from "./index";

type Tree = { [key: string]: string | Tree };

const flatten = (tree: Tree, prefix = ""): Record<string, string> =>
  Object.entries(tree).reduce<Record<string, string>>((acc, [key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") acc[path] = value;
    else Object.assign(acc, flatten(value, path));
    return acc;
  }, {});

const english = flatten(en as Tree);
const arabic = flatten(ar as Tree);

describe("language configuration", () => {
  it("declares the direction each language reads in", () => {
    expect(directionOf("en")).toBe("ltr");
    expect(directionOf("ar")).toBe("rtl");
  });

  it("falls back to left-to-right for an unknown language", () => {
    expect(directionOf("xx")).toBe("ltr");
  });

  it("offers exactly the two supported languages", () => {
    expect(SUPPORTED_LANGUAGES.map((item) => item.code)).toEqual(["en", "ar"]);
    expect(SUPPORTED_LANGUAGES.find((item) => item.code === "ar")?.nativeLabel).toBe("العربية");
  });
});

describe("translation catalogues", () => {
  it("has a non-trivial number of strings", () => {
    expect(Object.keys(english).length).toBeGreaterThan(250);
  });

  it("translates every English key into Arabic", () => {
    const missing = Object.keys(english).filter((key) => !(key in arabic));
    expect(missing, `missing Arabic keys: ${missing.join(", ")}`).toEqual([]);
  });

  it("has no Arabic key without an English counterpart", () => {
    const extra = Object.keys(arabic).filter((key) => !(key in english));
    expect(extra, `extra Arabic keys: ${extra.join(", ")}`).toEqual([]);
  });

  it("leaves no Arabic value empty", () => {
    const blank = Object.entries(arabic).filter(([, value]) => !value.trim());
    expect(blank.map(([key]) => key)).toEqual([]);
  });

  it("actually translates rather than copying the English string", () => {
    // A handful of values are legitimately identical (IFC, BIM); everything
    // else being identical would mean the catalogue was never translated.
    const identical = Object.keys(english).filter((key) => english[key] === arabic[key]);
    expect(identical.length).toBeLessThan(10);
  });

  it("keeps interpolation placeholders identical in both languages", () => {
    const placeholders = (value: string) =>
      (value.match(/\{\{\s*\w+\s*\}\}/g) || []).map((item) => item.replace(/\s/g, "")).sort();
    const mismatched = Object.keys(english).filter(
      (key) => placeholders(english[key]).join() !== placeholders(arabic[key] || "").join(),
    );
    expect(mismatched, `placeholder mismatch: ${mismatched.join(", ")}`).toEqual([]);
  });

  it("covers the surfaces the brief calls out", () => {
    for (const key of [
      "nav.tasks", "nav.issues", "nav.documents", "nav.siteReports",
      "common.save", "common.cancel", "common.status",
      "empty.noData", "empty.noProjects", "empty.noTasks",
      "auth.login", "auth.password",
      "roles.project_manager", "roles.consultant",
      "task.status.in_progress", "project.status.active",
      "issue.status.open", "designChange.status.approved",
      "errors.generic", "validation.required",
      "collaboration.counts.needsMyResponse",
    ]) {
      expect(english[key], `English missing ${key}`).toBeTruthy();
      expect(arabic[key], `Arabic missing ${key}`).toBeTruthy();
    }
  });

  it("uses construction terminology in Arabic rather than literal translation", () => {
    expect(arabic["nav.designChanges"]).toBe("التعديلات التصميمية");
    expect(arabic["roles.project_manager"]).toBe("مدير المشروع");
    expect(arabic["nav.siteReports"]).toBe("تقارير الموقع");
    expect(arabic["task.criticalPath"]).toBe("المسار الحرج");
    expect(arabic["nav.schedule"]).toContain("الجدول الزمني");
  });
});
