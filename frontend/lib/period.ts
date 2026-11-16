/** Report periods as inclusive local dates (YYYY-MM-DD) in the organisation's time zone. */

export function localToday(timezone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}

const iso = (d: Date) => d.toISOString().slice(0, 10);
const parse = (s: string) => new Date(`${s}T00:00:00Z`);

export interface Preset {
  key: string;
  label: string;
  from: string;
  to: string;
}

export function presets(today: string): Preset[] {
  const t = parse(today);
  const y = t.getUTCFullYear();
  const m = t.getUTCMonth();
  const monthStart = new Date(Date.UTC(y, m, 1));
  const lastMonthStart = new Date(Date.UTC(y, m - 1, 1));
  const lastMonthEnd = new Date(Date.UTC(y, m, 0));
  const minus = (days: number) => new Date(t.getTime() - days * 86_400_000);
  return [
    { key: "today", label: "Today", from: today, to: today },
    { key: "this-month", label: "This month", from: iso(monthStart), to: today },
    { key: "last-month", label: "Last month", from: iso(lastMonthStart), to: iso(lastMonthEnd) },
    { key: "last-30", label: "Last 30 days", from: iso(minus(29)), to: today },
    { key: "year", label: "Year to date", from: `${y}-01-01`, to: today },
  ];
}

export const isDate = (v: unknown): v is string => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);
