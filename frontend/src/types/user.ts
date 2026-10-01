import type { EngineerProfile, EngineerDiscipline, OrgRoleRef } from "./auth";

export interface UserProfile {
  id: string;
  fullName: string;
  email: string;
  status?: string;
  phoneNumber?: string;
  avatarUrl?: string;
  organization?: string;
  telegramChatId?: string;
  notifyByEmail?: boolean;
  notifyByTelegram?: boolean;
  mustChangePassword?: boolean;
  invitationAccepted?: boolean;
  isEmailVerified?: boolean;
  engineerProfile?: EngineerProfile;
  specialization?: string;
  bio?: string;
  createdAt?: string;
  /** The office role this person holds. */
  orgRole?: OrgRoleRef | null;
  disciplines?: Array<{ id: string; code: string; nameEn: string; nameAr?: string | null }>;
  isInternal?: boolean;
}

export interface UserFilters {
  /** An office role id. */
  roleId?: string;
  search?: string;
  status?: string;
  page?: number;
  limit?: number;
}

export interface UserListItem {
  id: string;
  fullName: string;
  email: string;
  orgRole?: OrgRoleRef | null;
  isActive: boolean;
  status: string;
  assignedProjectsCount: number;
  createdAt: string;
}

export interface UsersResponse {
  items?: UserListItem[];
  data: UserListItem[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export interface UpdateProfileRequest {
  email?: string;
  fullName?: string;
  phoneNumber?: string;
  avatarUrl?: string;
  telegramChatId?: string;
  notifyByEmail?: boolean;
  notifyByTelegram?: boolean;
  engineerProfile?: {
    discipline: EngineerDiscipline;
    licenseNumber?: string;
    yearsOfExperience?: number;
    employeeId?: string;
    canActAsProjectManager?: boolean;
  };
}
