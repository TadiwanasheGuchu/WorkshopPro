"""Quotation, invoice, credit note and receipt PDFs."""

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Spacer

from app.documents.base import (
    CONTENT_W,
    Document,
    OrgInfo,
    Party,
    data_table,
    heading,
    keep,
    money,
    p,
    paragraph_block,
    quantity,
    small,
    totals,
)
from app.schemas.invoice import InvoiceRead, PaymentRead
from app.schemas.quotation import ItemRead, QuotationRead

KIND = {"labour": "Labour", "part": "Part", "fee": "Fee", "discount": "Discount"}
METHOD = {
    "cash": "Cash",
    "eft": "EFT / bank transfer",
    "card": "Card",
    "mobile": "Mobile money",
    "cheque": "Cheque",
    "other": "Other",
}
DECISION_METHOD = {
    "customer_link": "online",
    "in_person": "in person",
    "phone": "by phone",
    "email": "by email",
    "whatsapp": "by WhatsApp",
    "other": "other",
}


def _lines_table(items: Sequence[ItemRead], currency: str, prices_include_tax: bool) -> Flowable:
    rows = []
    for i in items:
        desc: list[Flowable] = [p(i.description)]
        detail = KIND[i.kind] + (f" · {i.part_number}" if i.part_number else "")
        desc.append(small(detail))
        rows.append(
            [
                desc,
                quantity(i.quantity),
                money(i.unit_price, currency),
                f"{quantity(i.tax_rate_percent)}%" if i.tax_rate_name else "—",
                money(i.line_total if prices_include_tax else i.line_subtotal, currency),
            ]
        )
    return data_table(
        ["Description", "Qty", "Unit price", "Tax", "Amount"],
        rows,
        [CONTENT_W - 112 * mm, 18 * mm, 32 * mm, 18 * mm, 44 * mm],
        right_cols=(1, 2, 3, 4),
    )


def _tax_rows(items: Sequence[ItemRead], currency: str) -> list[tuple[str, str]]:
    """Tax per rate, summed from the server-calculated line tax."""
    by_rate: OrderedDict[str, Decimal] = OrderedDict()
    for i in items:
        if i.tax_rate_name:
            label = f"{i.tax_rate_name} ({quantity(i.tax_rate_percent)}%)"
            by_rate[label] = by_rate.get(label, Decimal(0)) + i.line_tax
    return [(f"Tax: {label}", money(amount, currency)) for label, amount in by_rate.items()]


def _amount_rows(
    items: Sequence[ItemRead],
    currency: str,
    subtotal: Decimal,
    tax_total: Decimal,
    total: Decimal,
) -> list[tuple[str, str]]:
    rows = [("Subtotal (excl. tax)", money(subtotal, currency))]
    rows += _tax_rows(items, currency) or [("Tax", money(tax_total, currency))]
    rows.append(("Total", money(total, currency)))
    return rows


# --------------------------------------------------------------------------- quotation


def quotation(org: OrgInfo, q: QuotationRead, customer: Party) -> bytes:
    v = q.current
    c = v.currency_code
    notice = None
    if v.status == "draft":
        notice = "Draft: not yet sent to the customer. Prices and scope may change."
    elif v.status == "expired":
        notice = (
            f"This quotation expired on {org.date(v.valid_until)}. "
            "Ask the workshop for an updated quotation."
        )
    elif v.decision:
        d = v.decision
        verb = "Approved" if d.decision == "approved" else "Declined"
        how = DECISION_METHOD.get(d.method, d.method)
        notice = (
            f"{verb} by {d.customer_name} {how} on {org.datetime(d.decided_at)} "
            f"for {money(d.total, d.currency_code)} (version {v.version_number})."
        )

    body: list[Flowable] = [_lines_table(v.items, c, v.prices_include_tax), Spacer(1, 3 * mm)]
    body.append(keep(totals(_amount_rows(v.items, c, v.subtotal, v.tax_total, v.total))))
    if v.prices_include_tax:
        body.append(small("Prices include tax."))
    body += paragraph_block("Notes", v.notes)
    body += paragraph_block("Terms", v.terms)
    body += [
        Spacer(1, 4 * mm),
        small(
            "Work starts only after you approve this exact quotation version. "
            "Any change in scope or price needs a new approval."
        ),
    ]
    return Document(
        org=org,
        title="Quotation",
        meta=[
            ("Quotation", q.quote_number),
            ("Version", str(v.version_number)),
            ("Date", org.date(v.sent_at or v.created_at)),
            ("Valid until", org.date(v.valid_until)),
            ("Job", q.job_card.name),
        ],
        customer=customer,
        vehicle=_vehicle(
            q.vehicle.registration_number,
            q.vehicle.make,
            q.vehicle.model,
            q.vehicle.year,
            q.vehicle.vin,
        ),
        notice=notice,
        body=body,
    ).render()


