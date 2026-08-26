/**
 * The short list an engineer picks from when the system is not sure.
 *
 * The whole design constraint is length. A picker showing every task in the
 * project is the "remember the exact task name" problem with extra scrolling,
 * so the server sends a ranked handful and this component shows them in that
 * order — never re-sorted, because the order carries the ranking. The free-text
 * box below is the escape hatch for the case the ranking got wrong, and it
 * re-ranks server-side rather than filtering the visible few.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "../../../components/ui/Input";
import api from "../../../services/api";
import { errorMessage } from "../../../utils/errorMessage";
import type { VoiceClarificationOption, VoiceTaskCandidate } from "../../../types/voice";

interface Props {
  projectId: string;
  /** Ranked options the server already produced for this action. */
  options: VoiceClarificationOption[];
  selectedTaskId?: string;
  onSelect: (taskId: string, label: string) => void;
  disabled?: boolean;
}

const asOption = (candidate: VoiceTaskCandidate): VoiceClarificationOption => ({
  value: candidate.taskId,
  label: candidate.taskCode ? `${candidate.taskCode} — ${candidate.name}` : candidate.name,
  status: candidate.status,
  progressPercentage: candidate.progressPercentage,
  discipline: candidate.discipline,
  score: candidate.score,
  reasons: candidate.reasons,
});

export const TaskCandidatePicker = ({
  projectId,
  options,
  selectedTaskId,
  onSelect,
  disabled = false,
}: Props) => {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<VoiceClarificationOption[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  // Derived, never mirrored: copying `options` into state through an effect
  // renders the stale list for one frame every time the server sends a new
  // ranking, which during a clarification is exactly when it changes.
  const shown = query.trim() && found ? found : options;

  // Abort rather than ignore: a slow earlier search must not overwrite the
  // list a later keystroke already produced.
  const search = useCallback(
    async (text: string) => {
      abortRef.current?.abort();
      if (!text.trim()) {
        setFound(null);
        setSearchError("");
        return;
      }
      const controller = new AbortController();
      abortRef.current = controller;
      setSearching(true);
      try {
        const result = await api.voice.taskCandidates(projectId, text, controller.signal);
        setFound(result.candidates.map(asOption));
        setSearchError("");
      } catch (error: unknown) {
        if (!controller.signal.aborted) {
          setSearchError(errorMessage(error, t("voiceAssistant.searchFailed")));
        }
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    },
    [projectId, t],
  );

  // Debounced so a typed word costs one ranking request, not one per letter.
  useEffect(() => {
    const timer = window.setTimeout(() => void search(query), 250);
    return () => window.clearTimeout(timer);
  }, [query, search]);

  useEffect(() => () => abortRef.current?.abort(), []);

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{t("voiceAssistant.whichTask")}</p>
      <ul className="space-y-1.5">
        {shown.map((option) => {
          const isSelected = option.value === selectedTaskId;
          return (
            <li key={option.value}>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onSelect(option.value, option.label)}
                aria-pressed={isSelected}
                className={`w-full rounded-lg border p-3 text-start transition ${
                  isSelected ? "border-primary-500 bg-primary-50 dark:bg-primary-900/20" : "hover:bg-slate-50 dark:hover:bg-slate-800/60"
                }`}
              >
                <span className="block text-sm font-medium">{option.label}</span>
                <span className="mt-1 flex flex-wrap items-center gap-2 text-xs opacity-70">
                  {option.status ? <span>{option.status}</span> : null}
                  {typeof option.progressPercentage === "number" ? (
                    <span>{`${option.progressPercentage}%`}</span>
                  ) : null}
                  {(option.reasons || []).map((reason) => (
                    <span key={reason} className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-700">
                      {reason}
                    </span>
                  ))}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {shown.length === 0 && !searching ? (
        <p className="text-xs opacity-70">{t("voiceAssistant.noCandidates")}</p>
      ) : null}
      <Input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t("voiceAssistant.searchOtherTasks")}
        aria-label={t("voiceAssistant.searchOtherTasks")}
        disabled={disabled}
      />
      {searching ? <p className="text-xs opacity-70">{t("voiceAssistant.searching")}</p> : null}
      {searchError ? <p className="text-xs text-red-600">{searchError}</p> : null}
    </div>
  );
};
