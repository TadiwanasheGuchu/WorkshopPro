"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { RoleAssignmentsEditor, type AssignmentDraft } from "@/components/app/role-assignments-editor";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { BranchSummary, Role, User } from "@/lib/api/types";
import { applyApiError, nullIfBlank } from "@/lib/forms";

const profileSchema = z.object({
  full_name: z.string().trim().min(1, "Enter a name.").max(200),
  email: z.email("Enter a valid email address."),
  phone: z.string().max(50),
});
type ProfileValues = z.infer<typeof profileSchema>;

export function ProfileForm({ user }: { user: User }) {
  const router = useRouter();
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: { full_name: user.full_name, email: user.email, phone: user.phone ?? "" },
  });
  const { errors, isSubmitting, isDirty } = form.formState;

  async function onSubmit(values: ProfileValues) {
    setMessage(null);
    try {
      const updated = await api<User>("PATCH", `/users/${user.id}`, nullIfBlank(values));
      form.reset({ full_name: updated.full_name, email: updated.email, phone: updated.phone ?? "" });
      setMessage({ tone: "success", text: "Details saved." });
      router.refresh();
    } catch (e) {
      const text = applyApiError(form, e);
      if (text) setMessage({ tone: "error", text });
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name" error={errors.full_name?.message}>
          {(p) => <Input {...p} {...form.register("full_name")} />}
        </Field>
        <Field
          label="Email"
          error={errors.email?.message}
          hint={user.status === "invited" ? "Changing this cancels the current invitation link." : undefined}
        >
          {(p) => <Input {...p} type="email" {...form.register("email")} />}
        </Field>
        <Field label="Phone" error={errors.phone?.message}>
          {(p) => <Input {...p} type="tel" {...form.register("phone")} />}
        </Field>
      </div>
      <Button type="submit" variant="primary" loading={isSubmitting} disabled={!isDirty}>
        Save details
      </Button>
    </form>
  );
}

export function RolesForm({
  user,
  roles,
  branches,
}: {
  user: User;
  roles: Role[];
  branches: BranchSummary[];
}) {
  const router = useRouter();
  const initial: AssignmentDraft[] = user.role_assignments.map((a) => ({ role_id: a.role_id, branch_id: a.branch_id }));
  const [value, setValue] = useState<AssignmentDraft[]>(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const dirty = JSON.stringify(value) !== JSON.stringify(initial);

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      await api("PUT", `/users/${user.id}/role-assignments`, { role_assignments: value });
      setMessage({ tone: "success", text: "Roles saved. Changes apply on the user's next action." });
      router.refresh();
    } catch (e) {
      setMessage({ tone: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <RoleAssignmentsEditor value={value} onChange={setValue} roles={roles} branches={branches} />
      <Button variant="primary" onClick={() => void save()} loading={busy} disabled={!dirty}>
        Save roles
      </Button>
    </div>
  );
}

export function StatusActions({ user, isSelf }: { user: User; isSelf: boolean }) {
  const router = useRouter();
  const [notice, setNotice] = useState<string | null>(null);

  async function post(path: string) {
    await api("POST", `/users/${user.id}/${path}`);
    router.refresh();
  }

  return (
    <div className="space-y-3">
      {notice ? <Alert tone="success">{notice}</Alert> : null}
      <div className="flex flex-wrap gap-2">
        {user.status === "invited" ? (
          <ConfirmButton
            trigger={<Button>Resend invitation</Button>}
            title="Resend invitation?"
            description={`A new link is emailed to ${user.email}. The previous link stops working.`}
            confirmLabel="Resend"
            onConfirm={async () => {
              await post("resend-invitation");
              setNotice(`Invitation sent to ${user.email}.`);
            }}
          />
        ) : null}
        {user.status !== "deactivated" && !isSelf ? (
          <ConfirmButton
            trigger={<Button variant="danger">Deactivate user</Button>}
            title={`Deactivate ${user.full_name}?`}
            description="They are signed out on all devices and cannot sign in. Their history is kept and you can reactivate them later."
            confirmLabel="Deactivate"
            destructive
            onConfirm={() => post("deactivate")}
          />
        ) : null}
        {user.status === "deactivated" ? (
          <ConfirmButton
            trigger={<Button>Reactivate user</Button>}
            title={`Reactivate ${user.full_name}?`}
            description="They will be able to sign in again with their existing password and roles."
            confirmLabel="Reactivate"
            onConfirm={() => post("activate")}
          />
        ) : null}
      </div>
    </div>
  );
}
