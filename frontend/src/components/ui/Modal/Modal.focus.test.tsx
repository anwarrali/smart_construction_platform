// @vitest-environment jsdom
/**
 * Regression coverage for a shared focus-loss bug in every modal-based form
 * in the app (Create Project, Create/Edit User, Task forms, Issue forms, ...).
 *
 * Root cause: `Modal`'s focus-management `useEffect` depended on
 * `[isOpen, handleKeyDown]`, and `handleKeyDown` was a `useCallback([onClose])`.
 * Callers overwhelmingly pass `onClose={() => setOpen(false)}` inline — a new
 * function every render of the parent — and the parent re-renders on every
 * keystroke whenever the open form's field values live in or above that same
 * component, which is the normal pattern here (see e.g.
 * `features/projects/pages/ProjectsPage.tsx`'s `form` state). So on every
 * keystroke: parent re-renders -> new `onClose` -> new `handleKeyDown` ->
 * the effect tears down and re-runs -> its cleanup calls
 * `previouslyFocused.focus()`, a stale closure over whatever was focused when
 * *that* instance of the effect had been set up, which one keystroke after
 * the modal opened is still the button that originally opened it. The input
 * DOM node itself was never destroyed (the character is correctly written to
 * it — reconciliation keeps the node), only focus was yanked back out of the
 * dialog, so the next keystroke lands nowhere useful until the field is
 * clicked again.
 *
 * `ChurningParentForm` below reproduces that exact shape — a parent whose
 * state (and therefore `onClose` identity) changes on every keystroke —
 * rather than asserting against `Modal` in isolation. Most tests in this
 * file exercise it directly to confirm the *intended* behaviour holds
 * end-to-end (every field, sequential fields, Arabic input, repeated open/
 * close, Escape). The one exception is the first test below, which needs a
 * harness built a specific way to reliably fail on the pre-fix component in
 * this environment: this repo's React Compiler pass can prove a bare
 * `() => setOpen(false)` referentially stable and memoize it away entirely,
 * which — only inside this jsdom + compiler combination, not in a real
 * browser — happens to remove the churn that exposes the bug before it ever
 * reaches `Modal`. That test's `onClose` closes over changing state
 * specifically to defeat that, and was confirmed (by temporarily reverting
 * `Modal.tsx`) to fail with 12 keydown-listener registrations for an
 * 11-character string instead of the expected 1. The bug itself — and this
 * fix — were additionally confirmed directly in the real running app (see
 * this session's browser verification), which is what actually matters for
 * a defect of this kind.
 */
import { useState } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

// This project's vitest config doesn't set `test.globals: true`, so
// Testing Library's automatic per-test `afterEach(cleanup)` (which relies on
// detecting a global test framework) never registers itself — without this,
// each test's rendered DOM piles up across the file and later
// `getByLabelText` calls fail with "multiple elements found".
afterEach(cleanup);

import { Modal, ModalActions } from "./Modal";

/** The exact shape every modal-based form in this app uses: field values
 * live in the same component that renders `<Modal>`, and `onClose` is a
 * fresh inline closure every render. */
const ChurningParentForm = ({
  fieldCount = 2,
  onCloseSpy,
}: {
  fieldCount?: number;
  onCloseSpy?: () => void;
}) => {
  const [isOpen, setIsOpen] = useState(true);
  const [values, setValues] = useState<string[]>(Array(fieldCount).fill(""));

  return (
    <div>
      <button
        type="button"
        onClick={() => {
          setValues(Array(fieldCount).fill(""));
          setIsOpen(true);
        }}
      >
        Open trigger
      </button>
      <Modal
        isOpen={isOpen}
        onClose={() => {
          // Closes over `values` (state that changes on every keystroke),
          // same as real callers frequently do (e.g. a confirmation prompt
          // referencing current field state before closing) — this is what
          // makes `onClose`'s identity genuinely change every render,
          // matching the shape that exposed the bug, rather than one simple
          // enough that a compiler-level optimization could coincidentally
          // paper over the very re-render churn this test exists to catch.
          if (values.length > 1_000_000) return;
          setIsOpen(false);
          onCloseSpy?.();
        }}
        title="Create Project"
      >
        <form>
          {values.map((value, index) => (
            <input
              key={index}
              aria-label={`field-${index}`}
              value={value}
              onChange={(e) => {
                const next = [...values];
                next[index] = e.target.value;
                setValues(next);
              }}
            />
          ))}
          <ModalActions>
            <button type="submit">Save</button>
          </ModalActions>
        </form>
      </Modal>
    </div>
  );
};

