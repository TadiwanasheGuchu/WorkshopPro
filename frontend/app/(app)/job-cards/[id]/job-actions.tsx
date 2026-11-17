"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton, Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { ApiError, api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { AssignableUser, ExceptionType, JobCardDetail, JobStatus, Priority } from "@/lib/api/types";
import { EXCEPTION_TYPE_LABEL, PRIORITY_LABEL, TRANSITION_ACTION } from "@/lib/job-status";

/** Shared submit handling: refresh on success; explain stale versions. */
function useMutation() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await fn();
      router.refresh();
      return true;
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === "stale_version"
          ? "Someone else updated this job. The page has been refreshed; check the changes and try again."
          : errorMessage(e),
      );
      if (e instanceof ApiError && e.code === "stale_version") router.refresh();
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run, setError };
}

// --------------------------------------------------------------------------- status

/** The normal next step from each status: shown as the single primary (orange) action.
 *  Other allowed moves (rework, waiting for parts, cancel) stay secondary. */
const FORWARD: Partial<Record<JobStatus, JobStatus[]>> = {
  vehicle_received: ["inspection_pending", "diagnosis_in_progress"],
  inspection_pending: ["diagnosis_in_progress"],
  diagnosis_in_progress: ["awaiting_approval", "repair_in_progress"],
  awaiting_approval: ["repair_in_progress", "awaiting_parts"],
  awaiting_parts: ["repair_in_progress"],
  repair_in_progress: ["quality_inspection"],
  quality_inspection: ["ready_for_collection"],
  ready_for_collection: ["completed"],
};

export function StatusActions({ job }: { job: JobCardDetail }) {
  const [target, setTarget] = useState<JobStatus | null>(null);
  const [note, setNote] = useState("");
  const [collectedBy, setCollectedBy] = useState("");
  const [handover, setHandover] = useState("");
  const { busy, error, run, setError } = useMutation();
  const options = job.capabilities.transitions;
  if (!options.length) return null;

  const forward = FORWARD[job.status] ?? [];
  const primary =
    forward.map((to) => options.find((o) => o.allowed && o.to_status === to)).find((o) => o !== undefined) ?? null;

  function open(to: JobStatus) {
    setTarget(to);
    setNote("");
    setError(null);
  }

  async function submit() {
    if (!target) return;
    const ok = await run(() =>
      api("POST", `/job-cards/${job.id}/transitions`, {
        to_status: target,
        version: job.version,
        note: target === "cancelled" ? null : note.trim() || null,
        cancellation_reason: target === "cancelled" ? note.trim() || null : null,
        collected_by_name: target === "completed" ? collectedBy.trim() || null : null,
        handover_notes: target === "completed" ? handover.trim() || null : null,
      }),
    );
    if (ok) setTarget(null);
  }

  const blocked = options.filter((o) => !o.allowed);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {options
          .filter((o) => o.allowed)
          .map((o) => (
            <Button
              key={o.to_status}
              variant={o === primary ? "primary" : o.to_status === "cancelled" ? "danger" : "secondary"}
              onClick={() => open(o.to_status)}
            >
              {TRANSITION_ACTION[o.to_status]}
            </Button>
          ))}
        {blocked.map((o) => (
          <Button key={o.to_status} disabled aria-describedby={`blocked-${o.to_status}`}>
            {TRANSITION_ACTION[o.to_status]}
          </Button>
        ))}
      </div>
      {blocked.length ? (
        <p id={`blocked-${blocked[0].to_status}`} className="text-xs text-muted">
          {blocked[0].reason}
        </p>
      ) : null}

      <Dialog
        open={target !== null}
        onOpenChange={(o) => !o && setTarget(null)}
        title={target ? TRANSITION_ACTION[target] : ""}
        description={
          target === "completed"
            ? "Record who collected the vehicle. The job is then closed."
            : target === "cancelled"
              ? "The job is closed without completing the work. This cannot be undone."
              : `Job ${job.job_number} moves to the next stage.`
        }
      >
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          {target === "completed" ? (
            <>
              <Field label="Collected by" required>
                {(p) => <Input {...p} value={collectedBy} onChange={(e) => setCollectedBy(e.target.value)} placeholder={job.customer.name} />}
              </Field>
              <Field label="Handover notes" hint="e.g. Old parts returned, next service at 135 000 km.">
                {(p) => <Textarea {...p} rows={2} value={handover} onChange={(e) => setHandover(e.target.value)} />}
              </Field>
            </>
          ) : (
            <Field label={target === "cancelled" ? "Reason for cancelling" : "Note (optional)"} required={target === "cancelled"}>
              {(p) => <Textarea {...p} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />}
            </Field>
          )}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setTarget(null)}>Back</Button>
            <Button
              variant={target === "cancelled" ? "danger" : "primary"}
              loading={busy}
              disabled={(target === "completed" && !collectedBy.trim()) || (target === "cancelled" && !note.trim())}
              onClick={() => void submit()}
            >
              {target ? TRANSITION_ACTION[target] : ""}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

