import type { User } from "./auth";

export type ConversationType = "DIRECT" | "GROUP" | "PROJECT_CHANNEL" | "CONTEXTUAL";

export interface ConversationParticipant {
  userId: string;
  user: User;
  joinedAt: string;
  lastReadAt?: string;
}

/** Project entities that can be shared into a conversation (see the backend's
 *  SHARED_ENTITY_LABELS — this list must stay in step with it). */
export type SharedEntityType =
  | "ISSUE"
  | "TASK"
  | "SITE_REPORT"
  | "DESIGN_CHANGE"
  | "DOCUMENT";

export interface ForwardOrigin {
  messageId: string;
  conversationId: string;
  sender: User;
  content: string;
  createdAt: string;
}

export interface ProjectMessage {
  id: string;
  conversationId: string;
  senderId: string;
  content: string;
  sender: User;
  createdAt: string;
  updatedAt: string;
  editedAt?: string;
  deletedAt?: string;
  /** Set when this message was created by forwarding another one. */
  forwardedFromMessageId?: string;
  /** The first, non-forwarded message in the chain — who it truly came from. */
  forwardOrigin?: ForwardOrigin;
  /** Set when this message was created by sharing a project entity. */
  sharedEntityType?: SharedEntityType;
  sharedEntityId?: string;
}

export interface Conversation {
  id: string;
  projectId: string;
  type: ConversationType;
  title?: string;
  createdById: string;
  contextType?: "TASK" | "ISSUE";
  contextId?: string;
  recipientGroup?: string;
  lastActivityAt: string;
  participants: ConversationParticipant[];
  lastMessage?: ProjectMessage;
  unreadCount: number;
  createdAt: string;
}

export interface ConversationDetail extends Conversation {
  messages: ProjectMessage[];
}

export interface ConversationPage {
  items: Conversation[];
  total: number;
  page: number;
  pageSize: number;
}

export interface RecipientGroup {
  code: string;
  label: string;
  recipientCount: number;
}

export interface RecipientOptions {
  users: User[];
  groups: RecipientGroup[];
}
