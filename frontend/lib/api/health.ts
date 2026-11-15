import "server-only";

import { z } from "zod";

import { apiBaseUrl } from "./config";

const dependencyCheck = z.object({
  status: z.enum(["ok", "error"]),
  latency_ms: z.number().nullable().optional(),
  detail: z.string().nullable().optional(),
});

const readinessSchema = z.object({
  status: z.enum(["ok", "error"]),
  checks: z.record(z.string(), dependencyCheck),
});

export type Readiness = z.infer<typeof readinessSchema>;

export type ReadinessResult =
  | { reachable: true; readiness: Readiness }
  | { reachable: false; reason: string };

/** Fetch API readiness. Never throws: an unreachable API is a displayable state. */
export async function getReadiness(): Promise<ReadinessResult> {
  try {
    const res = await fetch(`${apiBaseUrl()}/api/v1/health/ready`, {
      signal: AbortSignal.timeout(5000),
    });
    // 503 still carries a valid body describing which dependency failed.
    const parsed = readinessSchema.safeParse(await res.json());
    if (!parsed.success) {
      return { reachable: false, reason: `Unexpected response (HTTP ${res.status})` };
    }
    return { reachable: true, readiness: parsed.data };
  } catch {
    return { reachable: false, reason: "API did not respond" };
  }
}
