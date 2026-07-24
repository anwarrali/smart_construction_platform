import { create } from "zustand";
import type { UserProfile } from "../../types/user";

interface UserState {
  profile: UserProfile | null;
  users: UserProfile[];
  selectedUserId: string | null;
  isProfileLoading: boolean;
  isUsersLoading: boolean;

  setProfile: (profile: UserProfile) => void;
  setUsers: (users: UserProfile[]) => void;
  setSelectedUser: (userId: string | null) => void;
  updateProfile: (updates: Partial<UserProfile>) => void;
  setProfileLoading: (loading: boolean) => void;
  setUsersLoading: (loading: boolean) => void;
  clearUsers: () => void;
}

export const useUserStore = create<UserState>((set) => ({
  profile: null,
  users: [],
  selectedUserId: null,
  isProfileLoading: false,
  isUsersLoading: false,

  setProfile: (profile) => set({ profile, isProfileLoading: false }),

  setUsers: (users) => set({ users, isUsersLoading: false }),

  setSelectedUser: (userId) => set({ selectedUserId: userId }),

  updateProfile: (updates) =>
    set((state) => ({
      profile: state.profile ? { ...state.profile, ...updates } : null,
    })),

  setProfileLoading: (loading) => set({ isProfileLoading: loading }),

  setUsersLoading: (loading) => set({ isUsersLoading: loading }),

  clearUsers: () => set({ users: [], selectedUserId: null }),
}));
