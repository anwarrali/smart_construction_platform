import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Modal } from "../../../components/ui/Modal";
import { Select } from "../../../components/ui/Select";
import { useAuth } from "../../../hooks/useAuth";
import { useRole } from "../../../hooks/useRole";
import api from "../../../services/api";
import type { Conversation, ConversationDetail, ConversationType, RecipientOptions } from "../../../types/message";
import type { Project } from "../../../types/project";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";

type Tab = "all" | "unread" | "direct" | "teams" | "project";

export const MessagesPage = () => {
  const { t } = useTranslation();
  const workspace = useProjectWorkspace();
  const { user } = useAuth();
  const { isAdmin, isProjectManager } = useRole();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState(workspace.projectId || "");
  const projectId = workspace.projectId || selectedProjectId;
  const [items, setItems] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [options, setOptions] = useState<RecipientOptions>({ users: [], groups: [] });
  const [tab, setTab] = useState<Tab>("all");
  const [search, setSearch] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [recipientMode, setRecipientMode] = useState<"individual" | "multiple" | "group">("individual");
  const [recipientIds, setRecipientIds] = useState<string[]>([]);
  const [groupCode, setGroupCode] = useState("");
  const [title, setTitle] = useState("");
  const [firstMessage, setFirstMessage] = useState("");
  const [announcement, setAnnouncement] = useState(false);

  useEffect(() => {
    if (workspace.projectId) return setSelectedProjectId(workspace.projectId);
    api.projects.list({ limit: 100 }).then((response) => {
      setProjects(response.data || []);
      setSelectedProjectId((current) => current || response.data?.[0]?.id || "");
    }).catch(() => setProjects([]));
  }, [workspace.projectId]);

  const loadList = useCallback(async (quiet = false) => {
    if (!projectId) return;
    if (!quiet) setLoading(true);
    try {
      const type: ConversationType | "" =
        tab === "direct" ? "DIRECT" :
        tab === "teams" ? "GROUP" :
        tab === "project" ? "PROJECT_CHANNEL" : "";
      const response = await api.messages.conversations(projectId, {
        conversationType: type,
        unreadOnly: tab === "unread",
        search: search || undefined,
        pageSize: 100,
      });
      setItems(response.items);
      setSelectedId((current) =>
        response.items.some((item) => item.id === current)
          ? current : response.items[0]?.id || "",
      );
    } catch (err: any) {
      if (!quiet) toast.error(errorMessage(err, "Unable to load conversations."));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [projectId, search, tab]);

  const loadDetail = useCallback(async (quiet = false) => {
    if (!selectedId) return setDetail(null);
    try {
      const value = await api.messages.conversation(selectedId);
      setDetail(value);
      if (value.unreadCount) await api.messages.markConversationRead(value.id);
    } catch (err: any) {
      if (!quiet) toast.error(errorMessage(err, "Unable to open conversation."));
    }
  }, [selectedId]);

  useEffect(() => {
    if (!projectId) return;
    api.messages.recipientOptions(projectId).then(setOptions).catch(() => setOptions({ users: [], groups: [] }));
  }, [projectId]);
  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { loadDetail(); }, [loadDetail]);
  useEffect(() => {
    const timer = window.setInterval(() => {
      loadList(true);
      loadDetail(true);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [loadList, loadDetail]);

  const conversationTitle = (conversation: Conversation) => {
    if (conversation.title) return conversation.title;
    const others = conversation.participants
      .filter((item) => item.userId !== user?.id)
      .map((item) => item.user.fullName);
    return others.join(", ") || "Project discussion";
  };

  const send = async () => {
    if (!detail || !content.trim()) return;
    setBusy(true);
    try {
      await api.messages.sendToConversation(detail.id, content.trim());
      setContent("");
      await Promise.all([loadDetail(true), loadList(true)]);
    } catch (err: any) {
      toast.error(errorMessage(err, "Message could not be sent."));
    } finally { setBusy(false); }
  };

  const create = async () => {
    if (!projectId || !firstMessage.trim()) return;
    setBusy(true);
    try {
      const conversation = announcement
        ? await api.messages.announce(projectId, firstMessage.trim(), title.trim() || undefined, groupCode || "ALL_PROJECT_MEMBERS")
        : await api.messages.createConversation({
            projectId,
            recipientIds: recipientMode === "group" ? [] : recipientIds,
            groupCode: recipientMode === "group" ? groupCode : undefined,
            title: title.trim() || undefined,
            content: firstMessage.trim(),
          });
      setComposeOpen(false);
      setRecipientIds([]);
      setGroupCode("");
      setTitle("");
      setFirstMessage("");
      setAnnouncement(false);
      await loadList();
      setSelectedId(conversation.id);
    } catch (err: any) {
      toast.error(errorMessage(err, "Conversation could not be created."));
    } finally { setBusy(false); }
  };

  const tabs: Array<{ value: Tab; label: string }> = [
    { value: "all", label: "All" }, { value: "unread", label: "Unread" },
    { value: "direct", label: "Direct" }, { value: "teams", label: "Teams" },
    { value: "project", label: "Project" },
  ];
  const selectedRecipients = useMemo(
    () => options.users.filter((item) => recipientIds.includes(item.id)),
    [options.users, recipientIds],
  );

  return <div className="page-container space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h1 className="text-2xl font-bold">{t("messagesPage.project_communication")}</h1><p className="text-sm text-muted-foreground">{t("messagesPage.direct_team_announcement_and_contextual")}</p></div>
      <Button onClick={() => setComposeOpen(true)}>{t("messagesPage.new_conversation")}</Button>
    </div>
    {!workspace.projectId && <Card><Select label={t("messagesPage.project")} value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)} options={projects.map((project) => ({ value: project.id, label: project.name }))} /></Card>}
    <Card className="flex flex-wrap items-center gap-2 p-3">
      {tabs.map((item) => <Button key={item.value} size="sm" variant={tab === item.value ? "primary" : "ghost"} onClick={() => setTab(item.value)}>{item.label}</Button>)}
      <div className="ml-auto min-w-56"><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("messagesPage.search_messages_or_people")} /></div>
    </Card>
    <div className="grid min-h-[610px] overflow-hidden rounded-xl border bg-card lg:grid-cols-[340px_1fr]">
      <aside className="border-b lg:border-b-0 lg:border-r">
        <div className="max-h-[610px] overflow-y-auto">
          {items.map((conversation) => <button key={conversation.id} type="button" onClick={() => setSelectedId(conversation.id)}
            className={`w-full border-b p-4 text-left hover:bg-muted/50 ${selectedId === conversation.id ? "bg-primary/10" : ""}`}>
            <div className="flex items-start justify-between gap-2">
              <p className="truncate font-semibold">{conversationTitle(conversation)}</p>
              {conversation.unreadCount > 0 && <Badge size="sm" variant="danger">{conversation.unreadCount}</Badge>}
            </div>
            <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">{conversation.lastMessage?.content || "No messages"}</p>
            <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
              <span>{conversation.type.replaceAll("_", " ").toLowerCase()}</span>
              <span>{new Date(conversation.lastActivityAt).toLocaleString()}</span>
            </div>
          </button>)}
          {!loading && !items.length && <p className="p-8 text-center text-sm text-muted-foreground">{t("messagesPage.no_conversations_match_this_view")}</p>}
          {loading && <p className="p-8 text-center text-sm text-muted-foreground">{t("messagesPage.loading_conversations")}</p>}
        </div>
      </aside>
      <section className="flex min-h-[610px] flex-col">
        {detail ? <>
          <header className="border-b p-4">
            <div className="flex items-center gap-2"><h2 className="font-semibold">{conversationTitle(detail)}</h2><Badge>{detail.type.replaceAll("_", " ").toLowerCase()}</Badge></div>
            <p className="mt-1 text-xs text-muted-foreground">{detail.participants.map((item) => item.user.fullName).join(", ")}</p>
            {detail.contextType && <p className="mt-1 text-xs font-medium text-primary">{detail.contextType} discussion · {detail.contextId}</p>}
          </header>
          <div className="flex-1 space-y-3 overflow-y-auto bg-muted/20 p-4">
            {detail.messages.map((message) => {
              const mine = message.senderId === user?.id;
              return <div key={message.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-xl px-4 py-2 text-sm ${mine ? "bg-primary text-primary-foreground" : "border bg-card"}`}>
                  {!mine && detail.type !== "DIRECT" && <p className="mb-1 text-xs font-semibold text-primary">{message.sender.fullName}</p>}
                  <p className="whitespace-pre-wrap break-words">{message.content}</p>
                  <p className={`mt-1 text-[10px] ${mine ? "text-primary-foreground/70" : "text-muted-foreground"}`}>{new Date(message.createdAt).toLocaleString()}</p>
                </div>
              </div>;
            })}
          </div>
          <div className="flex gap-2 border-t p-3"><textarea className="input min-h-12 flex-1 resize-y" maxLength={4000} value={content} onChange={(event) => setContent(event.target.value)} placeholder={t("messagesPage.write_a_project_message")} /><Button disabled={busy || !content.trim()} onClick={send}>{t("messagesPage.send")}</Button></div>
        </> : <div className="m-auto text-sm text-muted-foreground">{t("messagesPage.select_or_create_a_conversation")}</div>}
      </section>
    </div>

    <Modal isOpen={composeOpen} onClose={() => setComposeOpen(false)} title={t("messagesPage.new_project_conversation")} size="lg">
      <div className="space-y-4">
        {(isAdmin || isProjectManager) && <label className="flex items-center gap-2 rounded border p-3 text-sm font-medium"><input type="checkbox" checked={announcement} onChange={(event) => setAnnouncement(event.target.checked)} /> Project/team announcement</label>}
        {!announcement && <Select label={t("messagesPage.send_to")} value={recipientMode} onChange={(event) => { setRecipientMode(event.target.value as typeof recipientMode); setRecipientIds([]); setGroupCode(""); }} options={[
          { value: "individual", label: "Individual" },
          { value: "multiple", label: "Multiple People" },
          ...(options.groups.length ? [{ value: "group", label: "Team / Group" }] : []),
        ]} />}
        {(recipientMode === "group" || announcement) ? <Select label={t("messagesPage.recipient_group")} value={groupCode} onChange={(event) => setGroupCode(event.target.value)} options={[
          ...(announcement ? [{ value: "ALL_PROJECT_MEMBERS", label: "All Project Members" }] : []),
          ...options.groups.map((group) => ({ value: group.code, label: `${group.label} (${group.recipientCount})` })),
        ]} /> : <div>
          <p className="mb-2 text-sm font-medium">{t("messagesPage.project_recipients")}</p>
          <div className="max-h-56 space-y-1 overflow-y-auto rounded border p-2">
            {options.users.map((recipient) => {
              const checked = recipientIds.includes(recipient.id);
              return <label key={recipient.id} className="flex cursor-pointer items-center gap-3 rounded p-2 hover:bg-muted">
                <input type={recipientMode === "individual" ? "radio" : "checkbox"} checked={checked}
                  onChange={() => setRecipientIds(recipientMode === "individual" ? [recipient.id] : checked ? recipientIds.filter((id) => id !== recipient.id) : [...recipientIds, recipient.id])} />
                <span><span className="block text-sm font-medium">{recipient.fullName}</span><span className="text-xs text-muted-foreground">{recipient.role.replaceAll("_", " ")}</span></span>
              </label>;
            })}
          </div>
          {selectedRecipients.length > 0 && <p className="mt-1 text-xs text-muted-foreground">{selectedRecipients.length} selected</p>}
        </div>}
        <Input label={t("messagesPage.title_optional")} value={title} onChange={(event) => setTitle(event.target.value)} />
        <label className="block text-sm font-medium">{t("messagesPage.message")}<textarea className="input mt-1 min-h-28 w-full" value={firstMessage} onChange={(event) => setFirstMessage(event.target.value)} maxLength={4000} /></label>
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setComposeOpen(false)}>{t("messagesPage.cancel")}</Button><Button disabled={busy || !firstMessage.trim() || (!(recipientMode === "group" || announcement) && recipientIds.length === 0) || ((recipientMode === "group" || announcement) && !groupCode)} onClick={create}>{t("messagesPage.send")}</Button></div>
      </div>
    </Modal>
  </div>;
};
