import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ShieldCheck } from "lucide-react";

import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { Modal } from "../ui/Modal";
import { errorMessage } from "../../utils/errorMessage";
import api from "../../services/api";
import type { StepUpChallenge } from "../../types/stepUp";

/**
 * The one verification dialog for every step-up-protected action.
 *
 * Pages never build their own: they call `useStepUp().run(...)`, which opens
 * this on a STEP_UP_REQUIRED response and retries the original call once the
 * code is accepted.
 */

interface Props {
  purpose: string;
  label: string;
  onVerified: () => void;
  onCancel: () => void;
}

export const StepUpDialog = ({ purpose, label, onVerified, onCancel }: Props) => {
  const { t } = useTranslation();
  const [challenge, setChallenge] = useState<StepUpChallenge | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  // Strict mode mounts effects twice in development; without this the dialog
  // would request two codes and immediately invalidate the first.
  const requested = useRef(false);

  const request = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const value = await api.stepUp.request(purpose);
      setChallenge(value);
      setCooldown(value.resendAfterSeconds || 0);
      setCode("");
    } catch (err: unknown) {
      setError(errorMessage(err, t("stepUp.requestFailed")));
    } finally {
      setBusy(false);
    }
  }, [purpose, t]);

  useEffect(() => {
    if (requested.current) return;
    requested.current = true;
    request();
  }, [request]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!code.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.stepUp.verify(purpose, code.trim());
      onVerified();
    } catch (err: unknown) {
      // The server answers every failure identically on purpose, so the
      // dialog does not try to guess a more specific reason than it was told.
      setError(errorMessage(err, t("stepUp.invalidCode")));
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal isOpen onClose={onCancel} title={t("stepUp.title")}>
      <form onSubmit={submit} className="space-y-4">
        <div className="flex items-start gap-3 rounded-lg border bg-muted/30 p-3">
          <ShieldCheck size={18} className="mt-0.5 shrink-0 text-primary" />
          <div className="text-sm">
            <p className="font-medium">{t("stepUp.protectedAction")}</p>
            <p className="text-muted-foreground">{label}</p>
          </div>
        </div>

        <p className="text-sm text-muted-foreground">{t("stepUp.explanation")}</p>

        {challenge && !challenge.delivered && (
          <p
            role="status"
            className="rounded-lg border border-state-review/40 bg-wash-review px-3 py-2 text-sm text-state-review"
          >
            {t("stepUp.deliveryUnavailable")}
          </p>
        )}

        <Input
          label={t("stepUp.codeLabel")}
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={10}
          autoFocus
          required
          // Announced to assistive technology, and tied to the field so the
          // error is read out rather than only seen.
          aria-invalid={!!error}
          aria-describedby={error ? "step-up-error" : undefined}
        />

        {error && (
          <p id="step-up-error" role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="flex items-center justify-between gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy || cooldown > 0}
            onClick={request}
          >
            {cooldown > 0 ? t("stepUp.resendIn", { seconds: cooldown }) : t("stepUp.resend")}
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={onCancel}>
              {t("stepUp.cancel")}
            </Button>
            <Button type="submit" isLoading={busy} disabled={!code.trim()}>
              {t("stepUp.verify")}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  );
};
