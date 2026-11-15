"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton } from "@/components/ui/dialog";
import { Checkbox, Field, Input, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { InspectionTemplate } from "@/lib/api/types";

/** "# Section" lines start a section; other lines are items, "Label | guidance". */
export function toText(t: InspectionTemplate | null): string {
  if (!t?.items) return "# Exterior and bodywork\nBody panels | Dents, scratches, rust\n\n# Tyres and wheels\nFront left tyre | Tread depth, damage, pressure\n";
  const lines: string[] = [];
  let section = "";
  for (const item of t.items) {
    if (item.section !== section) {
      if (lines.length) lines.push("");
      lines.push(`# ${item.section}`);
      section = item.section;
    }
    lines.push(item.guidance ? `${item.label} | ${item.guidance}` : item.label);
  }
  return lines.join("\n");
}

export function parse(text: string): { items: { section: string; label: string; guidance: string | null }[]; errors: string[] } {
  const items: { section: string; label: string; guidance: string | null }[] = [];
  const errors: string[] = [];
  let section = "";
  text.split("\n").forEach((raw, index) => {
    const line = raw.trim();
    if (!line) return;
    if (line.startsWith("#")) {
      section = line.replace(/^#+/, "").trim().slice(0, 100);
      return;
    }
    if (!section) {
      errors.push(`Line ${index + 1}: add a "# Section" heading before the first item.`);
      return;
    }
    const [label, ...rest] = line.split("|");
    const guidance = rest.join("|").trim();
    if (label.trim().length > 200) errors.push(`Line ${index + 1}: item is longer than 200 characters.`);
    items.push({ section, label: label.trim(), guidance: guidance ? guidance.slice(0, 500) : null });
  });
  if (!items.length) errors.push("Add at least one checklist item.");
  return { items, errors };
}

export function TemplateEditor({ template }: { template: InspectionTemplate | null }) {
  const router = useRouter();
  const [name, setName] = useState(template?.name ?? "");
  const [description, setDescription] = useState(template?.description ?? "");
  const [isDefault, setIsDefault] = useState(template?.is_default ?? false);
  const [text, setText] = useState(toText(template));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const parsed = parse(text);
  const sections = new Set(parsed.items.map((i) => i.section)).size;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body = { name: name.trim(), description: description.trim() || null, is_default: isDefault, items: parsed.items };
      const saved = template
        ? await api<InspectionTemplate>("PUT", `/inspection-templates/${template.id}`, body)
        : await api<InspectionTemplate>("POST", "/inspection-templates", body);
      router.push(`/settings/inspection-templates/${saved.id}?saved=1`);
      router.refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" required>
          {(p) => <Input {...p} value={name} maxLength={150} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Description">
          {(p) => <Input {...p} value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} />}
        </Field>
      </div>
      <Checkbox label="Default checklist" description="Pre-selected when starting an inspection." checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
      <Field
        label="Checklist"
        hint={`Start each section with "# Section name". One item per line; add guidance after "|". ${parsed.items.length} items in ${sections} sections.`}
        error={parsed.errors[0]}
      >
        {(p) => <Textarea {...p} rows={20} className="font-mono text-sm" value={text} onChange={(e) => setText(e.target.value)} />}
      </Field>
      <p className="text-xs text-muted">Inspections that have already started keep their own copy of the checklist.</p>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" loading={busy} disabled={!name.trim() || parsed.errors.length > 0} onClick={() => void save()}>
          {template ? "Save checklist" : "Create checklist"}
        </Button>
        {template && !template.archived_at ? (
          <ConfirmButton
            trigger={<Button variant="danger">Archive</Button>}
            title={`Archive ${template.name}?`}
            description="It can no longer be chosen for new inspections. Past inspections are not affected."
            confirmLabel="Archive"
            destructive
            onConfirm={async () => {
              await api("POST", `/inspection-templates/${template.id}/archive`);
              router.push("/settings/inspection-templates");
              router.refresh();
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
