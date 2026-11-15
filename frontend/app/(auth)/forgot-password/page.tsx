"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";

const schema = z.object({ email: z.email("Enter a valid email address.") });
type Values = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "" } });

  async function onSubmit(values: Values) {
    setError(null);
    try {
      await api("POST", "/auth/password-reset/request", values);
      setSent(true);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <>
      <h1 className="mb-1 text-lg font-semibold">Reset your password</h1>
      {sent ? (
        <div className="space-y-4">
          <Alert tone="success" title="Check your email">
            If an account exists for that address, we have sent a link to reset the password. The
            link expires in one hour.
          </Alert>
          <Link href="/sign-in" className="text-sm text-steel hover:underline">
            Back to sign in
          </Link>
        </div>
      ) : (
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="mt-4 space-y-4">
          <p className="text-muted">Enter your email and we will send you a link to choose a new password.</p>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Email" error={form.formState.errors.email?.message}>
            {(p) => <Input {...p} type="email" autoComplete="username" autoFocus {...form.register("email")} />}
          </Field>
          <Button type="submit" variant="primary" className="w-full" loading={form.formState.isSubmitting}>
            Send reset link
          </Button>
          <Link href="/sign-in" className="block text-sm text-steel hover:underline">
            Back to sign in
          </Link>
        </form>
      )}
    </>
  );
}
