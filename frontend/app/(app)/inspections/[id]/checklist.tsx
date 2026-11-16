"use client";

import { Camera, ChevronDown, Trash2 } from "lucide-react";
import Link from "next/link";

import { PdfLink } from "@/components/app/pdf-link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { ApiError, api, apiUpload } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { InspectionDetail, InspectionItem, InspectionPhoto, InspectionResult } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { RESULT_LABEL, RESULT_SHORT, RESULT_TONE, compressPhoto } from "@/lib/inspection";

const RESULTS: InspectionResult[] = ["pass", "attention", "fail", "not_inspected"];

const SELECTED: Record<InspectionResult, string> = {
  pass: "border-status-success bg-status-success-tint",
  attention: "border-status-waiting bg-status-waiting-tint",
  fail: "border-status-danger bg-status-danger-tint",
  not_inspected: "border-status-neutral bg-status-neutral-tint",
};

function Thumb({ photo, onDelete }: { photo: InspectionPhoto; onDelete?: () => void }) {
  return (
    <div className="relative">
      <a href={`/api/v1/files/${photo.file_id}`} target="_blank" rel="noreferrer">
        {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image, not optimisable */}
        <img
          src={`/api/v1/files/${photo.file_id}?variant=thumb`}
          alt={photo.caption ?? "Inspection photo"}
          className="size-20 rounded-control border border-border object-cover"
          loading="lazy"
        />
      </a>
      {onDelete ? (
        <button
          type="button"
          onClick={onDelete}
          aria-label="Remove photo"
          className="absolute -top-2 -right-2 flex size-7 items-center justify-center rounded-full border border-border bg-surface"
        >
          <Trash2 className="size-3.5" aria-hidden />
        </button>
      ) : null}
    </div>
  );
}

