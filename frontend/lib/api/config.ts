import "server-only";

/**
 * Base URL the Next.js server uses to reach the API.
 * In Docker Compose this is the internal service address (http://backend:8000);
 * read at request time so one image works in every environment.
 */
export function apiBaseUrl(): string {
  return (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");
}
