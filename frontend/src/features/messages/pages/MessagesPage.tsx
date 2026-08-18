import { useCallback, useEffect, useMemo, useState } from "react";
import { formatDateTime } from "../../../utils/dates";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import toast from "react-hot-toast";
import { Forward, ExternalLink } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Modal } from "../../../components/ui/Modal";
import { Select } from "../../../components/ui/Select";
import { useAuth } from "../../../hooks/useAuth";
import { useRole } from "../../../hooks/useRole";
import api from "../../../services/api";
import type { Conversation, ConversationDetail, ConversationType, ProjectMessage, RecipientOptions } from "../../../types/message";
import type { Project } from "../../../types/project";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";
import { projectEntityPath } from "../../../utils/projectRoutes";

type Tab = "all" | "unread" | "direct" | "teams" | "project";

export const MessagesPage = () => {
  const { t } = useTranslation();
  const workspace = useProjectWorkspace();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { isAdmin, isProjectManager, role, isConsultantEngineer } = useRole();
  // "View original" must land inside the role's own project workspace: the
  // portfolio-level /issues route redirects role-scoped users to their
  // dashboard and drops the query parameter, so the entity would be lost.
  const affiliation = isConsultantEngineer ? ("external_consultant" as const) : undefined;
  // Sharing an entity happens away from this page and then lands here, so the
  // conversation it created is selected from the URL on arrival.
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedConversationId = searchParams.get("conversationId");
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
  const [forwardingMessage, setForwardingMessage] = useState<ProjectMessage | null>(null);
  const [forwardRecipientMode, setForwardRecipientMode] = useState<"individual" | "multiple" | "group">("individual");
  const [forwardRecipientIds, setForwardRecipientIds] = useState<string[]>([]);
  const [forwardGroupCode, setForwardGroupCode] = useState("");
  const [forwardNote, setForwardNote] = useState("");
  const [forwardBusy, setForwardBusy] = useState(false);

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
  // Consumed once: after selecting the requested conversation the parameter is
  // dropped, so a later manual selection is not overridden on the next render.
  useEffect(() => {
    if (!requestedConversationId) return;
    setSelectedId(requestedConversationId);
    const next = new URLSearchParams(searchParams);
    next.delete("conversationId");
    setSearchParams(next, { replace: true });
  }, [requestedConversationId, searchParams, setSearchParams]);
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

  const openForward = (message: ProjectMessage) => {
    setForwardingMessage(message);
    setForwardRecipientMode("individual");
    setForwardRecipientIds([]);
    setForwardGroupCode("");
    setForwardNote("");
  };

  // Recipients come from the same `recipientOptions` the compose modal uses —
  // the same server-side `can_message_user` / group resolution, so the picker
  // can never offer someone the backend would reject anyway (2.7). The backend
  // still re-validates on submit regardless of what this list shows.
  const submitForward = async () => {
    if (!forwardingMessage) return;
    setForwardBusy(true);
    try {
      const conversation = await api.messages.forward(forwardingMessage.id, {
        recipientIds: forwardRecipientMode === "group" ? [] : forwardRecipientIds,
        groupCode: forwardRecipientMode === "group" ? forwardGroupCode : undefined,
        note: forwardNote.trim() || undefined,
      });
      setForwardingMessage(null);
      await loadList();
      setSelectedId(conversation.id);
      await loadDetail();
      toast.success(t("messagesPage.message_forwarded"));
    } catch (err: any) {
      toast.error(errorMessage(err, t("messagesPage.forward_failed")));
    } finally { setForwardBusy(false); }
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
              <span>{formatDateTime(conversation.lastActivityAt)}</span>
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
              const origin = message.forwardOrigin;
              return <div key={message.id} className={`group flex ${mine ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-xl px-4 py-2 text-sm ${mine ? "bg-primary text-primary-foreground" : "border bg-card"}`}>
                  {!mine && detail.type !== "DIRECT" && <p className="mb-1 text-xs font-semibold text-primary">{message.sender.fullName}</p>}
                  {/* A forwarded message never reads as if the forwarder wrote
                      the original content themselves (2.3 / 2.4): the quoted
                      block always names the true original sender, resolved to
                      the root of the chain even after several forwards. */}
                  {origin && (
                    <div className={`mb-2 rounded-lg border-l-2 px-2 py-1.5 text-xs ${mine ? "border-primary-foreground/40 bg-primary-foreground/10" : "border-primary/40 bg-muted/40"}`}>
                      <p className={`flex items-center gap-1 font-medium ${mine ? "text-primary-foreground/80" : "text-primary"}`}>
                        <Forward size={11} className="rtl-flip" /> {t("messagesPage.forwarded_from", { name: origin.sender.fullName })}
                      </p>
                      <p className={`mt-0.5 line-clamp-3 whitespace-pre-wrap break-words ${mine ? "text-primary-foreground/70" : "text-muted-foreground"}`}>{origin.content}</p>
                    </div>
                  )}
                  <p className="whitespace-pre-wrap break-words">{message.content}</p>
                  {/* A shared entity gets a way back to the entity itself. The
                      destination page re-checks permission on load, so showing
                      the link never implies the recipient may read it. */}
                  {message.sharedEntityType && message.sharedEntityId && (
                    <button
                      type="button"
                      onClick={() => navigate(projectEntityPath(
                        detail.projectId, message.sharedEntityType!, message.sharedEntityId!,
                        role, affiliation,
                      ))}
                      className={`mt-2 inline-flex items-center gap-1 text-xs font-medium underline ${mine ? "text-primary-foreground/90" : "text-primary"}`}
                    >
                      <ExternalLink size={11} className="rtl-flip" />
                      {t(`communication.viewOriginal.${message.sharedEntityType}`)}
                    </button>
                  )}
                  <div className="mt-1 flex items-center justify-between gap-3">
                    <p className={`text-[10px] ${mine ? "text-primary-foreground/70" : "text-muted-foreground"}`}>{formatDateTime(message.createdAt)}</p>
                    <button
                      type="button"
                      onClick={() => openForward(message)}
                      title={t("messagesPage.forward")}
                      className={`opacity-0 transition-opacity group-hover:opacity-100 ${mine ? "text-primary-foreground/70 hover:text-primary-foreground" : "text-muted-foreground hover:text-primary"}`}
                    >
                      <Forward size={13} className="rtl-flip" />
                    </button>
                  </div>
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

    <Modal isOpen={!!forwardingMessage} onClose={() => setForwardingMessage(null)} title={t("messagesPage.forward_message")} size="lg">
      <div className="space-y-4">
        {forwardingMessage && <div className="rounded-lg border-l-2 border-primary/40 bg-muted/40 px-3 py-2 text-xs">
          <p className="font-medium text-primary">{forwardingMessage.sender.fullName}</p>
          <p className="mt-0.5 line-clamp-3 whitespace-pre-wrap break-words text-muted-foreground">{forwardingMessage.content}</p>
        </div>}
        <Select label={t("messagesPage.send_to")} value={forwardRecipientMode} onChange={(event) => { setForwardRecipientMode(event.target.value as typeof forwardRecipientMode); setForwardRecipientIds([]); setForwardGroupCode(""); }} options={[
          { value: "individual", label: "Individual" },
          { value: "multiple", label: "Multiple People" },
          ...(options.groups.length ? [{ value: "group", label: "Team / Group" }] : []),
        ]} />
        {forwardRecipientMode === "group" ? <Select label={t("messagesPage.recipient_group")} value={forwardGroupCode} onChange={(event) => setForwardGroupCode(event.target.value)} options={
          options.groups.map((group) => ({ value: group.code, label: `${group.label} (${group.recipientCount})` }))
        } /> : <div>
          <p className="mb-2 text-sm font-medium">{t("messagesPage.project_recipients")}</p>
          <div className="max-h-56 space-y-1 overflow-y-auto rounded border p-2">
            {options.users.map((recipient) => {
              const checked = forwardRecipientIds.includes(recipient.id);
              return <label key={recipient.id} className="flex cursor-pointer items-center gap-3 rounded p-2 hover:bg-muted">
                <input type={forwardRecipientMode === "individual" ? "radio" : "checkbox"} checked={checked}
                  onChange={() => setForwardRecipientIds(forwardRecipientMode === "individual" ? [recipient.id] : checked ? forwardRecipientIds.filter((id) => id !== recipient.id) : [...forwardRecipientIds, recipient.id])} />
                <span><span className="block text-sm font-medium">{recipient.fullName}</span><span className="text-xs text-muted-foreground">{recipient.role.replaceAll("_", " ")}</span></span>
              </label>;
            })}
          </div>
        </div>}
        <label className="block text-sm font-medium">{t("messagesPage.forward_note_optional")}
          <textarea className="input mt-1 min-h-20 w-full" value={forwardNote} onChange={(event) => setForwardNote(event.target.value)} maxLength={4000} placeholder={t("messagesPage.forward_note_placeholder")} />
        </label>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setForwardingMessage(null)}>{t("messagesPage.cancel")}</Button>
          <Button
            disabled={forwardBusy || (forwardRecipientMode === "group" ? !forwardGroupCode : forwardRecipientIds.length === 0)}
            onClick={submitForward}
          >{t("messagesPage.forward")}</Button>
        </div>
      </div>
    </Modal>
  </div>;
};
