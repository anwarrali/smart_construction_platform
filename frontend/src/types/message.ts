import type { User } from "./auth";

export type ConversationType = "DIRECT" | "GROUP" | "PROJECT_CHANNEL" | "CONTEXTUAL";

export interface ConversationParticipant {
  userId: string;
  user: User;
  joinedAt: string;
  lastReadAt?: string;
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
