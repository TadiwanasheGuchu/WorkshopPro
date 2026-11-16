"""Pricing of document lines (quotations, invoices), shared so they never diverge."""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import TaxRate
from app.services.money import LineAmounts, line_amounts, sum_amounts


@dataclass(frozen=True)
class PricedLine:
    fields: dict[str, Any]  # column values for the item row
    amounts: LineAmounts


def price_lines(
    db: Session,
    organisation_id: uuid.UUID,
    items: list[Any],
    *,
    prices_include_tax: bool,
) -> tuple[list[PricedLine], LineAmounts]:
    """Validate tax rates (active, same organisation), snapshot them, and price each line.

    `items` are objects with kind, description, part_number, quantity, unit_price and
    tax_rate_id attributes (the ItemInput schema).
    """
    rate_ids = {i.tax_rate_id for i in items if i.tax_rate_id}
    rates = {
        r.id: r
        for r in db.scalars(
            select(TaxRate).where(
                TaxRate.id.in_(rate_ids), TaxRate.organisation_id == organisation_id
            )
        )
    }
    for rid in rate_ids:
        if rid not in rates or not rates[rid].is_active:
            raise ConflictError("Choose an active tax rate.", details={"tax_rate_id": str(rid)})

    priced = []
    for pos, i in enumerate(items):
        rate = rates.get(i.tax_rate_id) if i.tax_rate_id else None
        percent = rate.rate_percent if rate else Decimal("0")
        amounts = line_amounts(
            i.quantity,
            i.unit_price,
            percent,
            prices_include_tax=prices_include_tax,
            negative=i.kind == "discount",
        )
        priced.append(
            PricedLine(
                fields={
                    "position": pos,
                    "kind": i.kind,
                    "description": i.description,
                    "part_number": i.part_number,
                    "quantity": i.quantity,
                    "unit_price": i.unit_price,
                    "tax_rate_id": rate.id if rate else None,
                    "tax_rate_name": rate.name if rate else None,
                    "tax_rate_percent": percent,
                    "line_subtotal": amounts.subtotal,
                    "line_tax": amounts.tax,
                    "line_total": amounts.total,
                },
                amounts=amounts,
            )
        )
    return priced, sum_amounts([p.amounts for p in priced])


ITEM_COLUMNS = (
    "position",
    "kind",
    "description",
    "part_number",
    "quantity",
    "unit_price",
    "tax_rate_id",
    "tax_rate_name",
    "tax_rate_percent",
    "line_subtotal",
    "line_tax",
    "line_total",
)
