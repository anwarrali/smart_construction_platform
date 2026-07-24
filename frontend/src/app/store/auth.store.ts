import { create } from "zustand";
import type { User, AuthTokens } from "../../types/auth";

interface AuthState {
  user: User | null;
  tokens: AuthTokens | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  setAuth: (user: User, tokens: AuthTokens) => void;
  setUser: (user: User) => void;
  setTokens: (tokens: AuthTokens) => void;
  setLoading: (isLoading: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: (() => {
    const stored = localStorage.getItem("scp_user");
    return stored ? JSON.parse(stored) : null;
  })(),
  tokens: (() => {
    const accessToken = localStorage.getItem("scp_access_token");
    const refreshToken = localStorage.getItem("scp_refresh_token");
    return accessToken && refreshToken
      ? { accessToken, refreshToken, tokenType: "bearer" }
      : null;
  })(),
  isAuthenticated: (() => {
    return !!localStorage.getItem("scp_access_token");
  })(),
  isLoading: false,

  setAuth: (user, tokens) => {
    localStorage.setItem("scp_user", JSON.stringify(user));
    localStorage.setItem("scp_access_token", tokens.accessToken);
    localStorage.setItem("scp_refresh_token", tokens.refreshToken);
    set({ user, tokens, isAuthenticated: true, isLoading: false });
  },

  setUser: (user) => {
    localStorage.setItem("scp_user", JSON.stringify(user));
    set({ user });
  },

  setTokens: (tokens) => {
    localStorage.setItem("scp_access_token", tokens.accessToken);
    localStorage.setItem("scp_refresh_token", tokens.refreshToken);
    set({ tokens });
  },

  setLoading: (isLoading) => set({ isLoading }),

  logout: () => {
    localStorage.removeItem("scp_user");
    localStorage.removeItem("scp_access_token");
    localStorage.removeItem("scp_refresh_token");
    set({ user: null, tokens: null, isAuthenticated: false, isLoading: false });
  },
}));
