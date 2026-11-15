import { z } from "zod";

/** Mirrors backend password rules (app/core/security.py). */
export const passwordSchema = z
  .string()
  .min(10, "Use at least 10 characters.")
  .max(128, "Use at most 128 characters.")
  .refine((v) => v.trim().length > 0, "Password cannot be only spaces.");

export const newPasswordForm = z
  .object({ password: passwordSchema, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });

export type NewPasswordValues = z.infer<typeof newPasswordForm>;

/** Read `token` from the URL fragment (#token=...). Fragments never reach the server. */
export function tokenFromHash(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.hash.slice(1)).get("token");
}
