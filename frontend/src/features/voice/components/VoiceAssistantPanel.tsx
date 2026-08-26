/**
 * Speak → see what was understood → confirm → it happens.
 *
 * The panel is a state machine with one rule that outranks every UX
 * consideration in it: **nothing mutates project data until the engineer has
 * seen the interpretation and pressed confirm.** Recording, transcription and
 * interpretation are all reversible and therefore automatic; the step after
 * them is not, and so it is manual, always, including when the system is
 * confident.
 *
 * Realtime is deliberately not re-implemented here. A confirmed update goes
 * through the ordinary backend services, which publish the ordinary events, so
 * every board already listening through `useRealtimeRefresh` updates itself.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { useVoiceCapture } from "../../../hooks/useVoiceCapture";
import api from "../../../services/api";
import { errorMessage } from "../../../utils/errorMessage";
import type {
  VoiceActionDraft,
  VoiceClarification,
  VoiceClientTiming,
  VoiceCommand,
} from "../../../types/voice";
import { TaskCandidatePicker } from "./TaskCandidatePicker";

type Phase = "idle" | "recording" | "processing" | "review" | "executing" | "done";

interface Props {
  projectId: string;
  /** Pre-selects a task when the panel is opened from one. */
  taskId?: string;
  /** Called after a confirmed command finishes, so a host page can refetch. */
  onExecuted?: (command: VoiceCommand) => void;
}

const HIGH_RISK = "HIGH";

const payloadOf = (draft: VoiceActionDraft) => draft.userEditedPayload ?? draft.extractedPayload;

/** Human-readable field/value pairs for one interpreted action. */
const payloadEntries = (draft: VoiceActionDraft): Array<[string, string]> =>
  Object.entries(payloadOf(draft) || {})
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => [key, Array.isArray(value) ? value.join(", ") : String(value)]);

