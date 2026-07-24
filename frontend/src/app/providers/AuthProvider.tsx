import { useEffect, type ReactNode } from "react";
import { useAuthStore } from "../store/auth.store";
import api from "../../services/api";

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const { isAuthenticated, setUser, logout } = useAuthStore();

  useEffect(() => {
    const initAuth = async () => {
      if (isAuthenticated) {
        try {
          const user = await api.auth.me();
          setUser(user);
        } catch {
          logout();
        }
      }
    };
    initAuth();
  }, []);

  return <>{children}</>;
};
