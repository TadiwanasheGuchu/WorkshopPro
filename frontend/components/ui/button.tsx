import { Slot } from "radix-ui";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const variants: Record<Variant, string> = {
  // Orange fill, slate text (white on orange fails WCAG AA — see ADR 0003).
  primary: "bg-action text-on-action hover:bg-action-hover font-semibold",
  secondary: "bg-surface text-slate-deep border border-border hover:bg-mist",
  ghost: "text-slate-deep hover:bg-mist",
  danger: "bg-surface text-status-danger border border-border hover:bg-status-danger-tint",
};

const sizes: Record<Size, string> = {
  // Mobile-first: 40px min touch target on md; sm is for dense desktop toolbars.
  sm: "h-8 px-2.5 text-sm gap-1.5",
  md: "h-10 px-3.5 text-sm gap-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  asChild?: boolean;
  loading?: boolean;
}

export function Button({
  variant = "secondary",
  size = "md",
  asChild = false,
  loading = false,
  className,
  disabled,
  children,
  type,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      type={asChild ? undefined : (type ?? "button")}
      disabled={asChild ? undefined : disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-control whitespace-nowrap",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {children}
    </Comp>
  );
}
