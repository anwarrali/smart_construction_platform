export type UserRole =
  | "admin"
  | "owner"
  | "project_manager"
  | "engineer"
  | "consultant"
  | "worker";

export type UserStatus = "active" | "inactive" | "suspended" | "pending";

export type EngineerDiscipline =
  | "architectural"
  | "civil"
  | "electrical"
  | "mechanical";
export type EngineerAffiliation = "internal_engineer" | "main_contractor" | "external_consultant";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface CreateUserRequest {
  fullName: string;
  email: string;
  password: string;
  role: UserRole;
  phoneNumber?: string;
  organization?: string;
  engineerAffiliation?: EngineerAffiliation;
  engineerProfile?: {
    discipline: EngineerDiscipline;
    employeeId?: string;
  };
}

export interface UpdateUserRequest {
  fullName?: string;
  email?: string;
  role?: UserRole;
  status?: UserStatus;
  phoneNumber?: string;
  organization?: string;
  engineerAffiliation?: EngineerAffiliation;
  engineerProfile?: {
    discipline: EngineerDiscipline;
    employeeId?: string;
    licenseNumber?: string;
    yearsOfExperience?: number;
    canActAsProjectManager?: boolean;
  };
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
}

export interface AuthState {
  user: User | null;
  tokens: AuthTokens | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface User {
  id: string;
  fullName: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  phoneNumber?: string;
  avatarUrl?: string;
  organization?: string;
  engineerAffiliation?: EngineerAffiliation;
  isEmailVerified: boolean;
  isSuperuser: boolean;
  mustChangePassword: boolean;
  invitationAccepted: boolean;
  lastLoginAt?: string;
  telegramChatId?: string;
  notifyByEmail: boolean;
  notifyByTelegram: boolean;
  engineerProfile?: EngineerProfile;
  createdAt: string;
  updatedAt: string;
}

export interface EngineerProfile {
  id: string;
  userId: string;
  discipline: EngineerDiscipline;
  licenseNumber?: string;
  yearsOfExperience?: number;
  employeeId?: string;
  canActAsProjectManager: boolean;
}

export interface ResetPasswordRequest {
  email: string;
}

export interface ConfirmResetPasswordRequest {
  token: string;
  newPassword: string;
}

export interface ChangePasswordRequest {
  currentPassword: string;
  newPassword: string;
}

export interface CreateUserResponse extends User {
  temporaryPassword?: string;
}
