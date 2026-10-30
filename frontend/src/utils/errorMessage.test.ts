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

  it("flattens a FastAPI validation array into a sentence naming each field", () => {
    const detail = [
      { loc: ["body", "title"], msg: "Field required", type: "missing" },
      { loc: ["body", "scheduledEnd"], msg: "Input should be a valid datetime", type: "datetime" },
      { loc: ["body"], msg: "Value error, End date must be on or after start date", type: "value_error" },
    ];
    expect(errorMessage(asError(detail, 422), "fallback"))
      .toBe("Title: Field required. Scheduled end: Input should be a valid datetime. End date must be on or after start date");
  });

  it("marks an authorization refusal as one, so it is not read as bad input", () => {
    expect(errorMessage(asError("Only the Project Manager can assign tasks", 403), "fallback"))
      .toBe("Not permitted: Only the Project Manager can assign tasks");
    // A 400 with similar wording is left alone.
    expect(errorMessage(asError("Only the Project Manager can assign tasks", 400), "fallback"))
      .toBe("Only the Project Manager can assign tasks");
  });

  it("quotes the support ID of a server-side failure, and only of one", () => {
    const serverError = { response: { status: 500, data: { detail: { message: "Something went wrong", supportId: "abc123def" } } } };
    expect(errorMessage(serverError, "fallback")).toContain("abc123def");
    const fromHeader = { response: { status: 502, data: {}, headers: { "x-request-id": "req-98765432" } } };
    expect(errorMessage(fromHeader, "fallback")).toContain("req-98765432");
    const validation = { response: { status: 400, data: { detail: "Bad dates" }, headers: { "x-request-id": "req-1" } } };
    expect(errorMessage(validation, "fallback")).toBe("Bad dates");
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
