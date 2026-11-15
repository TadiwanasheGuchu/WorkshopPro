"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { RoleAssignmentsEditor } from "@/components/app/role-assignments-editor";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import type { BranchSummary, Role, User } from "@/lib/api/types";
import { applyApiError, nullIfBlank } from "@/lib/forms";

const schema = z.object({
  full_name: z.string().trim().min(1, "Enter the person's name.").max(200),
  email: z.email("Enter a valid email address."),
  phone: z.string().max(50),
  role_assignments: z
    .array(z.object({ role_id: z.string(), branch_id: z.string().nullable() }))
    .min(1, "Assign at least one role."),
});
type Values = z.infer<typeof schema>;

export function InviteForm({ roles, branches }: { roles: Role[]; branches: BranchSummary[] }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const defaultRole = roles.find((r) => r.template_key === "mechanic") ?? roles.find((r) => !r.is_owner);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: "",
      email: "",
      phone: "",
      role_assignments: defaultRole ? [{ role_id: defaultRole.id, branch_id: branches[0]?.id ?? null }] : [],
    },
  });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(values: Values) {
    setError(null);
    try {
      const user = await api<User>("POST", "/users", { ...nullIfBlank(values), role_assignments: values.role_assignments });
      router.push(`/users/${user.id}?invited=1`);
    } catch (e) {
      setError(applyApiError(form, e));
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="max-w-2xl space-y-5">
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name" required error={errors.full_name?.message}>
          {(p) => <Input {...p} autoComplete="off" {...form.register("full_name")} />}
        </Field>
        <Field label="Email" required error={errors.email?.message} hint="The invitation is sent here.">
          {(p) => <Input {...p} type="email" autoComplete="off" {...form.register("email")} />}
        </Field>
        <Field label="Phone" error={errors.phone?.message}>
          {(p) => <Input {...p} type="tel" autoComplete="off" {...form.register("phone")} />}
        </Field>
      </div>
      <fieldset>
        <legend className="mb-1 text-sm font-medium">Roles</legend>
        <p className="mb-2 text-xs text-muted">
          Choose a branch to limit the role to that branch, or All branches.
        </p>
        <Controller
          control={form.control}
          name="role_assignments"
          render={({ field }) => (
            <RoleAssignmentsEditor value={field.value} onChange={field.onChange} roles={roles} branches={branches} />
          )}
        />
        {errors.role_assignments?.message ? (
          <p className="mt-1 text-xs font-medium text-status-danger">{errors.role_assignments.message}</p>
        ) : null}
      </fieldset>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" loading={isSubmitting}>
          Send invitation
        </Button>
        <Button onClick={() => router.back()}>Cancel</Button>
      </div>
    </form>
  );
}
