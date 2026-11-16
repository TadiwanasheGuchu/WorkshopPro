import type { QuoteItem } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { LINE_KIND } from "@/lib/quotation";

interface LinesDocument {
  items: QuoteItem[];
  currency_code: string;
  prices_include_tax: boolean;
  subtotal: string;
  tax_total: string;
  total: string;
}

/** Read-only lines and totals of a quotation or invoice. Amounts come from the server;
 * nothing is calculated here. */
export function DocumentLines({ document: version }: { document: LinesDocument }) {
  const c = version.currency_code;
  return (
    <div>
      <table className="hidden w-full text-sm md:table">
        <thead className="border-b border-border text-xs text-muted">
          <tr>
            <th className="py-2 pr-3 text-left font-medium">Item</th>
            <th className="py-2 pr-3 text-right font-medium">Qty</th>
            <th className="py-2 pr-3 text-right font-medium">Unit price</th>
            <th className="py-2 pr-3 text-right font-medium">Tax</th>
            <th className="py-2 text-right font-medium">Amount</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {version.items.map((i) => (
            <tr key={i.id}>
              <td className="py-2 pr-3">
                <span className="text-xs text-muted">{LINE_KIND[i.kind]}</span>
                <p>{i.description}</p>
                {i.part_number ? <p className="font-mono text-xs text-muted">{i.part_number}</p> : null}
              </td>
              <td className="py-2 pr-3 text-right font-mono tabular-nums">{i.quantity}</td>
              <td className="py-2 pr-3 text-right font-mono tabular-nums">{formatMoney(i.unit_price, c)}</td>
              <td className="py-2 pr-3 text-right text-xs text-muted">{i.tax_rate_name ? `${i.tax_rate_percent}%` : "—"}</td>
              <td className="py-2 text-right font-mono tabular-nums">{formatMoney(version.prices_include_tax ? i.line_total : i.line_subtotal, c)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="divide-y divide-border md:hidden">
        {version.items.map((i) => (
          <li key={i.id} className="flex justify-between gap-3 py-2 text-sm">
            <div>
              <p>{i.description}</p>
              <p className="text-xs text-muted">
                {LINE_KIND[i.kind]} · {i.quantity} × {formatMoney(i.unit_price, c)}
              </p>
            </div>
            <span className="font-mono tabular-nums">{formatMoney(version.prices_include_tax ? i.line_total : i.line_subtotal, c)}</span>
          </li>
        ))}
      </ul>
      <dl className="mt-3 ml-auto w-full max-w-xs space-y-1 border-t border-border pt-3 text-sm">
        <div className="flex justify-between">
          <dt className="text-muted">Subtotal (excl. tax)</dt>
          <dd className="font-mono tabular-nums">{formatMoney(version.subtotal, c)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Tax</dt>
          <dd className="font-mono tabular-nums">{formatMoney(version.tax_total, c)}</dd>
        </div>
        <div className="flex justify-between text-base font-semibold">
          <dt>Total</dt>
          <dd className="font-mono tabular-nums">{formatMoney(version.total, c)}</dd>
        </div>
        {version.prices_include_tax ? <p className="text-xs text-muted">Prices include tax.</p> : null}
      </dl>
    </div>
  );
}
