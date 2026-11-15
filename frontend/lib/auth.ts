import "server-only";

import { cache } from "react";

import { apiGet } from "./api/server";
import type { Me } from "./api/types";

/**
 * The signed-in user, fetched once per request. Redirects to /sign-in when the
 * session is missing or expired. Not cached across requests, so revoked sessions
 * and permission changes apply immediately.
 */
export const requireMe = cache(async (): Promise<Me> => apiGet<Me>("/auth/me"));