describe("Modal focus stability while a parent re-renders on every keystroke", () => {
  it("does not re-register its keydown listener on every keystroke (only once per open)", async () => {
    // The direct mechanism, not just its visible symptom. `document.activeElement`
    // alone is an unreliable regression pin here: the effect's own "focus
    // the first field" `requestAnimationFrame` callback can resolve before a
    // synchronous post-`act()` assertion runs and paper back over a stale
    // focus state, in a single-field harness, even when the tear-down/re-run
    // cycle that causes it is still happening underneath. What must not
    // happen, regardless of that race, is the effect re-registering its
    // `document.addEventListener("keydown", ...)` more than once per open —
    // that registration is this effect's own signature of "I just tore down
    // and set back up", which is exactly what used to fire on every
    // keystroke (see this file's header).
    //
    // `onClose` here deliberately closes over `value` (state that changes on
    // every keystroke) rather than being a bare `() => setIsOpen(false)` —
    // empirically, this repo's React Compiler pass (`vite.config.ts`,
    // `reactCompilerPreset()`) can prove the simpler form referentially
    // stable across renders and auto-memoize it away, which would make this
    // test pass even against the pre-fix component for the wrong reason (no
    // re-render churn to expose the bug, rather than the effect correctly
    // tolerating it). Forcing a real dependency on changing state is what
    // makes this test actually fail on the pre-fix `Modal` — confirmed by
    // running it against `git stash` of this file's fix before writing it.
    const user = userEvent.setup();
    const addListenerSpy = vi.spyOn(document, "addEventListener");

    const SingleFieldHarness = () => {
      const [isOpen] = useState(true);
      const [value, setValue] = useState("");
      return (
        <Modal isOpen={isOpen} onClose={() => { if (value.length > 1_000_000) return; }} title="t">
          <input aria-label="f" value={value} onChange={(e) => setValue(e.target.value)} />
        </Modal>
      );
    };
    render(<SingleFieldHarness />);

    const field = screen.getByLabelText("f");
    await act(async () => {
      await user.click(field);
    });
    const keydownRegistrationsAfterOpen = addListenerSpy.mock.calls.filter(
      (call) => call[0] === "keydown",
    ).length;
    expect(keydownRegistrationsAfterOpen).toBe(1);

    await act(async () => {
      await user.type(field, "Residential");
    });

    const keydownRegistrationsAfterTyping = addListenerSpy.mock.calls.filter(
      (call) => call[0] === "keydown",
    ).length;
    expect(keydownRegistrationsAfterTyping).toBe(1);
    addListenerSpy.mockRestore();
  });

  it("keeps every character of a continuous multi-character string in the same field, without losing focus", async () => {
    const user = userEvent.setup();
    render(<ChurningParentForm />);

    const field = screen.getByLabelText("field-0");
    await act(async () => {
      await user.click(field);
    });
    expect(document.activeElement).toBe(field);

    await act(async () => {
      await user.type(field, "Residential");
    });

    expect(field).toHaveValue("Residential");
    // The bug this file exists to pin: focus used to be yanked back to the
    // trigger button (or elsewhere outside the field) after the very first
    // keystroke, well before the string finished typing.
    expect(document.activeElement).toBe(field);
  });

  it("routes every character to the field the user is actually typing in when moving between fields sequentially", async () => {
    const user = userEvent.setup();
    render(<ChurningParentForm fieldCount={3} />);

    const first = screen.getByLabelText("field-0");
    const second = screen.getByLabelText("field-1");
    const third = screen.getByLabelText("field-2");

    await act(async () => {
      await user.click(first);
      await user.type(first, "Residential Tower A");
      await user.click(second);
      await user.type(second, "Eight-storey building");
      await user.click(third);
      await user.type(third, "Ramallah, Palestine");
    });

    expect(first).toHaveValue("Residential Tower A");
    expect(second).toHaveValue("Eight-storey building");
    expect(third).toHaveValue("Ramallah, Palestine");
    expect(document.activeElement).toBe(third);
  });

  it("keeps focus stable while typing Arabic (RTL) text", async () => {
    const user = userEvent.setup();
    render(<ChurningParentForm />);

    const field = screen.getByLabelText("field-0");
    await act(async () => {
      await user.click(field);
      await user.type(field, "رام الله، فلسطين");
    });

    expect(field).toHaveValue("رام الله، فلسطين");
    expect(document.activeElement).toBe(field);
  });

  it("keeps typing correctly across the churn caused by re-opening the modal repeatedly", async () => {
    const user = userEvent.setup();
    render(<ChurningParentForm />);

    const field = screen.getByLabelText("field-0");
    await act(async () => {
      await user.click(field);
      await user.type(field, "First");
    });
    expect(field).toHaveValue("First");

    // Close and reopen through the component's own state, not a fresh
    // `render` — the modal's effect must clean up and re-run exactly once
    // each way, which is the one legitimate case for it to fire again,
    // unlike a mid-open parent re-render.
    await act(async () => {
      await user.keyboard("{Escape}");
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Open trigger" }));
    });
    const reopened = screen.getByLabelText("field-0");
    // Reopening resets this harness's own form state, same as the real
    // create-modals resetting to an empty form.
    expect(reopened).toHaveValue("");
    await act(async () => {
      await user.click(reopened);
      await user.type(reopened, "Second");
    });
    expect(reopened).toHaveValue("Second");
    expect(document.activeElement).toBe(reopened);
  });

  it("still closes on Escape and calls the latest onClose", async () => {
    const user = userEvent.setup();
    let closeCount = 0;
    render(<ChurningParentForm onCloseSpy={() => { closeCount += 1; }} />);

    const field = screen.getByLabelText("field-0");
    await act(async () => {
      await user.click(field);
      await user.type(field, "abc");
      await user.keyboard("{Escape}");
    });

    expect(closeCount).toBe(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("returns focus to the trigger element only once, when the modal actually closes — not on every keystroke", async () => {
    const user = userEvent.setup();

    const HarnessWithRealTrigger = () => {
      const [isOpen, setIsOpen] = useState(false);
      const [value, setValue] = useState("");
      return (
        <div>
          <button type="button" onClick={() => setIsOpen(true)}>
            Add Project
          </button>
          <Modal isOpen={isOpen} onClose={() => setIsOpen(false)} title="Create">
            <input aria-label="name" value={value} onChange={(e) => setValue(e.target.value)} />
          </Modal>
        </div>
      );
    };

    render(<HarnessWithRealTrigger />);
    const trigger = screen.getByRole("button", { name: "Add Project" });
    await act(async () => {
      await user.click(trigger);
    });

    const field = await screen.findByLabelText("name");
    await act(async () => {
      await user.click(field);
      await user.type(field, "Residential Complex D");
    });

    // The literal bug this reproduces: after typing, `document.activeElement`
    // used to be this exact trigger button, not the field.
    expect(document.activeElement).toBe(field);
    expect(document.activeElement).not.toBe(trigger);
    expect(field).toHaveValue("Residential Complex D");

    await act(async () => {
      await user.keyboard("{Escape}");
    });
    expect(document.activeElement).toBe(trigger);
  });
});
