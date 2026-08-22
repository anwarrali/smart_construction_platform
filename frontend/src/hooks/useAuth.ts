import { useCallback } from "react";
import { useAuthStore } from "../app/store/auth.store";
import api from "../services/api";
import { getDeviceId, teardownWebPush } from "../services/push/webPush";
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
    // Retire this browser's push registration *before* the session ends, while
    // the access token is still valid. Skipping it would leave a shared
    // machine delivering this user's notifications to whoever signs in next —
    // and after `storeLogout()` there is no longer a token to authorize the
    // call with. Both halves are best-effort: signing out must never be
    // blocked by the network.
    await api.notifications.unregisterDevice({ deviceId: getDeviceId() }).catch(() => {});
    await teardownWebPush();
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
