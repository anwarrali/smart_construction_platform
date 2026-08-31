/**
 * The retired platform roles.
 *
 * Roles are configured by the office now and come from
 * `GET /organization/roles`; this union is what the API still returns on
 * `User.role` while the legacy column exists, and it is used for
 * presentation fallbacks only. New code should read the `Role` record
 * rather than branch on these strings.
 *
 * `worker` is gone: workers are not platform users. Field evidence is
 * recorded by whoever holds `field_evidence.submit` — normally a Site
 * Engineer.
 */
export type UserRole =
  | "admin"
  | "owner"
  | "project_manager"
  | "engineer"
  | "consultant";

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
  /**
   * The office role the account is created under — a row the administrator
   * maintains, not a value from a fixed union. It decides the permissions,
   * whether the person is office staff, and (until the contract migration)
   * which legacy value the server writes to `role`.
   */
  orgRoleId?: string;
  /** Specializations the person practises. Several is normal. */
  disciplineIds?: string[];
  /** Retired. Sent only when no office role is available to send. */
  role?: UserRole;
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
  /**
   * The office role this person holds — the authority. `role` above is the
   * retired enum, still returned while the column exists and used only as a
   * presentation fallback for an account the backfill has not reached.
   */
  orgRole?: {
    id: string;
    code: string;
    nameEn: string;
    nameAr?: string | null;
    isInternalOnly: boolean;
  } | null;
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
