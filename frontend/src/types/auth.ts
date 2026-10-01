/**
 * The office role an account holds — a row the office maintains
 * (`GET /organization/roles`), never a fixed union. It names the person's
 * role and says whether they are office staff; what they may do comes from
 * `GET /access-control/me`.
 */
export interface OrgRoleRef {
  id: string;
  code: string;
  nameEn: string;
  nameAr?: string | null;
  isInternalOnly: boolean;
}

export type UserStatus = "active" | "inactive" | "suspended" | "pending";

export type EngineerDiscipline =
  | "architectural"
  | "civil"
  | "electrical"
  | "mechanical";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface CreateUserRequest {
  fullName: string;
  email: string;
  password: string;
  /**
   * The office role the account is created under — a row the administrator
   * maintains. It decides the permissions and whether the person is office
   * staff. Required: no account exists without one.
   */
  orgRoleId: string;
  /** Specializations the person practises. Several is normal. */
  disciplineIds?: string[];
  phoneNumber?: string;
  organization?: string;
  engineerProfile?: {
    discipline: EngineerDiscipline;
    employeeId?: string;
  };
}

export interface UpdateUserRequest {
  fullName?: string;
  email?: string;
  /** Move the account to another office role. */
  orgRoleId?: string;
  disciplineIds?: string[];
  status?: UserStatus;
  phoneNumber?: string;
  organization?: string;
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
  status: UserStatus;
  phoneNumber?: string;
  avatarUrl?: string;
  organization?: string;
  isEmailVerified: boolean;
  isSuperuser: boolean;
  mustChangePassword: boolean;
  invitationAccepted: boolean;
  lastLoginAt?: string;
  telegramChatId?: string;
  notifyByEmail: boolean;
  notifyByTelegram: boolean;
  engineerProfile?: EngineerProfile;
  /** The office role this person holds. */
  orgRole?: OrgRoleRef | null;
  disciplines?: Array<{ id: string; code: string; nameEn: string; nameAr?: string | null }>;
  /** Consulting-office staff, as opposed to an external participant. */
  isInternal?: boolean;
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
