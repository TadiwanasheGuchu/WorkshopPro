"""ORM models.

Import every model module here so Alembic autogenerate sees all tables.
"""

from app.db.base import Base
from app.models.audit import AuditLog
from app.models.branch import Branch, BranchOperatingHours, ServiceBay
from app.models.customer import (
    Customer,
    CustomerAddress,
    CustomerConsent,
    CustomerContact,
    Vehicle,
    VehicleOwnership,
)
from app.models.identity import (
    Role,
    RolePermission,
    User,
    UserRoleAssignment,
    UserSession,
    UserToken,
)
from app.models.organisation import (
    DocumentSequence,
    Organisation,
    OrganisationSettings,
    TaxRate,
)

__all__ = [
    "AuditLog",
    "Base",
    "Branch",
    "BranchOperatingHours",
    "Customer",
    "CustomerAddress",
    "CustomerConsent",
    "CustomerContact",
    "DocumentSequence",
    "Organisation",
    "OrganisationSettings",
    "Role",
    "RolePermission",
    "ServiceBay",
    "TaxRate",
    "User",
    "UserRoleAssignment",
    "UserSession",
    "UserToken",
    "Vehicle",
    "VehicleOwnership",
]
