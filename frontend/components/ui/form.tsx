import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const control =
  "block w-full rounded-control border border-border bg-surface px-3 text-slate-deep " +
  "placeholder:text-muted disabled:bg-mist disabled:text-muted " +
  "aria-[invalid=true]:border-status-danger";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(control, "h-10", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(control, "min-h-20 py-2", className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(control, "h-10 pr-8", className)} {...props}>
      {children}
    </select>
  );
}

export function Checkbox({
  label,
  description,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; description?: ReactNode }) {
  const id = useId();
  return (
    <div className={cn("flex items-start gap-2.5", className)}>
      <input
        id={id}
        type="checkbox"
        className="mt-0.5 size-4 shrink-0 accent-steel"
        aria-describedby={description ? `${id}-d` : undefined}
        {...props}
      />
      <div>
        <label htmlFor={id} className="font-medium">
          {label}
        </label>
        {description ? (
          <p id={`${id}-d`} className="text-xs text-muted">
            {description}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Label + control + hint + error. The child control receives id/aria props through
 * the render function so the label and messages stay connected for screen readers.
 */
export function Field({
  label,
  hint,
  error,
  required,
  className,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  className?: string;
  children: (props: { id: string; "aria-invalid"?: boolean; "aria-describedby"?: string }) => ReactNode;
}) {
  const id = useId();
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(" ");
  return (
    <div className={cn("space-y-1", className)}>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
        {required ? <span className="text-muted"> (required)</span> : null}
      </label>
      {children({
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": describedBy || undefined,
      })}
      {hint && !error ? (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="text-xs font-medium text-status-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
