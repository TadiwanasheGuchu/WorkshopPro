from fastapi import APIRouter

from app.api.v1 import (
    audit,
    auth,
    branches,
    customers,
    health,
    job_cards,
    organisation,
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
