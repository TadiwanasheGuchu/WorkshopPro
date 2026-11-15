"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/page";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { TokenInfo } from "@/lib/api/types";

import { newPasswordForm, tokenFromHash, type NewPasswordValues } from "./password-fields";

type State =
  | { kind: "checking" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; token: string; info: TokenInfo };

/**
 * Shared by "accept invitation" and "reset password": validates the token from the URL
 * fragment, then lets the user choose a password.
 */
export function SetPasswordForm({ purpose }: { purpose: "invitation" | "password_reset" }) {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "checking" });
  const [error, setError] = useState<string | null>(null);
  const form = useForm<NewPasswordValues>({
    resolver: zodResolver(newPasswordForm),
    defaultValues: { password: "", confirm: "" },
  });

  useEffect(() => {
    const token = tokenFromHash();
    const check: Promise<State> = token
      ? api<TokenInfo>("POST", `/auth/tokens/inspect?purpose=${purpose}`, { token }).then(
          (info): State => ({ kind: "ready", token, info }),
          (e: unknown): State => ({ kind: "invalid", message: errorMessage(e) }),
        )
      : Promise.resolve({
          kind: "invalid",
          message: "This link is incomplete. Open it again from your email.",
        });
    void check.then(setState);
  }, [purpose]);

  async function onSubmit(values: NewPasswordValues) {
    if (state.kind !== "ready") return;
    setError(null);
    try {
      if (purpose === "invitation") {
        await api("POST", "/auth/invitations/accept", { token: state.token, password: values.password });
        router.push("/sign-in?notice=invitation-accepted");
      } else {
        await api("POST", "/auth/password-reset/confirm", {
          token: state.token,
          new_password: values.password,
        });
        router.push("/sign-in?notice=password-reset");
      }
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  if (state.kind === "checking") {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Checking link">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  if (state.kind === "invalid") {
    return (
      <div className="space-y-4">
        <Alert tone="error" title="This link cannot be used">
          {state.message}
        </Alert>
        <Link
          href={purpose === "invitation" ? "/sign-in" : "/forgot-password"}
          className="text-sm text-steel hover:underline"
        >
          {purpose === "invitation" ? "Go to sign in" : "Request a new reset link"}
        </Link>
      </div>
    );
  }

  const { errors, isSubmitting } = form.formState;
  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
      <p className="text-muted">
        {purpose === "invitation" ? (
          <>
            Welcome, {state.info.full_name}. Choose a password for{" "}
            <span className="font-medium text-slate-deep">{state.info.email}</span> to join{" "}
            {state.info.organisation_name}.
          </>
        ) : (
          <>
            Choose a new password for <span className="font-medium text-slate-deep">{state.info.email}</span>.
            You will be signed out on all devices.
          </>
        )}
      </p>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {/* Lets password managers associate the new password with the account. */}
      <input type="email" autoComplete="username" value={state.info.email} readOnly hidden />
      <Field label="New password" hint="At least 10 characters." error={errors.password?.message}>
        {(p) => <Input {...p} type="password" autoComplete="new-password" autoFocus {...form.register("password")} />}
      </Field>
      <Field label="Repeat password" error={errors.confirm?.message}>
        {(p) => <Input {...p} type="password" autoComplete="new-password" {...form.register("confirm")} />}
      </Field>
      <Button type="submit" variant="primary" className="w-full" loading={isSubmitting}>
        {purpose === "invitation" ? "Activate account" : "Change password"}
      </Button>
    </form>
  );
}
