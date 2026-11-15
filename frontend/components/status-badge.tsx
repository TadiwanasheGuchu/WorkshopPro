/**
 * The only way to render a status in WorkshopPro (CLAUDE.md §9 "Status colours").
 * Tint background + solid dot + slate text. Do not create ad-hoc status colours.
 */

export type StatusTone = "neutral" | "active" | "waiting" | "success" | "danger";

const toneClasses: Record<StatusTone, { badge: string; dot: string }> = {
  neutral: { badge: "bg-status-neutral-tint", dot: "bg-status-neutral" },
  active: { badge: "bg-status-active-tint", dot: "bg-status-active" },
  waiting: { badge: "bg-status-waiting-tint", dot: "bg-status-waiting" },
  success: { badge: "bg-status-success-tint", dot: "bg-status-success" },
  danger: { badge: "bg-status-danger-tint", dot: "bg-status-danger" },
};

export function StatusBadge({ tone, children }: { tone: StatusTone; children: React.ReactNode }) {
  const classes = toneClasses[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-control px-2 py-0.5 text-xs font-medium text-slate-deep ${classes.badge}`}
    >
      <span aria-hidden="true" className={`size-1.5 rounded-full ${classes.dot}`} />
      {children}
    </span>
  );
}
