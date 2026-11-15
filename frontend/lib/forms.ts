"use client";

import type { FieldValues, Path, UseFormReturn } from "react-hook-form";

import { ApiError, errorMessage } from "./api/errors";

/**
 * Put a failed API call's field errors onto the form, and return the message to show
 * at the top of the form (null when every error was attached to a field).
 */
export function applyApiError<T extends FieldValues>(form: UseFormReturn<T>, error: unknown): string | null {
  if (error instanceof ApiError) {
    const fields = error.fieldErrors();
    const known = Object.keys(form.getValues());
    let unmatched = false;
    for (const [field, message] of Object.entries(fields)) {
      if (known.includes(field)) form.setError(field as Path<T>, { message });
      else unmatched = true;
    }
    if (Object.keys(fields).length && !unmatched) return null;
  }
  return errorMessage(error);
}

/** Convert empty strings to null for optional API fields. */
export function nullIfBlank<T extends Record<string, unknown>>(values: T): T {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(values)) out[k] = typeof v === "string" && v.trim() === "" ? null : v;
  return out as T;
}
