// Development: talk to the API on port 8000. Production build: leave VITE_API_BASE_URL empty and the app calls
// "/api/..." on the same address it was loaded from (a reverse proxy forwards that to the backend: no CORS, one HTTPS URL).
const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
const API_BASE = (configured ?? (import.meta.env.DEV ? "http://localhost:8000" : "")).replace(/\/$/, "");
const TOKEN_KEY = "reel.access_token";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}

// The token lives in sessionStorage: it is cleared when the tab/browser is closed.
export const getToken = (): string | null => { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } };
export const setToken = (token: string | null) => {
  try { token ? sessionStorage.setItem(TOKEN_KEY, token) : sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ }
};

let onUnauthorized: (() => void) | null = null;
export const setUnauthorizedHandler = (handler: (() => void) | null) => { onUnauthorized = handler; };

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) message = String(body.detail[0].msg).replace(/^Value error, /, "");
    } catch { /* response may not contain JSON */ }
    // A 401 on a protected call means the session ended; the login endpoint's own 401 is shown inline.
    if (response.status === 401 && token && !path.startsWith("/api/auth/login")) onUnauthorized?.();
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const apiBaseUrl = API_BASE;
export const absoluteUrl = (path: string) => `${API_BASE}${path}`;

export type UploadHandle<T> = { promise: Promise<T>; abort: () => void };

/** Upload a file as a raw request body with progress reporting (fetch cannot report upload progress). */
export function uploadFile<T>(path: string, file: File, onProgress: (percent: number) => void): UploadHandle<T> {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<T>((resolve, reject) => {
    xhr.open("POST", `${API_BASE}${path}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)); };
    xhr.onload = () => {
      let body: any = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) { resolve(body as T); return; }
      if (xhr.status === 401 && token) onUnauthorized?.();
      const detail = body && typeof body.detail === "string" ? body.detail : `Upload failed (${xhr.status}).`;
      reject(new ApiError(detail, xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Network error: the upload could not reach the server.", 0));
    xhr.onabort = () => reject(new ApiError("Upload cancelled.", 0));
    xhr.send(file);
  });
  return { promise, abort: () => xhr.abort() };
}
