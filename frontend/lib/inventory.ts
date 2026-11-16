import type { MovementKind, PartUnit } from "./api/types";

export const UNIT_LABEL: Record<PartUnit, string> = {
  each: "Each",
  pair: "Pair",
  set: "Set",
  box: "Box",
  litre: "Litre",
  kg: "Kilogram",
  metre: "Metre",
};

export const WHOLE_UNITS: PartUnit[] = ["each", "pair", "set", "box"];

export const MOVEMENT_LABEL: Record<MovementKind, string> = {
  opening: "Opening stock",
  adjustment: "Adjustment",
  transfer_out: "Transfer out",
  transfer_in: "Transfer in",
  receipt: "Received from supplier",
  issue: "Issued to job",
  return: "Returned from job",
  supplier_return: "Returned to supplier",
};

/** Quantities: drop ".00" for whole numbers ("5", "2.5"). */
export function qty(value: string | null | undefined): string {
  if (value == null) return "—";
  const n = Number(value);
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0$/, "");
}

export function signedQty(value: string): string {
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${qty(value)}`;
}
