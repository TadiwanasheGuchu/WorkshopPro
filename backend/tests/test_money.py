from decimal import Decimal as D  # noqa: N817 - short alias keeps the tables readable

import pytest

from app.services.money import line_amounts, sum_amounts


@pytest.mark.parametrize(
    ("qty", "price", "rate", "incl", "expected"),
    [
        # Tax-exclusive prices: tax added on top.
        ("2", "450.00", "15", False, ("900.00", "135.00", "1035.00")),
        ("1.5", "380.00", "15", False, ("570.00", "85.50", "655.50")),
        ("3", "33.33", "15", False, ("99.99", "15.00", "114.99")),  # 14.9985 -> 15.00
        # Tax-inclusive prices: tax extracted.
        ("1", "1150.00", "15", True, ("1000.00", "150.00", "1150.00")),
        ("1", "100.00", "15", True, ("86.96", "13.04", "100.00")),
        # Zero-rated.
        ("4", "12.50", "0", False, ("50.00", "0.00", "50.00")),
    ],
)
def test_line_amounts(
    qty: str, price: str, rate: str, incl: bool, expected: tuple[str, str, str]
) -> None:
    a = line_amounts(D(qty), D(price), D(rate), prices_include_tax=incl)
    assert (str(a.subtotal), str(a.tax), str(a.total)) == expected


def test_discount_line_is_negative_and_reduces_tax() -> None:
    a = line_amounts(D("1"), D("100.00"), D("15"), prices_include_tax=False, negative=True)
    assert (a.subtotal, a.tax, a.total) == (D("-100.00"), D("-15.00"), D("-115.00"))


def test_totals_are_sum_of_rounded_lines() -> None:
    lines = [line_amounts(D("1"), D("0.10"), D("15"), prices_include_tax=False) for _ in range(3)]
    total = sum_amounts(lines)
    # Each line: 0.10 + 0.02 (0.015 rounds half up) = 0.12; total 0.36, not 0.345 rounded.
    assert (total.subtotal, total.tax, total.total) == (D("0.30"), D("0.06"), D("0.36"))
