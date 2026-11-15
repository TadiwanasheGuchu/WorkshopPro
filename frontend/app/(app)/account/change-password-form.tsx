"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { passwordSchema } from "@/components/auth/password-fields";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { applyApiError } from "@/lib/forms";

const schema = z
  .object({ current_password: z.string().min(1, "Enter your current password."), new_password: passwordSchema, confirm: z.string() })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords do not match." });
type Values = z.infer<typeof schema>;

export function ChangePasswordForm({ email }: { email: string }) {
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { current_password: "", new_password: "", confirm: "" },
  });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(values: Values) {
    setMessage(null);
    try {
      await api("POST", "/auth/password", { current_password: values.current_password, new_password: values.new_password });
      form.reset();
      setMessage({ tone: "success", text: "Password changed. Other devices have been signed out." });
    } catch (e) {
      const text = applyApiError(form, e);
      if (text) setMessage({ tone: "error", text });
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="max-w-sm space-y-4">
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <input type="email" autoComplete="username" value={email} readOnly hidden />
      <Field label="Current password" error={errors.current_password?.message}>
        {(p) => <Input {...p} type="password" autoComplete="current-password" {...form.register("current_password")} />}
      </Field>
      <Field label="New password" hint="At least 10 characters." error={errors.new_password?.message}>
        {(p) => <Input {...p} type="password" autoComplete="new-password" {...form.register("new_password")} />}
      </Field>
      <Field label="Repeat new password" error={errors.confirm?.message}>
        {(p) => <Input {...p} type="password" autoComplete="new-password" {...form.register("confirm")} />}
      </Field>
      <Button type="submit" variant="primary" loading={isSubmitting}>
        Change password
      </Button>
    </form>
  );
}
