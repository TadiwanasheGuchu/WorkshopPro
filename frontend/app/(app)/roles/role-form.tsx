"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton } from "@/components/ui/dialog";
import { Checkbox, Field, Input, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import type { Permission, Role } from "@/lib/api/types";
import { applyApiError } from "@/lib/forms";

const schema = z.object({
  name: z.string().trim().min(1, "Enter a role name.").max(100),
  description: z.string().max(300),
  permissions: z.array(z.string()),
});
type Values = z.infer<typeof schema>;

export function RoleForm({
  role,
  catalogue,
  grantable,
}: {
  role?: Role;
  catalogue: Permission[];
  /** Permissions the current user holds and may therefore grant. */
  grantable: string[];
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: role?.name ?? "",
      description: role?.description ?? "",
      permissions: role?.permissions ?? [],
    },
  });
  const { errors, isSubmitting } = form.formState;
  const selected = useWatch({ control: form.control, name: "permissions" });

  const modules = [...new Set(catalogue.map((p) => p.module))];

  function toggle(code: string, on: boolean) {
    const next = on ? [...selected, code] : selected.filter((c) => c !== code);
    form.setValue("permissions", next, { shouldDirty: true });
  }

  async function onSubmit(values: Values) {
    setError(null);
    const body = { ...values, description: values.description.trim() || null };
    try {
      if (role) {
        await api<Role>("PATCH", `/roles/${role.id}`, body);
        router.refresh();
        form.reset(values);
      } else {
        const created = await api<Role>("POST", "/roles", body);
        router.push(`/roles/${created.id}`);
      }
    } catch (e) {
      setError(applyApiError(form, e));
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-5">
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Role name" required error={errors.name?.message}>
          {(p) => <Input {...p} {...form.register("name")} />}
        </Field>
        <Field label="Description" error={errors.description?.message} className="sm:col-span-2">
          {(p) => <Textarea {...p} rows={2} {...form.register("description")} />}
        </Field>
      </div>

      <fieldset className="space-y-4">
        <legend className="text-sm font-medium">Permissions</legend>
        {modules.map((module) => (
          <div key={module} className="rounded-control border border-border">
            <p className="border-b border-border bg-mist px-3 py-2 text-xs font-semibold text-muted uppercase">
              {module}
            </p>
            <div className="space-y-3 p-3">
              {catalogue
                .filter((p) => p.module === module)
                .map((p) => {
                  const checked = selected.includes(p.code);
                  const locked = !grantable.includes(p.code) && !checked;
                  return (
                    <Checkbox
                      key={p.code}
                      label={p.label}
                      description={
                        locked ? `${p.description} You do not hold this permission, so you cannot grant it.` : p.description
                      }
                      checked={checked}
                      disabled={locked}
                      onChange={(e) => toggle(p.code, e.target.checked)}
                    />
                  );
                })}
            </div>
          </div>
        ))}
      </fieldset>

      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" loading={isSubmitting} disabled={role && !form.formState.isDirty}>
          {role ? "Save role" : "Create role"}
        </Button>
        {role && !role.template_key && role.user_count === 0 && !role.archived_at ? (
          <ConfirmButton
            trigger={<Button variant="danger">Archive role</Button>}
            title={`Archive ${role.name}?`}
            description="Archived roles cannot be assigned. You can restore it later."
            confirmLabel="Archive"
            destructive
            onConfirm={async () => {
              await api("POST", `/roles/${role.id}/archive`);
              router.push("/roles");
            }}
          />
        ) : null}
      </div>
    </form>
  );
}
