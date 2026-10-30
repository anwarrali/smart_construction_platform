import axios from "../../../services/axios";

export type Permission = {
  code: string;
  group: string;
  label: string;
  description: string;
  projectScoped: boolean;
  adminLocked: boolean;
  /** Stripped from anybody outside the office, whatever their role grants. */
  officeOnly: boolean;
  /** Never held by an external participant. */
  neverExternal: boolean;
  /** Another condition the server checks before this permission does anything. */
  prerequisite?: string | null;
  /** Project-scoped codes apply only on projects the person can open. */
  scopeNote?: string | null;
};

export type UserPermissionOverride = {
  id: string;
  userId: string;
  projectId?: string | null;
  permissionCode: string;
  allowed: boolean;
  reason?: string | null;
};

/** Why the server says a permission is or is not held (`authorization.explain_permissions`). */
export type PermissionReason =
  | "granted_by_role"
  | "granted_by_project_role"
  | "granted_to_user"
  | "granted_on_project"
  | "admin_locked"
  | "denied_for_user"
  | "denied_on_project"
  | "blocked_external"
  | "blocked_project_access"
  | "account_inactive"
  | "not_granted";

export type PermissionDecision = {
  code: string;
  /** The effective answer — membership of the server's resolved set. */
  held: boolean;
  reason: PermissionReason;
  /** Whether the governing role confers it. */
  roleGrants: boolean;
  /** The explicit decision at this scope; null = inherits from the role. */
  override: boolean | null;
};

export type UserPermissionSummary = {
  userId: string;
  fullName: string;
  email: string;
  /** The office role the person holds. */
  roleCode?: string | null;
  roleName?: string | null;
  /** The role whose permissions apply — the office's copy of an edited template. */
  governingRoleId?: string | null;
  governingRoleName?: string | null;
  governedByOfficeCopy?: boolean;
  status: string;
  projectId?: string | null;
  effectivePermissions: string[];
  overrides: UserPermissionOverride[];
  decisions?: PermissionDecision[];
};

export type ConsultantScope = {
  projectId: string;
  consultantUserId: string;
  consultantName: string;
  approvalMode: string;
  disciplines: (string | null)[];
  engineerUserIds: string[];
};

/**
 * The administrator's view of access control. Every one of these endpoints is
 * gated on the server as well; this service only drives the interface.
 */
export const accessControlService = {
  permissions: () => axios.get<Permission[]>("/access-control/permissions").then((r) => r.data),
  user: (userId: string, projectId?: string) =>
    axios.get<UserPermissionSummary>(`/access-control/users/${userId}`, {
      params: projectId ? { project_id: projectId } : undefined,
    }).then((r) => r.data),
  setUserPermission: (userId: string, permissionCode: string, allowed: boolean | null, projectId?: string | null) =>
    axios.put<UserPermissionSummary>(`/access-control/users/${userId}`, {
      permissionCode, allowed, projectId: projectId ?? null,
    }).then((r) => r.data),
  consultants: (projectId: string) =>
    axios.get<ConsultantScope[]>(`/access-control/projects/${projectId}/consultants`).then((r) => r.data),
  setConsultantScope: (projectId: string, consultantUserId: string, engineerUserIds: string[]) =>
    axios.put<ConsultantScope>(`/access-control/projects/${projectId}/consultants`, {
      projectId, consultantUserId, engineerUserIds,
    }).then((r) => r.data),
  mine: (projectId?: string) =>
    axios.get<string[]>("/access-control/me", {
      params: projectId ? { project_id: projectId } : undefined,
    }).then((r) => r.data),
};

export default accessControlService;
