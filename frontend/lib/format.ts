import type { DateFormat } from "./api/types";

interface Prefs {
  timezone: string;
  date_format: DateFormat;
}

function parts(value: string | Date, timezone: string) {
  const date = typeof value === "string" ? new Date(value) : value;
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const map = Object.fromEntries(fmt.formatToParts(date).map((p) => [p.type, p.value]));
  return map as Record<"year" | "month" | "day" | "hour" | "minute", string>;
}

/** Date in the organisation's time zone and preferred format. */
export function formatDate(value: string | Date | null | undefined, prefs: Prefs): string {
  if (!value) return "—";
  const p = parts(value, prefs.timezone);
  switch (prefs.date_format) {
    case "YYYY-MM-DD":
      return `${p.year}-${p.month}-${p.day}`;
    case "MM/DD/YYYY":
      return `${p.month}/${p.day}/${p.year}`;
    default:
      return `${p.day}/${p.month}/${p.year}`;
  }
}

export function formatDateTime(value: string | Date | null | undefined, prefs: Prefs): string {
  if (!value) return "—";
  const p = parts(value, prefs.timezone);
  return `${formatDate(value, prefs)} ${p.hour}:${p.minute}`;
}

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/** "08:00:00" → "08:00" */
export function shortTime(value: string | null): string {
  return value ? value.slice(0, 5) : "";
}

/** "2500.5" + "NAD" → "N$ 2,500.50". Amounts arrive as decimal strings; never parsed to float. */
export function formatMoney(amount: string, currency: string): string {
  const negative = amount.startsWith("-");
  const [whole, cents = ""] = amount.replace("-", "").split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const symbol = currency === "NAD" ? "N$" : currency;
  return `${negative ? "-" : ""}${symbol} ${grouped}.${cents.padEnd(2, "0").slice(0, 2)}`;
}
