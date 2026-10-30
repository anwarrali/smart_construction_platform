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
  /** The project workspace currently open, if any. */
  activeProjectId: string | null;
  /** That project's effective permissions — `GET /access-control/me?project_id=`.
   *  `codes: null` means the request failed: fall back to the office-wide list. */
  project: { id: string; codes: string[] | null } | null;
  enterProject: (projectId: string) => Promise<void>;
  leaveProject: () => void;
  /** Re-read both answers without blanking them first — see `revalidate`. */
  revalidate: () => Promise<void>;
  clear: () => void;
}

/** A 403 or a refocused tab asks again at most this often. */
export const REVALIDATE_MIN_INTERVAL_MS = 5000;
/** Fired by the API client on a 403; see `services/axios.ts`. */
export const PERMISSIONS_STALE_EVENT = "permissions:stale";

let lastRevalidation = 0;

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

  activeProjectId: null,
  project: null,

  /* Inside a project the answer can differ from the office-wide one: a project
     role can add permissions, and since QA-06B the administrator holds the
     registry side (team, parties) of a project they are not on, but not its
     work. Without this the menu offered Tasks, Documents and IFC on such a
     project and every one of them answered 403. */
  enterProject: async (projectId: string) => {
    if (get().activeProjectId === projectId && get().project?.id === projectId) return;
    set({ activeProjectId: projectId });
    try {
      const codes = await accessControlService.mine(projectId);
      if (get().activeProjectId === projectId) set({ project: { id: projectId, codes } });
    } catch {
      // Falls back to the office-wide answer — read when asked, not copied
      // now, since it may not have arrived yet — so readiness never hangs on a
      // failed request; every endpoint re-checks anyway.
      if (get().activeProjectId === projectId) {
        set({ project: { id: projectId, codes: null } });
      }
    }
  },

  leaveProject: () => set({ activeProjectId: null, project: null }),

  /* Permissions change while people are signed in: an administrator grants
     or revokes something, or edits the role the person holds. The snapshot
     above was taken at sign-in, so without this an open tab kept offering a
     revoked action (refused by the server, but still on screen) and never
     showed a new grant until a reload. Asked again when the tab regains focus
     and whenever the server answers 403 — the moment the snapshot has been
     shown to be wrong. The previous answer stays until the new one arrives,
     so nothing flickers; a failed re-read keeps it, since every endpoint
     re-checks anyway. */
  revalidate: async () => {
    const { loadedForUserId, activeProjectId } = get();
    const now = Date.now();
    if (!loadedForUserId || now - lastRevalidation < REVALIDATE_MIN_INTERVAL_MS) return;
    lastRevalidation = now;
    try {
      const [codes, projectCodes] = await Promise.all([
        accessControlService.mine(),
        activeProjectId ? accessControlService.mine(activeProjectId) : Promise.resolve(null),
      ]);
      if (get().loadedForUserId !== loadedForUserId) return;
      set({ permissions: codes });
      if (activeProjectId && get().activeProjectId === activeProjectId && projectCodes) {
        set({ project: { id: activeProjectId, codes: projectCodes } });
      }
    } catch {
      // Keep the previous answer; see above.
    }
  },

  clear: () => {
    lastRevalidation = 0;
    set({
      permissions: null, isLoading: false, error: null, loadedForUserId: null,
      activeProjectId: null, project: null,
    });
  },
}));

if (typeof window !== "undefined") {
  const revalidate = () => { void usePermissionStore.getState().revalidate(); };
  window.addEventListener(PERMISSIONS_STALE_EVENT, revalidate);
  window.addEventListener("focus", revalidate);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") revalidate();
  });
}
