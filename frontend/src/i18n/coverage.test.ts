import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import en from "./locales/en/translation.json";

/**
 * Guards the two ways localization silently degrades in this codebase.
 *
 * 1. A component calls `t("some.key")` that nothing defines, so an Arabic
 *    reader sees the raw key. This happened when a batch rewrite produced keys
 *    whose catalogue entries were never written.
 * 2. A component goes back to a hardcoded English sentence, which then stays
 *    English no matter which language is selected.
 */
const SOURCE = join(__dirname, "..");

const walk = (dir: string): string[] =>
  readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return entry === "node_modules" ? [] : walk(path);
    return /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path) ? [path] : [];
  });

const files = walk(SOURCE);

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

/** `t("a.b")` — only literal, non-interpolated keys can be checked statically. */
const LITERAL_KEY = /\bt\(\s*"([a-zA-Z][\w.]*)"\s*[),]/g;
/** A key given an explicit fallback is intentionally allowed to be absent. */
const WITH_DEFAULT = /\bt\(\s*"([a-zA-Z][\w.]*)"\s*,\s*\{[^}]*defaultValue/g;

describe("translation coverage", () => {
  it("defines every translation key the source actually asks for", () => {
    const unresolved: string[] = [];
    for (const file of files) {
      const source = readFileSync(file, "utf8");
      const excused = new Set([...source.matchAll(WITH_DEFAULT)].map((m) => m[1]));
      for (const match of source.matchAll(LITERAL_KEY)) {
        const key = match[1];
        // Plural keys resolve through a CLDR suffix at runtime.
        const base = key.replace(/_(zero|one|two|few|many|other)$/, "");
        if (excused.has(key) || has(key) || has(`${base}_other`)) continue;
        unresolved.push(`${file.replace(SOURCE, "src")} -> ${key}`);
      }
    }
    expect(unresolved, `unresolved keys:\n${unresolved.join("\n")}`).toEqual([]);
  });

  it("keeps translation keys free of stray whitespace", () => {
    // A batch rewrite once split a key across two lines, producing
    // t("namespace\n.key") which resolves to nothing at runtime.
    const broken: string[] = [];
    for (const file of files) {
      const source = readFileSync(file, "utf8");
      if (/\bt\(\s*"[^"\n]*[\r\n]/.test(source)) broken.push(file.replace(SOURCE, "src"));
    }
    expect(broken, `keys broken across lines: ${broken.join(", ")}`).toEqual([]);
  });

  it("leaves no page rendering a hardcoded English sentence", () => {
    // A JSX text node of several words that never reaches the catalogue.
    const SENTENCE = />\s*([A-Z][a-z]+(?:\s+[A-Za-z][\w'&/-]*){2,})\s*</g;
    const offenders: string[] = [];
    for (const file of files) {
      if (!file.endsWith(".tsx")) continue;
      const source = readFileSync(file, "utf8");
      for (const match of source.matchAll(SENTENCE)) {
        const text = match[1].trim();
        if (/^(https?|www)/.test(text)) continue;
        offenders.push(`${file.replace(SOURCE, "src")} -> "${text}"`);
      }
    }
    expect(offenders, `hardcoded sentences:\n${offenders.slice(0, 40).join("\n")}`).toEqual([]);
  });
});