export const VoiceAssistantPanel = ({ projectId, taskId, onExecuted }: Props) => {
  const { t, i18n } = useTranslation();
  const capture = useVoiceCapture({ language: i18n.language.startsWith("ar") ? "ar-PS" : "en-US" });

  const [phase, setPhase] = useState<Phase>("idle");
  const [command, setCommand] = useState<VoiceCommand | null>(null);
  const [error, setError] = useState("");
  const [timing, setTiming] = useState<VoiceClientTiming>({});
  const [pendingSelection, setPendingSelection] = useState<Record<string, string>>({});
  const [acknowledged, setAcknowledged] = useState(false);
  const [retryable, setRetryable] = useState<{ blob: Blob; filename: string; seconds: number } | null>(null);

  const uploadRef = useRef<AbortController | null>(null);
  const startedAtRef = useRef(0);

  useEffect(() => () => uploadRef.current?.abort(), []);

  const drafts = useMemo(() => command?.actionDrafts ?? [], [command]);
  const clarifications = useMemo(() => command?.clarifications ?? [], [command]);
  const unresolved = drafts.filter((draft) => draft.missingFields.length > 0);
  const hasHighRisk = drafts.some(
    (draft) => draft.selectedForExecution && draft.riskLevel === HIGH_RISK,
  );
  const canConfirm =
    command?.status === "READY_FOR_CONFIRMATION" &&
    drafts.some((draft) => draft.selectedForExecution) &&
    unresolved.length === 0 &&
    (!hasHighRisk || acknowledged);

  const clarificationFor = useCallback(
    (draft: VoiceActionDraft): VoiceClarification | undefined =>
      clarifications.find(
        (item) =>
          item.voiceActionDraftId === draft.id &&
          item.expectedAnswerType === "TASK_SELECTION" &&
          !item.answerText,
      ),
    [clarifications],
  );

  const reset = useCallback(() => {
    uploadRef.current?.abort();
    setCommand(null);
    setError("");
    setTiming({});
    setPendingSelection({});
    setAcknowledged(false);
    setRetryable(null);
    setPhase("idle");
  }, []);

  const send = useCallback(
    async (audio: Blob, filename: string, durationSeconds: number, captured: VoiceClientTiming) => {
      // A new recording invalidates any interpretation still in flight.
      uploadRef.current?.abort();
      const controller = new AbortController();
      uploadRef.current = controller;
      setPhase("processing");
      setError("");
      const uploadStarted = performance.now();
      try {
        const result = await api.voice.createCommand(
          {
            projectId,
            taskId,
            durationSeconds,
            // Derived from the recording itself, so a retry of the *same*
            // audio is deduplicated by the server rather than interpreted and
            // charged twice.
            idempotencyKey: `web-${startedAtRef.current}-${durationSeconds}-${audio.size}`,
            audio,
            filename,
          },
          controller.signal,
        );
        setCommand(result);
        setRetryable(null);
        setTiming({
          ...captured,
          uploadAndProcessMs: Math.round(performance.now() - uploadStarted),
          totalMs: Math.round(performance.now() - startedAtRef.current),
        });
        setPhase("review");
      } catch (caught: unknown) {
        if (controller.signal.aborted) return;
        // Hold the audio so a network failure costs the engineer a tap, not
        // the whole spoken update.
        setRetryable({ blob: audio, filename, seconds: durationSeconds });
        setError(errorMessage(caught, t("voiceAssistant.processingFailed")));
        setPhase("idle");
      }
    },
    [projectId, t, taskId],
  );

  const onStart = useCallback(async () => {
    reset();
    startedAtRef.current = performance.now();
    await capture.start();
    setPhase("recording");
  }, [capture, reset]);

  const onStop = useCallback(async () => {
    const result = await capture.stop();
    if (!result) {
      setError(t("voiceAssistant.nothingHeard"));
      setPhase("idle");
      return;
    }
    await send(result.audio, result.filename, result.durationSeconds, {
      micStartMs: result.timings.micStartMs,
      recordingMs: result.timings.recordingMs,
      firstPartialTranscriptMs: result.timings.firstPartialTranscriptMs,
    });
  }, [capture, send, t]);

  const onRetry = useCallback(() => {
    if (!retryable) return;
    startedAtRef.current = performance.now();
    void send(retryable.blob, retryable.filename, retryable.seconds, {});
  }, [retryable, send]);

  const chooseTask = useCallback(
    async (draft: VoiceActionDraft, selectedTaskId: string) => {
      if (!command) return;
      setPendingSelection((current) => ({ ...current, [draft.id]: selectedTaskId }));
      const clarification = clarificationFor(draft);
      try {
        const updated = clarification
          ? await api.voice.answerClarification(command.id, clarification.id, selectedTaskId)
          : await api.voice.updateDraft(command.id, draft.id, {
              targetId: selectedTaskId,
              payload: payloadOf(draft) || {},
              selectedForExecution: true,
              rowVersion: command.rowVersion,
            });
        setCommand(updated);
      } catch (caught: unknown) {
        setError(errorMessage(caught, t("voiceAssistant.selectionFailed")));
      } finally {
        setPendingSelection((current) => {
          const next = { ...current };
          delete next[draft.id];
          return next;
        });
      }
    },
    [clarificationFor, command, t],
  );

  const toggleDraft = useCallback(
    async (draft: VoiceActionDraft) => {
      if (!command) return;
      try {
        setCommand(
          await api.voice.updateDraft(command.id, draft.id, {
            targetId: draft.targetEntityId,
            payload: payloadOf(draft) || {},
            selectedForExecution: !draft.selectedForExecution,
            rowVersion: command.rowVersion,
          }),
        );
      } catch (caught: unknown) {
        setError(errorMessage(caught, t("voiceAssistant.updateFailed")));
      }
    },
    [command, t],
  );

  const confirm = useCallback(async () => {
    if (!command) return;
    setPhase("executing");
    setError("");
    try {
      const confirmed = await api.voice.confirm(command.id, {
        selectedDraftIds: command.actionDrafts
          .filter((draft) => draft.selectedForExecution)
          .map((draft) => draft.id),
        rowVersion: command.rowVersion,
        detailedConfirmation: hasHighRisk,
      });
      const executed = await api.voice.execute(confirmed.id, confirmed.rowVersion);
      setCommand(executed);

      // Never claim success the backend did not report. A partially executed
      // command has some actions rejected by validation or authorization, and
      // saying "saved" there is the single most damaging lie this screen could
      // tell an engineer who will not check. The success state is therefore
      // derived from the results, not from the request having returned 200.
      const results = executed.actionResults || [];
      const failures = results.filter((item) => !item.success);
      if (results.length > 0 && failures.length === 0) {
        setPhase("done");
        toast.success(t("voiceAssistant.applied", { count: results.length }));
      } else {
        setPhase("review");
        // The server's explanation, which names the rule that refused in the
        // engineer's own language; its English `message` is for the log.
        const message =
          failures[0]?.userMessage || t("voiceAssistant.notApplied");
        setError(message);
        toast.error(message);
      }
      onExecuted?.(executed);
    } catch (caught: unknown) {
      setError(errorMessage(caught, t("voiceAssistant.notApplied")));
      setPhase("review");
    }
  }, [command, hasHighRisk, onExecuted, t]);

  const cancel = useCallback(async () => {
    if (command && ["READY_FOR_CONFIRMATION", "NEEDS_CLARIFICATION"].includes(command.status)) {
      // Cancel server-side too, so an abandoned command cannot be confirmed
      // later from another device.
      await api.voice.cancel(command.id).catch(() => undefined);
    }
    capture.cancel();
    reset();
  }, [capture, command, reset]);

  const latencyLine = useMemo(() => {
    const server = command?.providerMetadata?.latencyMs;
    const parts: string[] = [];
    if (timing.totalMs) parts.push(`${t("voiceAssistant.latencyTotal")} ${timing.totalMs}ms`);
    if (server?.transcription) parts.push(`${t("voiceAssistant.latencyTranscription")} ${server.transcription}ms`);
    if (server?.analysis) parts.push(`${t("voiceAssistant.latencyAnalysis")} ${server.analysis}ms`);
    return parts.join(" · ");
  }, [command, t, timing]);

  const transcript = command?.rawTranscript || capture.previewTranscript;
  const stored = command?.structuredResult?.answer;
  const answer = stored?.text ? stored : undefined;

  return (
    <Card className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t("voiceAssistant.title")}</h2>
          <p className="text-sm opacity-70">{t("voiceAssistant.subtitle")}</p>
        </div>
        {command?.detectedLanguage ? (
          <Badge variant="neutral">{command.detectedLanguage}</Badge>
        ) : null}
      </div>

      {!capture.supported ? (
        <p className="text-sm text-amber-600">{t("voiceAssistant.browserUnsupported")}</p>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        {phase === "recording" ? (
          <>
            <Button variant="destructive" onClick={() => void onStop()}>
              {t("voiceAssistant.stop")}
            </Button>
            <Button variant="ghost" onClick={() => void cancel()}>
              {t("voiceAssistant.cancel")}
            </Button>
            <span
              className="inline-flex h-3 w-3 rounded-full bg-red-500"
              style={{ transform: `scale(${1 + capture.level})` }}
              aria-hidden
            />
            <span className="text-sm tabular-nums" aria-live="polite">
              {`${String(Math.floor(capture.elapsedSeconds / 60)).padStart(2, "0")}:${String(
                capture.elapsedSeconds % 60,
              ).padStart(2, "0")}`}
            </span>
          </>
        ) : (
          <Button
            onClick={() => void onStart()}
            disabled={!capture.supported || phase === "processing" || phase === "executing"}
            isLoading={phase === "processing" || phase === "executing"}
          >
            {phase === "processing"
              ? t("voiceAssistant.understanding")
              : phase === "executing"
                ? t("voiceAssistant.applying")
                : t("voiceAssistant.speak")}
          </Button>
        )}
        {retryable ? (
          <Button variant="outline" onClick={onRetry}>
            {t("voiceAssistant.retrySend")}
          </Button>
        ) : null}
        {command ? (
          <Button variant="ghost" onClick={() => void cancel()}>
            {t("voiceAssistant.startOver")}
          </Button>
        ) : null}
      </div>

      {transcript ? (
        <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
          <p className="text-xs uppercase opacity-60">
            {command?.rawTranscript ? t("voiceAssistant.transcript") : t("voiceAssistant.hearing")}
          </p>
          <p className="mt-1 text-sm" aria-live="polite">{transcript}</p>
        </div>
      ) : null}

      {error ? <p className="text-sm text-red-600" role="alert">{error}</p> : null}

      {phase === "review" || phase === "executing" || phase === "done" ? (
        <div className="space-y-3">
          {/*
            What the assistant said back, in the language it was spoken to.
            This is the reply to a question ("المشروع منجز حوالي 45%…") and
            also the one thing it still needs before it can propose anything
            ("تمام، أي مهمة تقصد؟") — the same field either way, because to the
            person listening they are both simply the answer.
          */}
          {answer ? (
            <div
              className="rounded-lg border border-slate-200 p-3 dark:border-slate-700"
              dir={answer.language?.startsWith("ar") ? "rtl" : "ltr"}
            >
              <p className="text-xs uppercase opacity-60">{t("voiceAssistant.answer")}</p>
              <p className="mt-1 text-sm" aria-live="polite">{answer.text}</p>
            </div>
          ) : command?.structuredResult?.summary ? (
            <p className="text-sm font-medium">{command.structuredResult.summary}</p>
          ) : null}

          {drafts.length === 0 && !answer ? (
            <p className="text-sm opacity-70">{t("voiceAssistant.nothingUnderstood")}</p>
          ) : null}

          {drafts.map((draft) => {
            const needsTask = draft.missingFields.includes("target.taskId");
            const clarification = clarificationFor(draft);
            return (
              <div key={draft.id} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-semibold">
                    {t(`voiceAssistant.action.${draft.actionType}`, { defaultValue: draft.actionType })}
                  </span>
                  <span className="flex items-center gap-2">
                    <Badge variant={draft.riskLevel === HIGH_RISK ? "danger" : "neutral"}>
                      {t(`voiceAssistant.risk.${draft.riskLevel}`, { defaultValue: draft.riskLevel })}
                    </Badge>
                    <span className="text-xs opacity-70">
                      {`${t("voiceAssistant.confidence")} ${Math.round(Number(draft.confidence) * 100)}%`}
                    </span>
                  </span>
                </div>

                <dl className="mt-2 grid gap-1 text-sm">
                  {payloadEntries(draft).map(([key, value]) => (
                    <div key={key} className="flex gap-2">
                      <dt className="opacity-60">
                        {t(`voiceAssistant.field.${key}`, { defaultValue: key })}
                      </dt>
                      <dd className="font-medium">{value}</dd>
                    </div>
                  ))}
                </dl>

                {draft.targetSnapshot ? (
                  <p className="mt-2 text-xs opacity-70">
                    {t("voiceAssistant.currentValues", {
                      status: draft.targetSnapshot.status,
                      progress: draft.targetSnapshot.progressPercentage,
                    })}
                  </p>
                ) : null}

                {draft.warnings.map((warning) => (
                  <p key={warning} className="mt-1 text-xs text-amber-600">{warning}</p>
                ))}
                {draft.executionError ? (
                  <p className="mt-1 text-xs text-red-600">{draft.executionError}</p>
                ) : null}

                {needsTask || clarification ? (
                  <div className="mt-3">
                    <TaskCandidatePicker
                      projectId={projectId}
                      options={clarification?.options || []}
                      selectedTaskId={pendingSelection[draft.id] || draft.targetEntityId}
                      onSelect={(value) => void chooseTask(draft, value)}
                      disabled={phase !== "review"}
                    />
                  </div>
                ) : (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant={draft.selectedForExecution ? "outline" : "secondary"}
                      onClick={() => void toggleDraft(draft)}
                      disabled={phase !== "review"}
                    >
                      {draft.selectedForExecution
                        ? t("voiceAssistant.removeAction")
                        : t("voiceAssistant.includeAction")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setPendingSelection((current) => ({ ...current, [draft.id]: "" }))
                      }
                      disabled={phase !== "review"}
                    >
                      {t("voiceAssistant.chooseAnotherTask")}
                    </Button>
                  </div>
                )}

                {pendingSelection[draft.id] === "" ? (
                  <div className="mt-3">
                    <TaskCandidatePicker
                      projectId={projectId}
                      options={[]}
                      selectedTaskId={draft.targetEntityId}
                      onSelect={(value) => void chooseTask(draft, value)}
                      disabled={phase !== "review"}
                    />
                  </div>
                ) : null}
              </div>
            );
          })}

          {hasHighRisk && phase === "review" ? (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
              />
              <span>{t("voiceAssistant.highRiskAcknowledgement")}</span>
            </label>
          ) : null}

          {phase !== "done" ? (
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void confirm()} disabled={!canConfirm} isLoading={phase === "executing"}>
                {t("voiceAssistant.confirmAndApply")}
              </Button>
              <Button variant="ghost" onClick={() => void cancel()}>
                {t("voiceAssistant.cancel")}
              </Button>
            </div>
          ) : (
            <p className="text-sm font-medium text-emerald-600">
              {t("voiceAssistant.finished")}
            </p>
          )}
        </div>
      ) : null}

      {latencyLine ? <p className="text-xs opacity-50">{latencyLine}</p> : null}
    </Card>
  );
};