// --------------------------------------------------------------------------- work record

export function WorkRecord({ job }: { job: JobCardDetail }) {
  const [diagnosis, setDiagnosis] = useState(job.diagnosis ?? "");
  const [work, setWork] = useState(job.work_performed ?? "");
  const [saved, setSaved] = useState(false);
  const { busy, error, run } = useMutation();
  const dirty = diagnosis !== (job.diagnosis ?? "") || work !== (job.work_performed ?? "");

  if (!job.capabilities.edit_work) {
    return (
      <dl className="space-y-3 text-sm">
        <div>
          <dt className="text-xs text-muted">Diagnosis</dt>
          <dd className="whitespace-pre-line">{job.diagnosis ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Work performed</dt>
          <dd className="whitespace-pre-line">{job.work_performed ?? "—"}</dd>
        </div>
      </dl>
    );
  }

  return (
    <div className="space-y-4">
      {error ? <Alert tone="error">{error}</Alert> : null}
      {saved && !dirty ? <Alert tone="success">Saved.</Alert> : null}
      <Field label="Diagnosis" hint="What you found and the cause.">
        {(p) => <Textarea {...p} rows={3} value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} />}
      </Field>
      <Field label="Work performed">
        {(p) => <Textarea {...p} rows={3} value={work} onChange={(e) => setWork(e.target.value)} />}
      </Field>
      <Button
        variant="primary"
        disabled={!dirty}
        loading={busy}
        onClick={async () => {
          const ok = await run(() =>
            api("PATCH", `/job-cards/${job.id}`, {
              version: job.version,
              diagnosis: diagnosis.trim() || null,
              work_performed: work.trim() || null,
            }),
          );
          setSaved(ok);
        }}
      >
        Save work record
      </Button>
    </div>
  );
}

// --------------------------------------------------------------------------- details

