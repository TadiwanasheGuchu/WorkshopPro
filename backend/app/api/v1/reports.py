import uuid
from datetime import date

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession
from app.schemas.report import FinancialReport, OperationsReport
from app.services import reports

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "/financial",
    response_model=FinancialReport,
    summary="Financial report for a period",
    description=(
        "Invoiced, credited, received, refunded and reversed amounts for inclusive local "
        "dates (at most 366 days), plus receivables as at today. Invoices issued are not "
        "cash received; see `definitions` in the response."
    ),
)
def financial(
    principal: CurrentPrincipal,
    db: DbSession,
    date_from: date,
    date_to: date,
    branch_id: uuid.UUID | None = None,
) -> FinancialReport:
    return reports.financial(db, principal, date_from, date_to, branch_id)


@router.get(
    "/operations",
    response_model=OperationsReport,
    summary="Operations report for a period",
    description=(
        "Jobs received, completed and cancelled, turnaround, quotation outcomes and mechanic "
        "workload. 'Open now' figures are current, not as at the end of the period."
    ),
)
def operations(
    principal: CurrentPrincipal,
    db: DbSession,
    date_from: date,
    date_to: date,
    branch_id: uuid.UUID | None = None,
) -> OperationsReport:
    return reports.operations(db, principal, date_from, date_to, branch_id)
