import { describe, expect, it } from "vitest";

import en from "./locales/en/translation.json";
import ar from "./locales/ar/translation.json";
import { SUPPORTED_LANGUAGES, directionOf } from "./index";

// Landing-page copy stores repeated lines as arrays, so a node is a string, a
// list of strings, or another subtree. Lists flatten to indexed keys, which
// keeps every element covered by the parity and translation checks below.
type Tree = { [key: string]: string | string[] | Tree };

const flatten = (tree: Tree, prefix = ""): Record<string, string> =>
  Object.entries(tree).reduce<Record<string, string>>((acc, [key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") acc[path] = value;
    else if (Array.isArray(value)) value.forEach((item, index) => { acc[`${path}.${index}`] = item; });
    else Object.assign(acc, flatten(value, path));
    return acc;
  }, {});

const english = flatten(en as Tree);
const arabic = flatten(ar as Tree);

/**
 * i18next selects a plural form by suffixing the key with a CLDR category, and
 * the two languages do not have the same set: English has `one` and `other`,
 * Arabic additionally has `zero`, `two`, `few` and `many`. Comparing raw keys
 * would therefore report every Arabic plural as "extra" and every English one
 * as "missing", so parity is checked on the base key instead.
 */
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;
const base = (key: string) => key.replace(PLURAL_SUFFIX, "");
const baseKeys = (catalogue: Record<string, string>) => new Set(Object.keys(catalogue).map(base));

const englishBases = baseKeys(english);
const arabicBases = baseKeys(arabic);

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
    const missing = [...englishBases].filter((key) => !arabicBases.has(key));
    expect(missing, `missing Arabic keys: ${missing.join(", ")}`).toEqual([]);
  });

  it("has no Arabic key without an English counterpart", () => {
    const extra = [...arabicBases].filter((key) => !englishBases.has(key));
    expect(extra, `extra Arabic keys: ${extra.join(", ")}`).toEqual([]);
  });

  it("gives Arabic every plural form its grammar requires", () => {
    // Arabic selects between six categories; a counted string that only
    // defined the English pair would fall back to the raw key at runtime.
    const required = ["zero", "one", "two", "few", "many", "other"];
    const pluralBases = new Set(
      Object.keys(arabic).filter((key) => PLURAL_SUFFIX.test(key)).map(base),
    );
    const incomplete = [...pluralBases].filter((key) =>
      required.some((form) => !(`${key}_${form}` in arabic)),
    );
    expect(incomplete, `incomplete Arabic plurals: ${incomplete.join(", ")}`).toEqual([]);
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
    // Compared per base key: a plural form legitimately exists in one
    // language and not the other, but the placeholders inside must agree.
    const mismatched = Object.keys(english).filter((key) => {
      const counterpart = arabic[key] ?? arabic[`${base(key)}_other`] ?? arabic[base(key)];
      if (counterpart === undefined) return false;
      return placeholders(english[key]).join() !== placeholders(counterpart).join();
    });
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
