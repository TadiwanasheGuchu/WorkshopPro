"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";

const schema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type Values = z.infer<typeof schema>;

/** Only allow same-site relative paths, to prevent open redirects. */
function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export function SignInForm({ next, notice }: { next: string | null; notice: string | null }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(values: Values) {
    setError(null);
    try {
      await api("POST", "/auth/login", values);
      router.replace(safeNext(next));
      router.refresh();
    } catch (e) {
      setError(errorMessage(e));
      form.setValue("password", "");
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
      {notice ? <Alert tone="success">{notice}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Field label="Email" error={errors.email?.message}>
        {(p) => <Input {...p} type="email" autoComplete="username" autoFocus {...form.register("email")} />}
      </Field>
      <Field label="Password" error={errors.password?.message}>
        {(p) => <Input {...p} type="password" autoComplete="current-password" {...form.register("password")} />}
      </Field>
      <Button type="submit" variant="primary" className="w-full" loading={isSubmitting}>
        Sign in
      </Button>
      <p className="text-sm">
        <Link href="/forgot-password" className="text-steel hover:underline">
          Forgot your password?
        </Link>
      </p>
    </form>
  );
}
