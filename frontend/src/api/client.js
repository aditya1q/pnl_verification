// API access with login tokens.
// - Access token: kept only in memory (not localStorage), sent as "Authorization: Bearer".
// - Refresh token: httpOnly cookie set by the backend; scripts never see it.
// A request that gets 401 refreshes the access token once and is retried.

let accessToken = null;
let refreshing = null;
const sessionEndedListeners = new Set();

export function setAccessToken(token) {
  accessToken = token || null;
}

// Called when the session can no longer be renewed (refresh token expired or revoked).
export function onSessionEnded(listener) {
  sessionEndedListeners.add(listener);
  return () => sessionEndedListeners.delete(listener);
}

async function readJson(response) {
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!response.ok) {
    const detail = Array.isArray(data?.detail) ? data.detail.map((d) => d.msg).join("; ") : data?.detail;
    const error = new Error(detail || `Request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return data;
}

// New access token from the refresh cookie. Concurrent callers share one request.
export function refreshSession() {
  if (!refreshing) {
    refreshing = fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" })
      .then(readJson)
      .then((data) => { setAccessToken(data.access_token); return data; })
      .catch((err) => { setAccessToken(null); throw err; })
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

// Fetch JSON from the backend; throws an Error with the API's detail message on failure.
export async function requestJson(url, options = {}, retry = true) {
  const headers = new Headers(options.headers || {});
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  if (response.status === 401 && retry && !url.startsWith("/api/auth/")) {
    try {
      await refreshSession();
    } catch {
      sessionEndedListeners.forEach((listener) => listener());
      throw new Error("Your session has ended. Sign in again.");
    }
    return requestJson(url, options, false);
  }
  return readJson(response);
}

// POST one file as multipart form data.
export function uploadFile(url, file) {
  const body = new FormData();
  body.append("file", file);
  return requestJson(url, { method: "POST", body });
}

export function postJson(url, body, method = "POST") {
  return requestJson(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
