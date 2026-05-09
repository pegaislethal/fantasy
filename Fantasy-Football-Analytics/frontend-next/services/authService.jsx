import { apiPost } from "@/services/api";

function setCookie(name, value, maxAgeSeconds) {
  const encoded = encodeURIComponent(value);
  document.cookie = `${name}=${encoded}; Path=/; Max-Age=${maxAgeSeconds};`;
}

export async function login(payload) {
  const res = await apiPost("/api/auth/login/", payload);
  try {
    if (res?.tokens?.access) {
      // access token: 30 minutes
      setCookie("ff_access", res.tokens.access, 30 * 60);
      // store in localStorage if not already present
      if (typeof window !== "undefined" && !localStorage.getItem("ff_access")) {
        localStorage.setItem("ff_access", res.tokens.access);
      }
    }
    if (res?.tokens?.refresh) {
      // refresh token: 7 days
      setCookie("ff_refresh", res.tokens.refresh, 7 * 24 * 60 * 60);
      if (typeof window !== "undefined" && !localStorage.getItem("ff_refresh")) {
        localStorage.setItem("ff_refresh", res.tokens.refresh);
      }
    }
    if (res?.user) {
      if (typeof window !== "undefined" && !localStorage.getItem("ff_user")) {
        try {
          localStorage.setItem("ff_user", JSON.stringify(res.user));
        } catch (e) {
          console.warn("Failed to store user in localStorage", e);
        }
      }
    }
    if (res?.user?.role) {
      setCookie("ff_role", res.user.role, 7 * 24 * 60 * 60);
    }
  } catch (e) {
    // non-fatal: continue returning response
    console.warn("Failed to set auth cookies", e);
  }
  return res;
}

export async function signup(payload) {
  const res = await apiPost("/api/register/", payload);
  try {
    if (res?.tokens?.access) {
      setCookie("ff_access", res.tokens.access, 30 * 60);
      if (typeof window !== "undefined" && !localStorage.getItem("ff_access")) {
        localStorage.setItem("ff_access", res.tokens.access);
      }
    }
    if (res?.tokens?.refresh) {
      setCookie("ff_refresh", res.tokens.refresh, 7 * 24 * 60 * 60);
      if (typeof window !== "undefined" && !localStorage.getItem("ff_refresh")) {
        localStorage.setItem("ff_refresh", res.tokens.refresh);
      }
    }
    if (res?.user) {
      if (typeof window !== "undefined" && !localStorage.getItem("ff_user")) {
        try {
          localStorage.setItem("ff_user", JSON.stringify(res.user));
        } catch (e) {
          console.warn("Failed to store user in localStorage", e);
        }
      }
    }
    if (res?.user?.role) {
      setCookie("ff_role", res.user.role, 7 * 24 * 60 * 60);
    }
  } catch (e) {
    console.warn("Failed to set auth cookies", e);
  }
  return res;
}

export function requestSignupCode(payload) {
  return apiPost("/api/register/code/", payload);
}

export function verify2FA(payload) {
  return apiPost("/api/auth/2fa/verify/", payload);
}

export function requestPasswordReset(payload) {
  return apiPost("/api/auth/password-reset/request/", payload);
}

export function confirmPasswordReset(payload) {
  return apiPost("/api/auth/password-reset/confirm/", payload);
}