def _vehicle(
    registration: str | None,
    make: str | None,
    model: str | None,
    year: int | None,
    vin: str | None,
    odometer_km: int | None = None,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    title = " ".join(str(x) for x in (year, make, model) if x)
    if title:
        rows.append(("", title))
    if registration:
        rows.append(("Registration", registration))
    if vin:
        rows.append(("VIN", vin))
    if odometer_km is not None:
        rows.append(("Odometer", f"{odometer_km:,} km"))
    return rows


@dataclass(frozen=True)
class VehicleInfo:
    registration: str | None
    make: str | None
    model: str | None
    year: int | None
    vin: str | None
    odometer_km: int | None = None

    def rows(self) -> list[tuple[str, str]]:
        return _vehicle(
            self.registration, self.make, self.model, self.year, self.vin, self.odometer_km
        )


# --------------------------------------------------------------------------- invoice


def invoice(org: OrgInfo, inv: InvoiceRead, customer: Party, vehicle: VehicleInfo | None) -> bytes:
    c = inv.currency_code
    notice = None
    if inv.status == "draft":
        notice = "Draft: this is not an invoice. Do not pay against this document."
    elif inv.payment_status == "credited":
        notice = "This invoice has been fully credited. Nothing is owed."

    rows = _amount_rows(inv.items, c, inv.subtotal, inv.tax_total, inv.total)
    body: list[Flowable] = [_lines_table(inv.items, c, inv.prices_include_tax), Spacer(1, 3 * mm)]
    body.append(keep(totals(rows)))
    if inv.prices_include_tax:
        body.append(small("Prices include tax."))
    if inv.status == "issued":
        balance = inv.balance_due
        settlement = []
        if inv.amount_credited:
            settlement.append(("Credited", money(-inv.amount_credited, c)))
        settlement.append(("Paid", money(-inv.amount_paid, c)))
        settlement.append(("Overpaid" if balance < 0 else "Balance due", money(abs(balance), c)))
        body += [Spacer(1, 2 * mm), keep(totals(settlement))]

        if inv.payments:
            body.append(heading("Payments"))
            body.append(
                data_table(
                    ["Receipt", "Date", "Method", "Amount"],
                    [
                        [
                            (
                                "Refund "
                                if x.kind == "refund"
                                else "Reversal "
                                if x.kind == "reversal"
                                else ""
                            )
                            + x.receipt_number,
                            org.date(x.received_at),
                            METHOD[x.method],
                            money(x.amount, c),
                        ]
                        for x in inv.payments
                    ],
                    [40 * mm, 30 * mm, CONTENT_W - 110 * mm, 40 * mm],
                    right_cols=(3,),
                )
            )
        if inv.credit_notes:
            body.append(heading("Credit notes"))
            body.append(
                data_table(
                    ["Credit note", "Date", "Reason", "Amount"],
                    [
                        [
                            cn.credit_note_number,
                            org.date(cn.issue_date),
                            cn.reason,
                            money(cn.total, c),
                        ]
                        for cn in inv.credit_notes
                    ],
                    [32 * mm, 26 * mm, CONTENT_W - 98 * mm, 40 * mm],
                    right_cols=(3,),
                )
            )
    body += paragraph_block("Notes", inv.notes)
    body += paragraph_block("Terms", inv.terms)
    meta = [("Invoice", inv.invoice_number or "Draft")]
    if inv.status == "issued":
        meta += [("Issue date", org.date(inv.issue_date)), ("Due date", org.date(inv.due_date))]
    if inv.job_card:
        meta.append(("Job", inv.job_card.name))
    return Document(
        org=org,
        title="Invoice",
        meta=meta,
        customer=customer,
        vehicle=vehicle.rows() if vehicle else [],
        notice=notice,
        body=body,
    ).render()


# --------------------------------------------------------------------------- credit note


@dataclass(frozen=True)
class CreditNoteLine:
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate_name: str | None
    tax_rate_percent: Decimal
    line_subtotal: Decimal
    line_tax: Decimal
    line_total: Decimal


def credit_note(
    org: OrgInfo,
    *,
    number: str,
    issue_date: object,
    reason: str,
    invoice_number: str,
    currency: str,
    prices_include_tax: bool,
    lines: Sequence[CreditNoteLine],
    subtotal: Decimal,
    tax_total: Decimal,
    total: Decimal,
    customer: Party,
) -> bytes:
    rows = [
        [
            ln.description,
            quantity(ln.quantity),
            money(ln.unit_price, currency),
            f"{quantity(ln.tax_rate_percent)}%" if ln.tax_rate_name else "—",
            money(ln.line_total if prices_include_tax else ln.line_subtotal, currency),
        ]
        for ln in lines
    ]
    body: list[Flowable] = [
        data_table(
            ["Description", "Qty", "Unit price", "Tax", "Amount"],
            rows,
            [CONTENT_W - 112 * mm, 18 * mm, 32 * mm, 18 * mm, 44 * mm],
            right_cols=(1, 2, 3, 4),
        ),
        Spacer(1, 3 * mm),
        keep(
            totals(
                [
                    ("Subtotal (excl. tax)", money(subtotal, currency)),
                    ("Tax", money(tax_total, currency)),
                    ("Total credited", money(total, currency)),
                ]
            )
        ),
        heading("Reason"),
        p(reason),
        Spacer(1, 3 * mm),
        small(f"This credit note reduces the amount owed on invoice {invoice_number}."),
    ]
    return Document(
        org=org,
        title="Credit note",
        meta=[
            ("Credit note", number),
            ("Date", org.date(issue_date)),  # type: ignore[arg-type]
            ("Invoice", invoice_number),
        ],
        customer=customer,
        body=body,
    ).render()


# --------------------------------------------------------------------------- receipt


def receipt(org: OrgInfo, pay: PaymentRead, customer: Party) -> bytes:
    c = pay.currency_code
    title = {"payment": "Receipt", "refund": "Refund", "reversal": "Payment reversal"}[pay.kind]
    notice = None
    if pay.reversed_by_receipt:
        notice = (
            f"This payment was reversed by {pay.reversed_by_receipt} "
            "and no longer counts towards any invoice."
        )
    elif pay.reverses_receipt:
        notice = f"Reverses payment {pay.reverses_receipt}."

    verb = {
        "payment": "Amount received",
        "refund": "Amount paid back",
        "reversal": "Amount reversed",
    }[pay.kind]
    details = [
        (verb, money(pay.amount, c)),
        ("Method", METHOD[pay.method] + (" (recorded only)" if pay.method == "card" else "")),
    ]
    if pay.reference:
        details.append(("Reference", pay.reference))
    body: list[Flowable] = [
        data_table([], details, [50 * mm, CONTENT_W - 50 * mm]),
    ]
    if pay.allocations:
        body.append(heading("Applied to"))
        body.append(
            data_table(
                ["Invoice", "Amount"],
                [[a.invoice_number or "", money(a.amount, c)] for a in pay.allocations],
                [CONTENT_W - 50 * mm, 50 * mm],
                right_cols=(1,),
            )
        )
    if pay.kind == "payment" and not pay.reversed_by_receipt and pay.unallocated > 0:
        body += [
            Spacer(1, 2 * mm),
            small(f"{money(pay.unallocated, c)} is held as credit on your account."),
        ]
    if pay.notes and pay.kind != "payment":
        body += paragraph_block("Reason", pay.notes)
    body += [Spacer(1, 4 * mm), small(f"Recorded by {pay.recorded_by} at {pay.branch.name}.")]
    return Document(
        org=org,
        title=title,
        meta=[(title, pay.receipt_number), ("Date", org.datetime(pay.received_at))],
        customer=customer,
        notice=notice,
        body=body,
    ).render()
