import type { ApiErrorBody } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(status: number, body: Partial<ApiErrorBody>) {
    super(body.message ?? "Something went wrong.");
    this.status = status;
    this.code = body.code ?? "error";
    this.details = body.details;
    this.requestId = body.request_id ?? null;
  }

  /** Field-level messages from a 422 validation error, keyed by field name. */
  fieldErrors(): Record<string, string> {
    if (this.code !== "validation_error" || !Array.isArray(this.details)) return {};
    const result: Record<string, string> = {};
    for (const item of this.details as { loc?: unknown[]; msg?: string }[]) {
      const field = item.loc?.filter((p) => typeof p === "string" && p !== "body").at(-1);
      if (typeof field === "string" && item.msg) result[field] = item.msg.replace(/^Value error, /, "");
    }
    return result;
  }
}

export async function toApiError(res: Response): Promise<ApiError> {
  let body: Partial<ApiErrorBody> = {};
  try {
    const json: unknown = await res.json();
    if (json && typeof json === "object" && "error" in json) {
      body = (json as { error: ApiErrorBody }).error;
    }
  } catch {
    // Non-JSON error (e.g. proxy failure).
  }
  if (!body.message) {
    body.message =
      res.status >= 500
        ? "The server could not complete the request. Try again shortly."
        : `Request failed (${res.status}).`;
  }
  return new ApiError(res.status, body);
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) return "Could not reach the server. Check your connection.";
  return "Something went wrong.";
}
