"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Select } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { InspectionDetail, InspectionKind, InspectionSummary, InspectionTemplate } from "@/lib/api/types";
import { KIND_LABEL } from "@/lib/inspection";

export function StartInspectionButton({ jobId, hasIntake }: { jobId: string; hasIntake: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [templates, setTemplates] = useState<InspectionTemplate[] | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [kind, setKind] = useState<InspectionKind>(hasIntake ? "quality" : "intake");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openDialog() {
    setOpen(true);
    setError(null);
    if (templates) return;
    try {
      const list = await api<InspectionTemplate[]>("GET", "/inspection-templates");
      setTemplates(list);
      setTemplateId((list.find((t) => t.is_default) ?? list[0])?.id ?? "");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const inspection = await api<InspectionDetail>("POST", `/job-cards/${jobId}/inspections`, { template_id: templateId, kind });
      router.push(`/inspections/${inspection.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" variant="primary" onClick={() => void openDialog()}>
        Start inspection
      </Button>
      <Dialog open={open} onOpenChange={setOpen} title="Start inspection">
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Type">
            {(p) => (
              <Select {...p} value={kind} onChange={(e) => setKind(e.target.value as InspectionKind)}>
                {(Object.keys(KIND_LABEL) as InspectionKind[]).map((k) => (
                  <option key={k} value={k}>
                    {KIND_LABEL[k]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Checklist">
            {(p) => (
              <Select {...p} value={templateId} onChange={(e) => setTemplateId(e.target.value)} disabled={!templates}>
                {(templates ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.item_count} items)
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={busy} disabled={!templateId} onClick={() => void start()}>
              Start
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}

export function InspectionList({ inspections }: { inspections: InspectionSummary[] }) {
  if (!inspections.length) return <p className="px-4 py-3 text-sm text-muted">No inspections yet.</p>;
  return (
    <ul className="divide-y divide-border">
      {inspections.map((i) => (
        <li key={i.id}>
          <Link href={`/inspections/${i.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-mist">
            <div>
              <p className="font-medium text-steel">{KIND_LABEL[i.kind]}</p>
              <p className="text-xs text-muted">{i.template_name}</p>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-1.5">
              {i.counts.fail ? <StatusBadge tone="danger">{i.counts.fail} failed</StatusBadge> : null}
              {i.counts.attention ? <StatusBadge tone="waiting">{i.counts.attention} attention</StatusBadge> : null}
              <StatusBadge tone={i.status === "submitted" ? "success" : "neutral"}>{i.status === "submitted" ? "Submitted" : "Draft"}</StatusBadge>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
