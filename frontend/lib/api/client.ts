"use client";

import { ApiError, toApiError } from "./errors";

const CSRF_COOKIE = "wp_csrf";

function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function csrfToken(): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return existing;
  const res = await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
  if (!res.ok) throw await toApiError(res);
  return ((await res.json()) as { csrf_token: string }).csrf_token;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

/**
 * Call the API from the browser. Requests go to the same origin (/api/v1/...), which
 * the Next.js proxy forwards to the backend. Unsafe methods carry the CSRF header.
 * Payments pass an idempotency key so a retried or double-submitted request is recorded once.
 */
export async function api<T = void>(method: Method, path: string, body?: unknown, options?: { idempotencyKey?: string }): Promise<T> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (body !== undefined) headers["content-type"] = "application/json";
  if (method !== "GET") headers["x-csrf-token"] = await csrfToken();
  if (options?.idempotencyKey) headers["idempotency-key"] = options.idempotencyKey;

  const res = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  if (!res.ok) {
    const error = await toApiError(res);
    if (error.status === 401 && !path.startsWith("/auth/")) {
      // Full page load on session expiry: discards all client-side state from the old session.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign(`/sign-in?next=${encodeURIComponent(window.location.pathname)}`);
    }
    throw error;
  }
  if (res.status === 204 || res.status === 202) return undefined as T;
  return (await res.json()) as T;
}

export { ApiError };

/** Multipart upload (photos). Same origin, CSRF header, JSON response. */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method: "POST",
    headers: { accept: "application/json", "x-csrf-token": await csrfToken() },
    body: form,
    credentials: "same-origin",
  });
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

/** POST that returns a file (e.g. the customer's quotation PDF) and saves it. */
export async function downloadFile(path: string, body: unknown, filename: string): Promise<void> {
  const res = await fetch(`/api/v1${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-csrf-token": await csrfToken() },
    body: JSON.stringify(body),
    credentials: "same-origin",
  });
  if (!res.ok) throw await toApiError(res);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
