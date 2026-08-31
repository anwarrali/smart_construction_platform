import axios from "../../../services/axios";

/**
 * Configuring the office: roles, disciplines and each project's external
 * parties.
 *
 * These replace the frontend's static role table. A role is a row the office
 * owns now, so the interface reads the list rather than shipping one — which
 * is what lets an office add "Resident Engineer" without a release.
 *
 * Every endpoint is enforced on the server as well; this service only drives
 * the interface.
 */

export type RoleScope = "ORG" | "PROJECT" | "BOTH";

export type Role = {
  id: string;
  code: string;
  nameEn: string;
  nameAr?: string | null;
  description?: string | null;
  scope: RoleScope;
  /** Office staff only. An external participant can never hold it. */
  isInternalOnly: boolean;
  /** Seeded by the platform. Still renameable and re-permissionable. */
  isSystem: boolean;
  /** The office administrator role; the server refuses to delete it. */
  undeletable: boolean;
  rank: number;
  isActive: boolean;
  permissions: string[];
  /** How many people hold it, so the cost of a change is visible first. */
  memberCount: number;
};

export type Discipline = {
  id: string;
  code: string;
  nameEn: string;
  nameAr?: string | null;
  /** IFC classification names this discipline covers. */
  ifcDisciplines: string[];
  rank: number;
  isActive: boolean;
};

export type PartyKind =
  | "CLIENT"
  | "MAIN_CONTRACTOR"
  | "SUBCONTRACTOR"
  | "CONSULTANT"
  | "SUPPLIER"
  | "AUTHORITY"
  | "OTHER";

export type ProjectParty = {
  id: string;
  projectId: string;
  kind: PartyKind;
  displayName: string;
  /** A subcontractor points at the contractor it works under. */
  parentPartyId?: string | null;
  isPrimary: boolean;
  contactName?: string | null;
  contactEmail?: string | null;
  contactPhone?: string | null;
  notes?: string | null;
  isActive: boolean;
  memberCount: number;
};

export type RoleDraft = {
  code: string;
  nameEn: string;
  nameAr?: string;
  description?: string;
  scope?: RoleScope;
  isInternalOnly?: boolean;
  rank?: number;
  permissions?: string[];
};

export const organizationService = {
  roles: () => axios.get<Role[]>("/organization/roles").then((r) => r.data),
  createRole: (draft: RoleDraft) =>
    axios.post<Role>("/organization/roles", draft).then((r) => r.data),
  updateRole: (roleId: string, patch: Partial<RoleDraft> & { isActive?: boolean }) =>
    axios.patch<Role>(`/organization/roles/${roleId}`, patch).then((r) => r.data),
  setRolePermissions: (roleId: string, permissions: string[]) =>
    axios
      .put<Role>(`/organization/roles/${roleId}/permissions`, { permissions })
      .then((r) => r.data),
  deleteRole: (roleId: string) =>
    axios.delete(`/organization/roles/${roleId}`).then((r) => r.data),

  assignUserRole: (userId: string, roleId: string, jobTitle?: string) =>
    axios
      .put<Role>(`/organization/users/${userId}/role`, { roleId, jobTitle })
      .then((r) => r.data),
  setUserDisciplines: (
    userId: string,
    disciplineIds: string[],
    primaryDisciplineId?: string | null,
  ) =>
    axios
      .put<{ disciplines: string[] }>(`/organization/users/${userId}/disciplines`, {
        disciplineIds,
        primaryDisciplineId: primaryDisciplineId ?? null,
      })
      .then((r) => r.data),

  disciplines: () =>
    axios.get<Discipline[]>("/organization/disciplines").then((r) => r.data),
  createDiscipline: (draft: {
    code: string;
    nameEn: string;
    nameAr?: string;
    ifcDisciplines?: string[];
    rank?: number;
  }) => axios.post<Discipline>("/organization/disciplines", draft).then((r) => r.data),
  updateDiscipline: (
    disciplineId: string,
    patch: Partial<{
      nameEn: string;
      nameAr: string;
      ifcDisciplines: string[];
      rank: number;
      isActive: boolean;
    }>,
  ) =>
    axios
      .patch<Discipline>(`/organization/disciplines/${disciplineId}`, patch)
      .then((r) => r.data),

  partyKinds: () =>
    axios.get<{ kinds: PartyKind[] }>("/organization/party-kinds").then((r) => r.data.kinds),
  parties: (projectId: string) =>
    axios
      .get<ProjectParty[]>(`/projects/${encodeURIComponent(projectId)}/parties`)
      .then((r) => r.data),
  createParty: (
    projectId: string,
    draft: {
      kind: PartyKind;
      displayName: string;
      parentPartyId?: string | null;
      isPrimary?: boolean;
      contactName?: string;
      contactEmail?: string;
      contactPhone?: string;
      notes?: string;
    },
  ) =>
    axios
      .post<ProjectParty>(`/projects/${encodeURIComponent(projectId)}/parties`, draft)
      .then((r) => r.data),
  updateParty: (
    projectId: string,
    partyId: string,
    patch: Partial<{
      displayName: string;
      parentPartyId: string | null;
      isPrimary: boolean;
      contactName: string;
      contactEmail: string;
      contactPhone: string;
      notes: string;
      isActive: boolean;
    }>,
  ) =>
    axios
      .patch<ProjectParty>(
        `/projects/${encodeURIComponent(projectId)}/parties/${partyId}`,
        patch,
      )
      .then((r) => r.data),
  deleteParty: (projectId: string, partyId: string) =>
    axios
      .delete(`/projects/${encodeURIComponent(projectId)}/parties/${partyId}`)
      .then((r) => r.data),
};

export default organizationService;
