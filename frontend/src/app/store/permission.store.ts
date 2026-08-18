import { create } from "zustand";
import accessControlService from "../../features/admin/services/accessControl.service";

interface PermissionState {
  /** null = not loaded yet (or cleared on logout); never confused with "loaded, zero permissions". */
  permissions: string[] | null;
  isLoading: boolean;
  error: string | null;
  /** The user this snapshot belongs to, so a different user's cached list is never shown. */
  loadedForUserId: string | null;
  fetch: (userId: string) => Promise<void>;
  clear: () => void;
}

/**
 * The frontend's cache of the caller's effective permissions, as resolved by
 * the backend's central authorization service (GET /access-control/me). This
 * is presentation state only — every protected operation is re-checked on the
 * server, exactly as documented on that endpoint. See [[useRole]]/[[usePermissions]]
 * for the hook most components should use instead of this store directly.
 */
export const usePermissionStore = create<PermissionState>((set, get) => ({
  permissions: null,
  isLoading: false,
  error: null,
  loadedForUserId: null,

  fetch: async (userId: string) => {
    // Guards against every component that calls useRole() mounting at once
    // after login and firing off a duplicate request each.
    if (get().isLoading) return;
    set({ isLoading: true, error: null });
    try {
      const codes = await accessControlService.mine();
      set({ permissions: codes, isLoading: false, loadedForUserId: userId, error: null });
    } catch {
      set({ isLoading: false, error: "Unable to load permissions", permissions: null, loadedForUserId: null });
    }
  },

  clear: () => set({ permissions: null, isLoading: false, error: null, loadedForUserId: null }),
}));
