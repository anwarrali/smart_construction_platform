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

// The refresh token is single-use: the server rotates it on every call and
// revokes the old one. When an access token expires, several requests
// typically 401 within the same tick (e.g. a page that fires a Promise.all
// of several fetches) and each used to call this independently — the second
// one to reach the server would hit an already-revoked token. Sharing one
// in-flight promise means only the first caller actually hits the network;
// everyone else awaits that same result instead of racing it.
let refreshInFlight: Promise<string> | null = null;

const refreshAccessToken = (): Promise<string> => {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
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
  })().finally(() => {
    refreshInFlight = null;
  });

  return refreshInFlight;
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

/** The server's marker for "authenticated, but this action needs step-up". */
export interface StepUpChallengeInfo {
  code: "STEP_UP_REQUIRED";
  purpose: string;
  label: string;
}

export const stepUpInfo = (error: unknown): StepUpChallengeInfo | null => {
  const detail = (error as AxiosError<{ detail?: StepUpChallengeInfo }>)?.response?.data?.detail;
  return detail && typeof detail === "object" && detail.code === "STEP_UP_REQUIRED"
    ? detail
    : null;
};

const isStepUpRequired = (error: AxiosError) =>
  error.response?.status === 401 && stepUpInfo(error) !== null;

axiosInstance.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // A step-up challenge also answers 401, but it means "this session is
    // fine, prove it is really you" — not "your token expired". Without this
    // guard it would fall into the refresh path below, burn the single-use
    // refresh token on a request that was never going to succeed, and finally
    // sign the user out for asking to change their own password.
    if (isStepUpRequired(error)) {
      return Promise.reject(error);
    }

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
