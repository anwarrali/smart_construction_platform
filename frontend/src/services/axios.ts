import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from "../utils/constants";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "") || "/api/v1";

const axiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

const getTokens = () => {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!accessToken || !refreshToken) return null;
  return { accessToken, refreshToken };
};

const setAccessToken = (token: string) => {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
};

const clearTokens = () => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem("scp_user");
};

const refreshAccessToken = async (): Promise<string> => {
  const tokens = getTokens();
  if (!tokens?.refreshToken) {
    throw new Error("No refresh token available");
  }

  // Use a bare client: sending refresh through axiosInstance would let a 401
  // from the refresh endpoint recursively invoke this interceptor forever.
  const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
    refresh_token: tokens.refreshToken,
  });

  const { access_token, refresh_token } = response.data;
  setAccessToken(access_token);
  if (refresh_token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token);
  }

  return access_token;
};

axiosInstance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const tokens = getTokens();
    if (tokens?.accessToken && config.headers) {
      config.headers.Authorization = `Bearer ${tokens.accessToken}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

axiosInstance.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const tokens = getTokens();

      if (tokens?.refreshToken) {
        try {
          const newAccessToken = await refreshAccessToken();
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          }
          return axiosInstance(originalRequest);
        } catch {
          clearTokens();
          window.location.href = "/auth/login";
          return Promise.reject(error);
        }
      }

      clearTokens();
      window.location.href = "/auth/login";
    }

    return Promise.reject(error);
  },
);

export default axiosInstance;
