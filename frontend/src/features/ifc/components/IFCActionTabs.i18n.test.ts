import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import en from "../../../i18n/locales/en/translation.json";

/**
 * IFCActionTabs deliberately mixes genuine application UI copy with
 * IFC-standard vocabulary and live model data (element names, IFC classes,
 * GlobalIds, revision codes). The general translation-coverage sweep
 * (`src/i18n/coverage.test.ts`) only flags hardcoded JSX *text nodes* of
 * three or more words — it doesn't see string literals passed as JSX
 * attributes (`description="..."`) or into plain function calls
 * (`setError("...")`, `toast.success("...")`), which is exactly where this
 * file's untranslated strings used to hide. This test closes that gap for
 * this one file specifically, rather than loosening the general sweep (which
 * would then also have to start ignoring legitimate non-UI string literals —
 * class names, IFC identifiers — across the rest of the codebase).
 */
const SOURCE_PATH = join(__dirname, "IFCActionTabs.tsx");
const source = readFileSync(SOURCE_PATH, "utf8");

type Node = { [key: string]: string | string[] | Node };
const has = (path: string): boolean => {
  let node: unknown = en as Node;
  for (const part of path.split(".")) {
    if (typeof node !== "object" || node === null) return false;
    node = (node as Record<string, unknown>)[part];
    if (node === undefined) return false;
  }
  return true;
};

describe("IFCActionTabs localization", () => {
  it("passes every description/message/label prop through t() rather than a literal", () => {
    const ATTR_STRING = /\b(?:description|message|label)="([^"{}]{6,})"/g;
    const offenders = [...source.matchAll(ATTR_STRING)].map((match) => match[1]);
    expect(offenders).toEqual([]);
  });

  it("passes every setError/toast argument through t() rather than a literal sentence", () => {
    const CALL_STRING = /\b(?:setError|toast\.(?:success|error))\(\s*"([^"]{4,})"/g;
    const offenders = [...source.matchAll(CALL_STRING)].map((match) => match[1]);
    expect(offenders).toEqual([]);
  });

  it("defines every ifcActions.* key this component asks for in the English catalogue", () => {
    const missing = [...new Set([...source.matchAll(/t\(\s*"(ifcActions\.[\w.]+)"/g)].map((match) => match[1]))]
      .filter((key) => !has(key));
    expect(missing).toEqual([]);
  });

  it("keeps IFC-standard/dynamic values out of the catalogue lookup path", () => {
    // `translateArea` must fall through to the raw value for anything that
    // isn't one of the four fixed UI sentinels — i.e. for IFC identity field
    // names such as "GlobalId" or "Name", which come straight from the
    // model and must never be run through the translation catalogue.
    expect(source).toMatch(/AREA_LABEL_KEYS\[area\]\s*\?\s*t\(AREA_LABEL_KEYS\[area\]\)\s*:\s*area/);
  });

  it("does not reintroduce the specific hardcoded sentences this file used to render", () => {
    const reintroduced = [
      "Stable IFC GlobalIds are used where available",
      "AI-generated suggestions should be reviewed by a qualified engineer",
      "Comparison requires at least two revisions",
      "Select a base and comparison revision to review",
      "No findings match the current revision and filters",
      "The model analysis remains available in the other tabs",
      "Revision comparisons could not be loaded",
      "Model quality findings could not be loaded",
      "Suggestions could not be loaded. The rest of the model analysis",
      "Model review suggestion",
      "No reason was supplied.",
      "Review may improve model data quality.",
      "Review the available IFC evidence.",
    ].filter((needle) => source.includes(`"${needle}`) || source.includes(`>${needle}`));
    expect(reintroduced).toEqual([]);
  });
});
