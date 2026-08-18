import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { Forward, MessageCircleQuestion } from "lucide-react";

import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";
import { Select } from "../ui/Select";
import { errorMessage } from "../../utils/errorMessage";
import { ROUTES } from "../../utils/constants";
import api from "../../services/api";
import type { RecipientOptions, SharedEntityType } from "../../types/message";

/**
 * The single Forward / Ask-for-Opinion control used by every entity that
 * supports consultation (Issues, Tasks, Site Reports, Design Changes,
 * Documents).
 *
 * It takes the entity's identity rather than duplicating any per-entity UI or
 * request logic: the backend's `/messages/share` builds the context summary
 * from the entity itself, so adding another entity later means allowing it
 * server-side and passing a new `entityType` here — not writing another modal.
 *
 * The recipient list comes from `recipientOptions`, the same source the
 * compose and forward modals use, so the picker can only ever offer people
 * the project's own messaging rules already allow. The backend independently
 * re-validates both the sender's and every recipient's access to the entity,
 * so this list is a convenience, never the protection.
 */

type Intent = "forward" | "opinion";

interface Props {
  entityType: SharedEntityType;
  entityId: string;
  projectId: string;
  /** Hide "Ask for Opinion" where only plain sharing makes sense. */
  intents?: Intent[];
  size?: "sm" | "md";
  className?: string;
}

export const CommunicationActions = ({
  entityType,
  entityId,
  projectId,
  intents = ["forward", "opinion"],
  size = "sm",
  className = "",
}: Props) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [intent, setIntent] = useState<Intent | null>(null);
  const [options, setOptions] = useState<RecipientOptions>({ users: [], groups: [] });
  const [mode, setMode] = useState<"individual" | "multiple">("individual");
  const [recipientIds, setRecipientIds] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const open = useCallback((value: Intent) => {
    setIntent(value);
    setMode("individual");
    setRecipientIds([]);
    // "Ask for Opinion" is a question by definition, so it starts with the
    // request already written — the user only has to pick who to ask.
    setNote(value === "opinion" ? t("communication.opinionDefaultNote") : "");
  }, [t]);

  useEffect(() => {
    if (!intent || !projectId) return;
    api.messages.recipientOptions(projectId)
      .then(setOptions)
      .catch(() => setOptions({ users: [], groups: [] }));
  }, [intent, projectId]);

  const submit = async () => {
    if (!recipientIds.length) return;
    setBusy(true);
    try {
      const conversation = await api.messages.shareEntity({
        entityType, entityId, recipientIds, note: note.trim() || undefined,
      });
      setIntent(null);
      toast.success(
        intent === "opinion" ? t("communication.opinionSent") : t("communication.shared"),
        {
          // Sharing happens away from Messages, so the confirmation carries the
          // way back to the thread it created rather than stranding the user.
          duration: 6000,
        },
      );
      navigate(`${ROUTES.MESSAGES}?conversationId=${conversation.id}`);
    } catch (err: any) {
      toast.error(errorMessage(err, t("communication.shareFailed")));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (id: string) => {
    if (mode === "individual") return setRecipientIds([id]);
    setRecipientIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
  };

  return (
    <>
      <span className={`inline-flex flex-wrap gap-2 ${className}`}>
        {intents.includes("forward") && (
          <Button size={size} variant="outline" onClick={() => open("forward")}>
            <Forward size={13} className="rtl-flip me-1" /> {t("communication.forward")}
          </Button>
        )}
        {intents.includes("opinion") && (
          <Button size={size} variant="outline" onClick={() => open("opinion")}>
            <MessageCircleQuestion size={13} className="me-1" /> {t("communication.askOpinion")}
          </Button>
        )}
      </span>

      <Modal
        isOpen={intent !== null}
        onClose={() => setIntent(null)}
        title={intent === "opinion" ? t("communication.askOpinionTitle") : t("communication.forwardTitle")}
        size="lg"
      >
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {intent === "opinion"
              ? t("communication.askOpinionDescription")
              : t("communication.forwardDescription")}
          </p>
          <Select
            label={t("communication.sendTo")}
            value={mode}
            onChange={(event) => {
              setMode(event.target.value as typeof mode);
              setRecipientIds([]);
            }}
            options={[
              { value: "individual", label: t("communication.individual") },
              { value: "multiple", label: t("communication.multiplePeople") },
            ]}
          />
          <div>
            <p className="mb-2 text-sm font-medium">{t("communication.projectRecipients")}</p>
            <div className="max-h-56 space-y-1 overflow-y-auto rounded border p-2">
              {options.users.map((recipient) => (
                <label key={recipient.id} className="flex cursor-pointer items-center gap-3 rounded p-2 hover:bg-muted">
                  <input
                    type={mode === "individual" ? "radio" : "checkbox"}
                    checked={recipientIds.includes(recipient.id)}
                    onChange={() => toggle(recipient.id)}
                  />
                  <span>
                    <span className="block text-sm font-medium">{recipient.fullName}</span>
                    <span className="text-xs text-muted-foreground">{recipient.role.replaceAll("_", " ")}</span>
                  </span>
                </label>
              ))}
              {!options.users.length && (
                <p className="p-3 text-center text-sm text-muted-foreground">
                  {t("communication.noRecipients")}
                </p>
              )}
            </div>
          </div>
          <label className="block text-sm font-medium">
            {t("communication.note")}
            <textarea
              className="input mt-1 min-h-20 w-full"
              value={note}
              maxLength={4000}
              onChange={(event) => setNote(event.target.value)}
              placeholder={t("communication.notePlaceholder")}
            />
          </label>
          <p className="text-xs text-muted-foreground">{t("communication.ownershipHint")}</p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setIntent(null)}>{t("communication.cancel")}</Button>
            <Button disabled={busy || !recipientIds.length} onClick={submit}>
              {intent === "opinion" ? t("communication.askOpinion") : t("communication.forward")}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
};