export function EditDetailsButton({ job }: { job: JobCardDetail }) {
  const [open, setOpen] = useState(false);
  const [priority, setPriority] = useState<Priority>(job.priority);
  const [complaint, setComplaint] = useState(job.complaint);
  const [requested, setRequested] = useState(job.requested_work ?? "");
  const [promised, setPromised] = useState(job.promised_at ? toLocalInput(job.promised_at) : "");
  const { busy, error, run } = useMutation();

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Edit details
      </Button>
      <Dialog open={open} onOpenChange={setOpen} title="Edit job details">
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Customer complaint" required>
            {(p) => <Textarea {...p} rows={3} value={complaint} onChange={(e) => setComplaint(e.target.value)} />}
          </Field>
          <Field label="Requested work">
            {(p) => <Textarea {...p} rows={2} value={requested} onChange={(e) => setRequested(e.target.value)} />}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Priority">
              {(p) => (
                <Select {...p} value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
                  {Object.entries(PRIORITY_LABEL).map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Promised for">
              {(p) => <Input {...p} type="datetime-local" value={promised} onChange={(e) => setPromised(e.target.value)} />}
            </Field>
          </div>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={!complaint.trim()}
              onClick={async () => {
                const ok = await run(() =>
                  api("PATCH", `/job-cards/${job.id}`, {
                    version: job.version,
                    complaint: complaint.trim(),
                    requested_work: requested.trim() || null,
                    priority,
                    promised_at: promised ? new Date(promised).toISOString() : null,
                  }),
                );
                if (ok) setOpen(false);
              }}
            >
              Save
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// --------------------------------------------------------------------------- assignments

export function Assignments({ job }: { job: JobCardDetail }) {
  const router = useRouter();
  const [candidates, setCandidates] = useState<AssignableUser[] | null>(null);
  const [selected, setSelected] = useState("");
  const { busy, error, run } = useMutation();
  const active = job.assignments.filter((a) => !a.unassigned_at);

  async function load() {
    try {
      setCandidates(await api<AssignableUser[]>("GET", `/job-cards/${job.id}/assignable-users`));
    } catch {
      setCandidates([]);
    }
  }

  const available = (candidates ?? []).filter((c) => !active.some((a) => a.user.id === c.id));
  return (
    <div className="space-y-3">
      {error ? <Alert tone="error">{error}</Alert> : null}
      {active.length === 0 ? <p className="text-sm text-muted">No mechanic assigned.</p> : null}
      <ul className="space-y-1.5">
        {active.map((a) => (
          <li key={a.user.id} className="flex items-center justify-between gap-2">
            <span className="font-medium">{a.user.name}</span>
            {job.capabilities.assign ? (
              <ConfirmButton
                trigger={<Button size="sm" variant="ghost">Unassign</Button>}
                title={`Unassign ${a.user.name}?`}
                description="They will no longer see this job unless they can view all jobs at the branch."
                confirmLabel="Unassign"
                onConfirm={async () => {
                  await api("DELETE", `/job-cards/${job.id}/assignments/${a.user.id}`);
                  setCandidates(null);
                  router.refresh();
                }}
              />
            ) : null}
          </li>
        ))}
      </ul>
      {job.capabilities.assign ? (
        candidates === null ? (
          <Button size="sm" onClick={() => void load()}>
            Assign mechanic
          </Button>
        ) : available.length === 0 ? (
          <p className="text-sm text-muted">No other users can work on jobs at this branch.</p>
        ) : (
          <div className="flex gap-2">
            <label htmlFor="assign-user" className="sr-only">
              Mechanic
            </label>
            <Select id="assign-user" value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">Choose mechanic</option>
              {available.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.full_name} ({c.active_jobs} open {c.active_jobs === 1 ? "job" : "jobs"})
                </option>
              ))}
            </Select>
            <Button
              variant="primary"
              disabled={!selected}
              loading={busy}
              onClick={async () => {
                if (await run(() => api("POST", `/job-cards/${job.id}/assignments`, { user_id: selected }))) {
                  setSelected("");
                  setCandidates(null);
                }
              }}
            >
              Assign
            </Button>
          </div>
        )
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------- notes

export function AddNote({ jobId }: { jobId: string }) {
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState<"internal" | "customer">("internal");
  const { busy, error, run } = useMutation();
  return (
    <div className="space-y-2 border-t border-border p-4">
      {error ? <Alert tone="error">{error}</Alert> : null}
      <label htmlFor="new-note" className="sr-only">
        New note
      </label>
      <Textarea id="new-note" rows={2} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add a note" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-steel"
            checked={visibility === "customer"}
            onChange={(e) => setVisibility(e.target.checked ? "customer" : "internal")}
          />
          Customer may see this note
        </label>
        <Button
          size="sm"
          variant="primary"
          disabled={!body.trim()}
          loading={busy}
          onClick={async () => {
            if (await run(() => api("POST", `/job-cards/${jobId}/notes`, { body: body.trim(), visibility }))) setBody("");
          }}
        >
          Add note
        </Button>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- approval exceptions

export function AuthoriseExceptionButton({
  job,
  currency,
  children,
}: {
  job: JobCardDetail;
  currency: string;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<ExceptionType>("customer_verbal");
  const [reason, setReason] = useState("");
  const [scope, setScope] = useState("");
  const [contact, setContact] = useState("");
  const [amount, setAmount] = useState("");
  const { busy, error, run } = useMutation();
  const amountValid = !amount || /^\d{1,12}(\.\d{1,2})?$/.test(amount);

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        {children ?? "Authorise exception"}
      </Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Authorise work without quotation approval"
        description="Use only when the customer has agreed another way, or no charge applies. This is recorded with your name."
      >
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Type">
            {(p) => (
              <Select {...p} value={type} onChange={(e) => setType(e.target.value as ExceptionType)}>
                {Object.entries(EXCEPTION_TYPE_LABEL).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Reason" required hint="Why the work cannot wait for a quotation approval.">
            {(p) => <Textarea {...p} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <Field label="Authorised work" required hint="Exactly what may be done, e.g. Replace front brake pads.">
            {(p) => <Textarea {...p} rows={2} value={scope} onChange={(e) => setScope(e.target.value)} />}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Customer contact" hint="Who agreed, and how.">
              {(p) => <Input {...p} value={contact} onChange={(e) => setContact(e.target.value)} />}
            </Field>
            <Field label={`Maximum amount (${currency === "NAD" ? "N$" : currency})`} hint="Optional." error={amountValid ? undefined : "Use an amount like 2500.00"}>
              {(p) => <Input {...p} inputMode="decimal" className="font-mono" value={amount} onChange={(e) => setAmount(e.target.value)} />}
            </Field>
          </div>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={reason.trim().length < 5 || scope.trim().length < 5 || !amountValid}
              onClick={async () => {
                const ok = await run(() =>
                  api("POST", `/job-cards/${job.id}/approval-exceptions`, {
                    exception_type: type,
                    reason: reason.trim(),
                    scope: scope.trim(),
                    customer_contact: contact.trim() || null,
                    max_amount: amount || null,
                  }),
                );
                if (ok) setOpen(false);
              }}
            >
              Authorise
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}

export function RevokeExceptionButton({ jobId, exceptionId }: { jobId: string; exceptionId: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const { busy, error, run } = useMutation();
  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        Revoke
      </Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Revoke this exception?"
        description="Work that has not started will need customer approval again. The record is kept."
      >
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Reason" required>
            {(p) => <Input {...p} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="danger"
              loading={busy}
              disabled={reason.trim().length < 3}
              onClick={async () => {
                const ok = await run(() =>
                  api("POST", `/job-cards/${jobId}/approval-exceptions/${exceptionId}/revoke`, { reason: reason.trim() }),
                );
                if (ok) {
                  setOpen(false);
                  setReason("");
                }
              }}
            >
              Revoke
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
