import { useCallback } from "react";
import { useAuthStore } from "../app/store/auth.store";
import api from "../services/api";
import type { LoginRequest } from "../types/auth";

export const useAuth = () => {
  const {
    user,
    tokens,
    isAuthenticated,
    isLoading,
    setAuth,
    setUser,
    setLoading,
    logout: storeLogout,
  } = useAuthStore();

  const login = useCallback(
    async (data: LoginRequest) => {
      setLoading(true);
      try {
        const tokens = await api.auth.login(data);
        localStorage.setItem("scp_access_token", tokens.accessToken);
        localStorage.setItem("scp_refresh_token", tokens.refreshToken);
        const user = await api.auth.me();
        setAuth(user, tokens);
        return user;
      } finally {
        setLoading(false);
      }
    },
    [setAuth, setLoading],
  );

  const logout = useCallback(async () => {
    await api.auth.logout(tokens?.refreshToken).catch(() => {});
    storeLogout();
  }, [storeLogout, tokens?.refreshToken]);

  const refreshUser = useCallback(async () => {
    const user = await api.auth.me();
    setUser(user);
    return user;
  }, [setUser]);

  return {
    user,
    tokens,
    isAuthenticated,
    isLoading,
    login,
    logout,
    refreshUser,
  };
};
