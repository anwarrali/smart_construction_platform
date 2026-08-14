import axios from "../../../services/axios";

export type Permission = {
  code: string;
  group: string;
  label: string;
  description: string;
  defaultRoles: string[];
  projectScoped: boolean;
  adminLocked: boolean;
};

export type RolePermissionState = {
  role: string;
  permissionCode: string;
  defaultAllowed: boolean;
  effectiveAllowed: boolean;
  overridden: boolean;
};

export type UserPermissionOverride = {
  id: string;
  userId: string;
  projectId?: string | null;
  permissionCode: string;
  allowed: boolean;
  reason?: string | null;
};

export type UserPermissionSummary = {
  userId: string;
  fullName: string;
  email: string;
  role: string;
  status: string;
  projectId?: string | null;
  effectivePermissions: string[];
  overrides: UserPermissionOverride[];
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
  roleMatrix: () => axios.get<RolePermissionState[]>("/access-control/roles").then((r) => r.data),
  setRolePermission: (role: string, permissionCode: string, allowed: boolean | null) =>
    axios.put<RolePermissionState>("/access-control/roles", { role, permissionCode, allowed }).then((r) => r.data),
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
