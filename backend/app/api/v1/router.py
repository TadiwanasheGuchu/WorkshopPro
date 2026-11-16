from fastapi import APIRouter

from app.api.v1 import (
    appointments,
    audit,
    auth,
    branches,
    customers,
    documents,
    files,
    health,
    inspections,
    inventory,
    invoices,
    job_cards,
    organisation,
    quotations,
    reports,
    roles,
    users,
    vehicles,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organisation.router)
api_router.include_router(branches.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(audit.router)
api_router.include_router(customers.router)
api_router.include_router(vehicles.router)
api_router.include_router(job_cards.router)
api_router.include_router(inspections.router)
api_router.include_router(files.router)
api_router.include_router(appointments.router)
api_router.include_router(quotations.router)
api_router.include_router(invoices.router)
api_router.include_router(documents.router)
api_router.include_router(reports.router)
api_router.include_router(inventory.router)
