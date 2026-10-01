import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The interface decides access by capability (`useRole().hasCapability`), and
 * names a person's role from `orgRole`. The retired fields — `user.role`, the
 * engineer affiliation, a membership's `roleOnProject` — are gone from the API,
 * so code reading them is not merely old-fashioned: it reads `undefined` and
 * quietly hides or shows the wrong thing. This keeps them from coming back.
 */
const SOURCE = join(__dirname, "..");

const walk = (dir: string): string[] =>
  readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return entry === "node_modules" ? [] : walk(path);
    return /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path) ? [path] : [];
  });

/** Source lines with comments blanked (line numbers kept): history notes may name the old fields. */
const codeLines = (path: string) =>
  readFileSync(path, "utf-8")
    .replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, " "))
    .split(/\r?\n/)
    .map((line, index) => ({ line, number: index + 1 }))
    .filter(({ line }) => !/^\s*\/\//.test(line));

const RETIRED = [
  /\.role\b(?!\w)/, // user.role, member.user.role, summary.role …
  /\broleOnProject\b/,
  /\bengineerAffiliation\b/,
  /\bUserRole\b/,
  /\b(isAdmin|isProjectManager|isEngineer|isOwner)\b/,
  /\bcheckPermission\b/,
];

describe("retired role model", () => {
  it("is not read anywhere in the interface", () => {
    const offenders: string[] = [];
    for (const file of walk(SOURCE)) {
      for (const { line, number } of codeLines(file)) {
        if (RETIRED.some((pattern) => pattern.test(line))) {
          offenders.push(`${file.slice(SOURCE.length + 1)}:${number}: ${line.trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
