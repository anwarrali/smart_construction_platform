import { describe, expect, it } from "vitest";

import ar from "../../../i18n/locales/ar/translation.json";
import en from "../../../i18n/locales/en/translation.json";
import { rejectUpload } from "./IFCShared";

/**
 * Every failure code `backend/app/services/ifc_policy.py` can store on a
 * version. `ProcessingFailure` looks its heading up by code, so a code with no
 * entry silently degrades to the generic heading in both languages.
 */
const BACKEND_ERROR_CODES = [
  "IFC_FILE_CORRUPTED", "IFC_PARSER_UNAVAILABLE", "IFC_ENTITY_LIMIT_EXCEEDED",
  "IFC_PARSE_TIMEOUT", "IFC_PARSER_OUT_OF_MEMORY", "IFC_PROCESSING_FAILED",
  "IFC_GEOMETRY_FAILED",
];

/**
 * Pre-upload validation exists so a site engineer on a slow connection is not
 * asked to transmit a half-gigabyte model before being told it is the wrong
 * file. It must therefore refuse exactly what the server refuses — no more, or
 * it blocks legitimate uploads the server would have taken.
 */
const file = (name: string, size: number) =>
  new File([new Uint8Array(Math.min(size, 8))], name, { type: "application/octet-stream" });

const sized = (name: string, size: number) => {
  const value = file(name, 1);
  Object.defineProperty(value, "size", { value: size });
  return value;
};

const CONSTRAINTS = { acceptedExtensions: [".ifc"], maxFileBytes: 500 * 1024 * 1024, maxFileMb: 500 };

const lookup = (catalogue: unknown, key: string): unknown =>
  key.split(".").reduce<unknown>(
    (node, part) => (node && typeof node === "object" ? (node as Record<string, unknown>)[part] : undefined),
    catalogue,
  );
const messageFor = (key: string): unknown => lookup(en, key);

describe("pre-upload IFC validation", () => {
  it("accepts an ordinary IFC file", () => {
    expect(rejectUpload(sized("building.ifc", 12_000_000), CONSTRAINTS)).toBeNull();
  });

  it("accepts an IFC file whose extension is upper case", () => {
    expect(rejectUpload(sized("BUILDING.IFC", 12_000_000), CONSTRAINTS)).toBeNull();
  });

  it("refuses a file that is not an IFC", () => {
    const rejection = rejectUpload(sized("model.rvt", 12_000_000), CONSTRAINTS);
    expect(rejection?.key).toBe("ifcWorkspace.file_must_be_ifc");
    expect(rejection?.values?.extensions).toBe(".ifc");
  });

  it("refuses a renamed file that merely contains .ifc in its name", () => {
    expect(rejectUpload(sized("my.ifc.zip", 1_000), CONSTRAINTS)?.key).toBe("ifcWorkspace.file_must_be_ifc");
  });

  it("refuses an empty file", () => {
    expect(rejectUpload(sized("empty.ifc", 0), CONSTRAINTS)?.key).toBe("ifcWorkspace.file_is_empty");
  });

  it("refuses a file over the server's limit and reports both numbers", () => {
    const rejection = rejectUpload(sized("huge.ifc", 600 * 1024 * 1024), CONSTRAINTS);
    expect(rejection?.key).toBe("ifcWorkspace.file_exceeds_limit");
    expect(rejection?.values).toEqual({ size: "600.0", limit: 500 });
  });

  it("accepts a file exactly on the limit", () => {
    expect(rejectUpload(sized("exact.ifc", 500 * 1024 * 1024), CONSTRAINTS)).toBeNull();
  });

  it("does not invent a size limit when the server's rules could not be loaded", () => {
    // Guessing a limit here would reject uploads a differently configured
    // server would have accepted. Size is left to the server in that case.
    expect(rejectUpload(sized("huge.ifc", 900 * 1024 * 1024), undefined)).toBeNull();
    expect(rejectUpload(sized("huge.rvt", 900 * 1024 * 1024), undefined)?.key).toBe("ifcWorkspace.file_must_be_ifc");
  });

  it("honours a server that accepts more than one extension", () => {
    const extended = { ...CONSTRAINTS, acceptedExtensions: [".ifc", ".ifcxml"] };
    expect(rejectUpload(sized("model.ifcxml", 5_000), extended)).toBeNull();
  });

  it("names a message that actually exists in the catalogue", () => {
    // These keys are built at runtime from the rejection, so the static
    // `t("literal")` coverage check cannot see them.
    for (const name of ["file_must_be_ifc", "file_is_empty", "file_exceeds_limit"]) {
      expect(typeof messageFor(`ifcWorkspace.${name}`)).toBe("string");
    }
  });
});

describe("processing failure headings", () => {
  it.each(BACKEND_ERROR_CODES)("explains %s in both languages", (code) => {
    for (const catalogue of [en, ar]) {
      expect(typeof lookup(catalogue, `ifcWorkspace.error_${code}_title`)).toBe("string");
      expect(typeof lookup(catalogue, `ifcWorkspace.error_${code}_action`)).toBe("string");
    }
  });

  it("gives a timeout and an out-of-memory failure different advice", () => {
    // They arrive from different causes and need different next steps; the
    // backend distinguishes them, so the UI must not collapse them back.
    expect(messageFor("ifcWorkspace.error_IFC_PARSE_TIMEOUT_action"))
      .not.toBe(messageFor("ifcWorkspace.error_IFC_PARSER_OUT_OF_MEMORY_action"));
  });
});
