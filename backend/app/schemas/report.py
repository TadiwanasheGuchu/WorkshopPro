import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.job_card import JobStatus, Ref


class Period(BaseModel):
    date_from: date
    date_to: date
    timezone: str


class Definition(BaseModel):
    term: str
    definition: str


class CountAmount(BaseModel):
    count: int
    total: Decimal


class InvoicedTotals(BaseModel):
    count: int
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal


class MethodRow(BaseModel):
    method: str
    received: Decimal
    paid_out: Decimal  # refunds and reversals


class DayRow(BaseModel):
    date: date
    invoiced: Decimal
    received: Decimal


class AgeingRow(BaseModel):
    bucket: str
    count: int
    amount: Decimal


class Receivables(BaseModel):
    as_at: date
    outstanding: Decimal
    overdue: Decimal
    open_invoices: int
    ageing: list[AgeingRow]
    unapplied_credit: Decimal


class FinancialReport(BaseModel):
    period: Period
    branch: Ref | None
    currency_code: str
    invoiced: InvoicedTotals
    credited: CountAmount
    net_invoiced: Decimal
    received: CountAmount
    refunded: CountAmount
    reversed: CountAmount
    net_received: Decimal
    by_method: list[MethodRow]
    daily: list[DayRow]
    receivables: Receivables
    definitions: list[Definition]


class MechanicRow(BaseModel):
    user_id: uuid.UUID
    name: str
    open_jobs: int
    completed_in_period: int


class QuotationOutcomes(BaseModel):
    sent: int
    approved: int
    rejected: int
    approved_value: Decimal


class OperationsReport(BaseModel):
    period: Period
    branch: Ref | None
    currency_code: str
    received: int
    completed: int
    cancelled: int
    turnaround_hours_avg: float | None
    turnaround_hours_median: float | None
    open_by_status: dict[JobStatus, int]
    open_total: int
    overdue_now: int
    quotations: QuotationOutcomes
    mechanics: list[MechanicRow]
    definitions: list[Definition]


# --------------------------------------------------------------------------- inventory


class LocationValue(BaseModel):
    location: Ref
    branch: Ref
    units: Decimal
    value: Decimal


class CategoryValue(BaseModel):
    category: str
    parts: int
    units: Decimal
    value: Decimal


class Valuation(BaseModel):
    as_at: date
    total_value: Decimal
    parts_in_stock: int
    units: Decimal
    by_location: list[LocationValue]
    by_category: list[CategoryValue]


class MovementSummary(BaseModel):
    kind: str
    count: int
    quantity: Decimal
    value: Decimal  # signed: quantity x unit cost at the time


class PartUsage(BaseModel):
    part: Ref
    sku: str
    quantity: Decimal
    cost_value: Decimal


class PurchasingSummary(BaseModel):
    orders_approved: int
    approved_value: Decimal
    received_value: Decimal
    returned_value: Decimal
    open_orders: int
    open_value: Decimal
    overdue_orders: int


class Reconciliation(BaseModel):
    stock_levels_checked: int
    on_hand_mismatches: int
    reserved_mismatches: int


class InventoryReport(BaseModel):
    period: Period
    branch: Ref | None
    currency_code: str
    valuation: Valuation
    low_stock_parts: int
    movements: list[MovementSummary]
    usage: list[PartUsage]
    purchasing: PurchasingSummary
    reconciliation: Reconciliation
    definitions: list[Definition]
