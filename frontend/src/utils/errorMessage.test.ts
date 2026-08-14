import { describe, expect, it } from "vitest";

import { errorMessage } from "./errorMessage";

/**
 * The failure this guards against: `response.data.detail` was passed straight
 * into `toast.error(...)` and into JSX. FastAPI returns that field as a string,
 * as a list of validation objects, or as a structured object, so the non-string
 * shapes crashed React with "Objects are not valid as a React child" and blanked
 * the whole application.
 */
const asError = (detail: unknown, status = 400) => ({ response: { status, data: { detail } } });

describe("errorMessage", () => {
  it("passes a plain string detail through", () => {
    expect(errorMessage(asError("Engineer must be an active project participant"), "fallback"))
      .toBe("Engineer must be an active project participant");
  });

  it("flattens a FastAPI validation array into a sentence", () => {
    const detail = [
      { loc: ["body", "title"], msg: "Field required", type: "missing" },
      { loc: ["body", "scheduledEnd"], msg: "Input should be a valid datetime", type: "datetime" },
    ];
    expect(errorMessage(asError(detail, 422), "fallback"))
      .toBe("Field required. Input should be a valid datetime");
  });

  it("reads the message out of a structured detail object", () => {
    const detail = { message: "Site visit conflicts with an existing visit", conflicts: [{ id: "x" }] };
    expect(errorMessage(asError(detail, 409), "fallback"))
      .toBe("Site visit conflicts with an existing visit");
  });

  it("always returns a string, whatever the shape", () => {
    for (const detail of [null, undefined, 42, [], {}, [{ nope: 1 }], { a: { b: {} } }]) {
      expect(typeof errorMessage(asError(detail), "fallback")).toBe("string");
    }
  });

  it("falls back when the request never reached the server", () => {
    expect(errorMessage(new Error("Network Error"), "fallback")).toBe("Network Error");
    expect(errorMessage({}, "fallback")).toBe("fallback");
  });

  it("never returns an empty string for a blank detail", () => {
    expect(errorMessage(asError("   "), "fallback")).toBe("fallback");
  });
});
