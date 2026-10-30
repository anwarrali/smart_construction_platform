import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "../../../components/ui/Button";
import type { VoiceClarification } from "../../../types/voice";

interface ClarificationAnswerProps {
  clarification: VoiceClarification;
  onAnswer: (answer: string) => Promise<void> | void;
  disabled?: boolean;
}

/**
 * Answers one question the assistant asked about an action — by the kind of
 * answer it expects, not by assuming every question is "which task?".
 *
 * The panel used to recognise only `TASK_SELECTION`. A text question such as
 * "How was it solved?" (an issue's required resolution note) got no input at
 * all, while the card still offered "Choose another task" — so a standalone
 * issue could not be resolved from the website and the screen read as if the
 * issue needed a task. Task selection keeps its dedicated picker in the panel;
 * this covers every other answer type: options to pick from (an issue, a
 * status), or free text and numbers.
 */
export const ClarificationAnswer = ({ clarification, onAnswer, disabled }: ClarificationAnswerProps) => {
  const { t, i18n } = useTranslation();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const arabic = (i18n.resolvedLanguage || i18n.language || "en").startsWith("ar");
  const question = (arabic ? clarification.questionAr : clarification.questionEn)
    || clarification.questionEn || clarification.questionAr;

  const submit = async (answer: string) => {
    if (!answer.trim() || busy) return;
    setBusy(true);
    try {
      await onAnswer(answer.trim());
      setText("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 space-y-2" data-testid="clarification-answer">
      <p className="text-sm font-medium">{question}</p>
      {clarification.options.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {clarification.options.map((option) => (
            <Button
              key={option.value}
              size="sm"
              variant="secondary"
              disabled={disabled || busy}
              onClick={() => void submit(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>
      ) : (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(event) => { event.preventDefault(); void submit(text); }}
        >
          <input
            className="input min-w-0 flex-1"
            type={clarification.expectedAnswerType === "NUMBER" ? "number" : "text"}
            value={text}
            onChange={(event) => setText(event.target.value)}
            aria-label={question}
            disabled={disabled || busy}
            // The engineer answers in whichever language they think in.
            dir="auto"
          />
          <Button type="submit" size="sm" disabled={disabled || !text.trim()} isLoading={busy}>
            {t("voiceAssistant.answer")}
          </Button>
        </form>
      )}
    </div>
  );
};
