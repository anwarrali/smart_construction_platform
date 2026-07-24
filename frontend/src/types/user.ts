import type { UserRole, EngineerProfile, EngineerDiscipline, EngineerAffiliation } from "./auth";

export interface UserProfile {
  id: string;
  fullName: string;
  email: string;
  role: UserRole;
  status?: string;
  phoneNumber?: string;
  avatarUrl?: string;
  organization?: string;
  engineerAffiliation?: EngineerAffiliation;
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
}

export interface UserFilters {
  role?: UserRole;
  search?: string;
  status?: string;
  page?: number;
  limit?: number;
}

export interface UserListItem {
  id: string;
  fullName: string;
  email: string;
  role: UserRole;
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
