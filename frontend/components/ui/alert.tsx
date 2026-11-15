import { CircleAlert, CircleCheck, Info } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "error" | "success" | "info";

const tones: Record<Tone, { box: string; icon: ReactNode }> = {
  error: {
    box: "border-status-danger/40 bg-status-danger-tint",
    icon: <CircleAlert className="size-4 text-status-danger" aria-hidden />,
  },
  success: {
    box: "border-status-success/40 bg-status-success-tint",
    icon: <CircleCheck className="size-4 text-status-success" aria-hidden />,
  },
  info: {
    box: "border-border bg-surface",
    icon: <Info className="size-4 text-steel" aria-hidden />,
  },
};

/** Inline message. Errors are announced to screen readers. */
export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  const t = tones[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("flex gap-2.5 rounded-control border px-3 py-2.5 text-sm", t.box, className)}
    >
      <span className="mt-0.5">{t.icon}</span>
      <div>
        {title ? <p className="font-medium">{title}</p> : null}
        {children ? <div className={title ? "text-muted" : undefined}>{children}</div> : null}
      </div>
    </div>
  );
}
