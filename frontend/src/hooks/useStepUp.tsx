import { useCallback, useState } from "react";

import { StepUpDialog } from "../components/shared/StepUpDialog";
import { stepUpInfo } from "../services/axios";

/**
 * Wraps any API call that might be step-up protected.
 *
 * The page does not need to know which of its actions are protected, or which
 * purpose each maps to — the server says so in its 401, and this replays the
 * original call unchanged once verification succeeds. Adding protection to a
 * new endpoint therefore needs no frontend change at all beyond using `run`.
 *
 *   const { run, dialog } = useStepUp();
 *   await run(() => api.users.deactivate(id));
 *   ...
 *   {dialog}
 */
export const useStepUp = () => {
  const [pending, setPending] = useState<{
    purpose: string;
    label: string;
    resolve: (value: unknown) => void;
    reject: (reason?: unknown) => void;
    action: () => Promise<unknown>;
  } | null>(null);

  const run = useCallback(<T,>(action: () => Promise<T>): Promise<T> => {
    return action().catch((error: unknown) => {
      const info = stepUpInfo(error);
      if (!info) throw error;
      // Hold the caller's promise open while the user verifies, so `await
      // run(...)` simply resolves with the eventual result and the page needs
      // no separate "verified" callback.
      return new Promise<T>((resolve, reject) => {
        setPending({
          purpose: info.purpose,
          label: info.label,
          resolve: resolve as (value: unknown) => void,
          reject,
          action: action as () => Promise<unknown>,
        });
      });
    });
  }, []);

  const dialog = pending ? (
    <StepUpDialog
      purpose={pending.purpose}
      label={pending.label}
      onVerified={async () => {
        const current = pending;
        setPending(null);
        try {
          current.resolve(await current.action());
        } catch (error) {
          current.reject(error);
        }
      }}
      onCancel={() => {
        const current = pending;
        setPending(null);
        // Cancelling is a real outcome, not a hang: reject so the caller's
        // `finally` runs and any spinner it owns is cleared.
        current.reject(new Error("STEP_UP_CANCELLED"));
      }}
    />
  ) : null;

  return { run, dialog };
};