function ItemRow({
  inspectionId,
  item,
  editable,
  onChange,
}: {
  inspectionId: string;
  item: InspectionItem;
  editable: boolean;
  onChange: (item: InspectionItem) => void;
}) {
  const [notes, setNotes] = useState(item.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const needsDetail = item.result === "attention" || item.result === "fail";
  const showNotes = needsDetail || Boolean(item.notes);

  async function save(patch: { result?: InspectionResult; notes?: string | null }) {
    const previous = item;
    onChange({ ...item, ...patch, notes: patch.notes !== undefined ? patch.notes : item.notes });
    setSaving(true);
    setError(null);
    try {
      onChange(await api<InspectionItem>("PATCH", `/inspections/${inspectionId}/items/${item.id}`, patch));
    } catch (e) {
      onChange(previous);
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", await compressPhoto(file), file.name.replace(/\.\w+$/, ".jpg"));
      form.append("item_id", item.id);
      const photo = await apiUpload<InspectionPhoto>(`/inspections/${inspectionId}/photos`, form);
      onChange({ ...item, photos: [...item.photos, photo] });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function removePhoto(photo: InspectionPhoto) {
    try {
      await api("DELETE", `/inspections/${inspectionId}/photos/${photo.id}`);
      onChange({ ...item, photos: item.photos.filter((p) => p.id !== photo.id) });
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <li className="space-y-2 px-4 py-3" aria-busy={saving || undefined}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium">{item.label}</p>
          {item.guidance ? <p className="text-xs text-muted">{item.guidance}</p> : null}
        </div>
        {!editable ? <StatusBadge tone={RESULT_TONE[item.result]}>{RESULT_LABEL[item.result]}</StatusBadge> : null}
      </div>

      {editable ? (
        <div role="radiogroup" aria-label={`Result for ${item.label}`} className="grid grid-cols-4 gap-1.5">
          {RESULTS.map((r) => (
            <button
              key={r}
              type="button"
              role="radio"
              aria-checked={item.result === r}
              onClick={() => item.result !== r && void save({ result: r })}
              className={cn(
                "h-11 rounded-control border text-sm",
                item.result === r ? `${SELECTED[r]} font-semibold` : "border-border bg-surface hover:bg-mist",
              )}
            >
              {RESULT_SHORT[r]}
            </button>
          ))}
        </div>
      ) : null}

      {editable && showNotes ? (
        <div>
          <label htmlFor={`notes-${item.id}`} className="sr-only">
            Notes for {item.label}
          </label>
          <Textarea
            id={`notes-${item.id}`}
            rows={2}
            value={notes}
            placeholder={needsDetail ? "What did you find? (note or photo required)" : "Notes"}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={() => notes !== (item.notes ?? "") && void save({ notes: notes.trim() || null })}
          />
        </div>
      ) : null}
      {!editable && item.notes ? <p className="text-sm whitespace-pre-line">{item.notes}</p> : null}

      {item.photos.length || (editable && (showNotes || item.result !== "not_inspected")) ? (
        <div className="flex flex-wrap items-center gap-3">
          {item.photos.map((p) => (
            <Thumb key={p.id} photo={p} onDelete={editable ? () => void removePhoto(p) : undefined} />
          ))}
          {editable ? (
            <>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="sr-only"
                id={`photo-${item.id}`}
                onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])}
              />
              <label
                htmlFor={`photo-${item.id}`}
                className="flex h-11 cursor-pointer items-center gap-2 rounded-control border border-border bg-surface px-3 text-sm hover:bg-mist"
              >
                <Camera className="size-4" aria-hidden /> {uploading ? "Uploading…" : "Photo"}
              </label>
            </>
          ) : null}
        </div>
      ) : null}
      {error ? <p role="alert" className="text-xs font-medium text-status-danger">{error}</p> : null}
    </li>
  );
}

export function Checklist({ inspection }: { inspection: InspectionDetail }) {
  const router = useRouter();
  const [items, setItems] = useState(inspection.items);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; items?: string[] } | null>(null);
  const [odometer, setOdometer] = useState(inspection.odometer_km != null ? String(inspection.odometer_km) : "");
  const [summary, setSummary] = useState(inspection.summary ?? "");
  const editable = inspection.capabilities.edit;

  const sections = [...new Set(items.map((i) => i.section))];
  const done = items.filter((i) => i.result !== "not_inspected").length;

  function update(next: InspectionItem) {
    setItems((prev) => prev.map((i) => (i.id === next.id ? next : i)));
  }

  async function saveHeader() {
    try {
      await api("PATCH", `/inspections/${inspection.id}`, {
        odometer_km: odometer ? Number(odometer.replace(/\s/g, "")) : null,
        summary: summary.trim() || null,
      });
    } catch (e) {
      setError({ message: errorMessage(e) });
    }
  }

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await saveHeader();
      await api("POST", `/inspections/${inspection.id}/submit`);
      router.refresh();
    } catch (e) {
      const details = e instanceof ApiError ? (e.details as { items?: string[] } | null) : null;
      setError({ message: errorMessage(e), items: details?.items });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      {editable ? (
        <div className="sticky top-14 z-20 -mx-4 border-b border-border bg-mist px-4 py-2 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:p-0">
          <div className="flex items-center justify-between text-sm">
            <span>
              <span className="font-semibold tabular-nums">{done}</span> of {items.length} checked
            </span>
            <span className="text-xs text-muted">Saved as you go</span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-border" aria-hidden>
            <div className="h-1.5 rounded-full bg-steel" style={{ width: `${(done / Math.max(items.length, 1)) * 100}%` }} />
          </div>
        </div>
      ) : null}

      {sections.map((section) => {
        const sectionItems = items.filter((i) => i.section === section);
        const flagged = sectionItems.filter((i) => i.result === "fail" || i.result === "attention").length;
        const checked = sectionItems.filter((i) => i.result !== "not_inspected").length;
        return (
          <details key={section} open className="group rounded-panel border border-border bg-surface">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3">
              <span className="font-semibold">{section}</span>
              <span className="flex items-center gap-2 text-xs text-muted">
                {flagged ? <StatusBadge tone="waiting">{flagged} flagged</StatusBadge> : null}
                <span className="tabular-nums">
                  {checked}/{sectionItems.length}
                </span>
                <ChevronDown className="size-4 transition-transform group-open:rotate-180" aria-hidden />
              </span>
            </summary>
            <ul className="divide-y divide-border border-t border-border">
              {sectionItems.map((item) => (
                <ItemRow key={item.id} inspectionId={inspection.id} item={item} editable={editable} onChange={update} />
              ))}
            </ul>
          </details>
        );
      })}

      {editable ? (
        <section className="space-y-4 rounded-panel border border-border bg-surface p-4">
          <Field label="Odometer (km)">
            {(p) => <Input {...p} inputMode="numeric" value={odometer} onChange={(e) => setOdometer(e.target.value)} onBlur={() => void saveHeader()} className="font-mono sm:max-w-xs" />}
          </Field>
          <Field label="Summary for the customer" hint="Main findings in plain language.">
            {(p) => <Textarea {...p} rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} onBlur={() => void saveHeader()} />}
          </Field>
          {error ? (
            <Alert tone="error" title={error.message}>
              {error.items?.length ? (
                <ul className="mt-1 list-disc pl-5">
                  {error.items.map((label) => (
                    <li key={label}>{label}</li>
                  ))}
                </ul>
              ) : null}
            </Alert>
          ) : null}
          <Button variant="primary" className="w-full sm:w-auto" loading={submitting} onClick={() => void submit()}>
            Submit inspection
          </Button>
          <p className="text-xs text-muted">After submitting, the inspection is locked. Corrections are recorded as amendments.</p>
        </section>
      ) : (
        <>
          {inspection.summary ? (
            <section className="rounded-panel border border-border bg-surface p-4">
              <h2 className="text-sm font-semibold">Summary</h2>
              <p className="mt-1 whitespace-pre-line">{inspection.summary}</p>
            </section>
          ) : null}
          {inspection.capabilities.amend ? <AmendButton inspection={inspection} /> : null}
          <div className="flex flex-wrap items-center gap-3">
            <PdfLink href={`/inspections/${inspection.id}/pdf`} label="Customer report (PDF)" />
            <Link href={`/inspections/${inspection.id}/print`} className="text-sm text-steel hover:underline">
              Print view
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

function AmendButton({ inspection }: { inspection: InspectionDetail }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [itemId, setItemId] = useState(inspection.items[0]?.id ?? "");
  const item = inspection.items.find((i) => i.id === itemId);
  const [result, setResult] = useState<InspectionResult>(item?.result ?? "pass");
  const [notes, setNotes] = useState(item?.notes ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function choose(id: string) {
    const next = inspection.items.find((i) => i.id === id);
    setItemId(id);
    setResult(next?.result ?? "pass");
    setNotes(next?.notes ?? "");
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>Amend submitted inspection</Button>
      <Dialog open={open} onOpenChange={setOpen} title="Amend inspection" description="The original result and your reason are kept in the record.">
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Item">
            {(p) => (
              <Select {...p} value={itemId} onChange={(e) => choose(e.target.value)}>
                {inspection.items.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.section} – {i.label} ({RESULT_SHORT[i.result]})
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Corrected result">
            {(p) => (
              <Select {...p} value={result} onChange={(e) => setResult(e.target.value as InspectionResult)}>
                {RESULTS.map((r) => (
                  <option key={r} value={r}>
                    {RESULT_LABEL[r]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Notes">{(p) => <Textarea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
          <Field label="Reason for the correction" required>
            {(p) => <Input {...p} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={reason.trim().length < 3}
              onClick={async () => {
                setBusy(true);
                setError(null);
                try {
                  await api("POST", `/inspections/${inspection.id}/amendments`, {
                    item_id: itemId,
                    result,
                    notes: notes.trim() || null,
                    reason: reason.trim(),
                  });
                  setOpen(false);
                  setReason("");
                  router.refresh();
                } catch (e) {
                  setError(errorMessage(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Save amendment
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
