import "server-only";

import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { apiBaseUrl } from "./config";
import { toApiError } from "./errors";

/**
 * GET from the API on behalf of the signed-in user (Server Components only).
 * Forwards the browser's cookies. Redirects to sign-in on 401 and renders the
 * not-found page on 404; other errors throw to the nearest error boundary.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const cookieHeader = (await cookies()).toString();
  const res = await fetch(`${apiBaseUrl()}/api/v1${path}`, {
    headers: { cookie: cookieHeader, accept: "application/json" },
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  if (res.status === 401) redirect("/sign-in");
  if (res.status === 404) notFound();
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

/** Build a query string from defined values only. */
export function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}
