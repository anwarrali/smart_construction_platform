import { useCallback, useEffect, useState } from "react";
import { formatDateTime } from "../../../utils/dates";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import toast from "react-hot-toast";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { useAuth } from "../../../hooks/useAuth";
import api from "../../../services/api";
import type { ConversationDetail } from "../../../types/message";

interface Props { projectId: string; contextType: "TASK" | "ISSUE"; contextId: string; title?: string }

export const ContextDiscussion = ({ projectId, contextType, contextId, title = "Discussion" }: Props) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const value = await api.messages.context(projectId, contextType, contextId);
      setConversation(value);
      if (value?.unreadCount) await api.messages.markConversationRead(value.id);
    } catch (err: any) {
      if (!quiet) toast.error(errorMessage(err, "Unable to load discussion."));
    } finally { if (!quiet) setLoading(false); }
  }, [contextId, contextType, projectId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const timer = window.setInterval(() => load(true), 15000);
    return () => window.clearInterval(timer);
  }, [load]);
  const send = async () => {
    if (!content.trim()) return;
    setBusy(true);
    try {
      if (conversation) await api.messages.sendToConversation(conversation.id, content.trim());
      else await api.messages.createContext(projectId, contextType, contextId, content.trim());
      setContent("");
      await load(true);
    } catch (err: any) {
      toast.error(errorMessage(err, "Discussion message could not be sent."));
    } finally { setBusy(false); }
  };
  return <Card className="space-y-3">
    <div><h2 className="font-semibold">{title}</h2><p className="text-xs text-muted-foreground">Messages retain this {contextType.toLowerCase()} as structured project context.</p></div>
    <div className="max-h-72 space-y-2 overflow-y-auto rounded border bg-muted/20 p-3">
      {conversation?.messages.map((message) => {
        const mine = message.senderId === user?.id;
        return <div key={message.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}><div className={`max-w-[88%] rounded-lg px-3 py-2 text-sm ${mine ? "bg-primary text-primary-foreground" : "border bg-card"}`}>{!mine && <p className="mb-1 text-xs font-semibold">{message.sender.fullName}</p>}<p className="whitespace-pre-wrap break-words">{message.content}</p><p className={`mt-1 text-[10px] ${mine ? "text-primary-foreground/70" : "text-muted-foreground"}`}>{formatDateTime(message.createdAt)}</p></div></div>;
      })}
      {!loading && !conversation?.messages.length && <p className="py-5 text-center text-sm text-muted-foreground">{t("contextDiscussion.no_discussion_yet")}</p>}
      {loading && <p className="py-5 text-center text-sm text-muted-foreground">{t("contextDiscussion.loading_discussion")}</p>}
    </div>
    <div className="flex gap-2"><textarea className="input min-h-12 flex-1" value={content} onChange={(event) => setContent(event.target.value)} placeholder={`Discuss this ${contextType.toLowerCase()}…`} maxLength={4000} /><Button disabled={busy || !content.trim()} onClick={send}>{conversation ? "Send" : "Start Discussion"}</Button></div>
  </Card>;
};
