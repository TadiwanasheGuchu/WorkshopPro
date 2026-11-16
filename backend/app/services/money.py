"""Money arithmetic. Decimal only, never float (CLAUDE.md §3.9).

Amounts are rounded to cents with ROUND_HALF_UP per line; document totals are the sum
of rounded line amounts, so the printed lines always add up to the printed total.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LineAmounts:
    subtotal: Decimal  # excluding tax
    tax: Decimal
    total: Decimal  # including tax


def line_amounts(
    quantity: Decimal,
    unit_price: Decimal,
    tax_percent: Decimal,
    *,
    prices_include_tax: bool,
    negative: bool = False,
) -> LineAmounts:
    """Amounts for one line. `negative` is used for discount lines."""
    gross = cents(quantity * unit_price)
    if negative:
        gross = -gross
    rate = tax_percent / HUNDRED
    if prices_include_tax:
        total = gross
        subtotal = cents(gross / (1 + rate)) if rate else gross
        tax = total - subtotal
    else:
        subtotal = gross
        tax = cents(gross * rate)
        total = subtotal + tax
    return LineAmounts(subtotal=subtotal, tax=tax, total=total)


def sum_amounts(lines: list[LineAmounts]) -> LineAmounts:
    return LineAmounts(
        subtotal=sum((x.subtotal for x in lines), ZERO),
        tax=sum((x.tax for x in lines), ZERO),
        total=sum((x.total for x in lines), ZERO),
    )
