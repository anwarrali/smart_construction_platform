import { useEffect } from "react";
import { useAuthStore } from "../app/store/auth.store";
import { usePermissionStore } from "../app/store/permission.store";

/**
 * The authenticated user's effective permissions, backend-derived from the
 * central authorization resolver (`GET /access-control/me`), cached so every
 * component that needs a capability check does not each trigger a fetch.
 *
 * This is UX visibility only: the backend re-checks every protected operation
 * regardless of what this hook reports, so it never widens what a person can
 * actually do — it only decides what the interface offers them up front.
 *
 * Most components should reach this indirectly through [[useRole]], which
 * layers the pre-existing role/permission developer API on top.
 */
export const usePermissions = () => {
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const permissions = usePermissionStore((state) => state.permissions);
  const isLoading = usePermissionStore((state) => state.isLoading);
  const error = usePermissionStore((state) => state.error);
  const loadedForUserId = usePermissionStore((state) => state.loadedForUserId);
  const fetchPermissions = usePermissionStore((state) => state.fetch);
  const clearPermissions = usePermissionStore((state) => state.clear);
  const activeProjectId = usePermissionStore((state) => state.activeProjectId);
  const project = usePermissionStore((state) => state.project);
  const enterProject = usePermissionStore((state) => state.enterProject);

  useEffect(() => {
    if (!isAuthenticated || !user) {
      clearPermissions();
      return;
    }
    if (loadedForUserId !== user.id) {
      void fetchPermissions(user.id);
    }
  }, [isAuthenticated, user, loadedForUserId, fetchPermissions, clearPermissions]);

  /* Inside an open project, that project's answer once it has arrived;
     the office-wide one otherwise (and while it loads). */
  const scoped = project && project.id === activeProjectId && project.codes ? project.codes : permissions;
  const hasPermission = (code: string): boolean => scoped?.includes(code) ?? false;
  const hasAnyPermission = (codes: string[]): boolean => codes.some(hasPermission);
  const hasAllPermissions = (codes: string[]): boolean => codes.every(hasPermission);

  return {
    permissions,
    isLoading,
    error,
    /** True once a real (possibly empty) permission list has been loaded for the current user. */
    isReady: permissions !== null && (!activeProjectId || project?.id === activeProjectId),
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    refresh: async () => {
      if (!user) return;
      await fetchPermissions(user.id);
      if (activeProjectId) {
        usePermissionStore.setState({ project: null });
        await enterProject(activeProjectId);
      }
    },
  };
};
