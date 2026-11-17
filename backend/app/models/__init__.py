"""ORM models.

Import every model module here so Alembic autogenerate sees all tables.
"""

from app.db.base import Base
from app.models.appointment import Appointment, AppointmentRequest
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
from app.models.inspection import (
    Inspection,
    InspectionAmendment,
    InspectionItem,
    InspectionPhoto,
    InspectionTemplate,
    InspectionTemplateItem,
    StoredFile,
)
from app.models.inventory import (
    Part,
    PartCategory,
    StockLevel,
    StockLocation,
    StockMovement,
    StockOperation,
    StockReservation,
)
from app.models.invoice import (
    CreditNote,
    CreditNoteItem,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentAllocation,
)
from app.models.job_card import (
    JobApprovalException,
    JobAssignment,
    JobCard,
    JobNote,
    JobStatusHistory,
)
from app.models.notification import Notification, NotificationTemplate, ServiceReminder
from app.models.organisation import (
    DocumentSequence,
    Organisation,
    OrganisationSettings,
    TaxRate,
)
from app.models.portal import PortalAccount, PortalSession, PortalToken
from app.models.purchasing import (
    GoodsReceivedLine,
    GoodsReceivedNote,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierPart,
    SupplierReturn,
    SupplierReturnLine,
)
from app.models.quotation import (
    Quotation,
    QuotationDecision,
    QuotationItem,
    QuotationLink,
    QuotationVersion,
)
from app.models.storage import StoredObject

__all__ = [
    "Appointment",
    "AppointmentRequest",
    "AuditLog",
    "Base",
    "Branch",
    "BranchOperatingHours",
    "CreditNote",
    "CreditNoteItem",
    "Customer",
    "CustomerAddress",
    "CustomerConsent",
    "CustomerContact",
    "DocumentSequence",
    "GoodsReceivedLine",
    "GoodsReceivedNote",
    "Inspection",
    "InspectionAmendment",
    "InspectionItem",
    "InspectionPhoto",
    "InspectionTemplate",
    "InspectionTemplateItem",
    "Invoice",
    "InvoiceItem",
    "JobApprovalException",
    "JobAssignment",
    "JobCard",
    "JobNote",
    "JobStatusHistory",
    "Notification",
    "NotificationTemplate",
    "Organisation",
    "OrganisationSettings",
    "Part",
    "PartCategory",
    "Payment",
    "PaymentAllocation",
    "PortalAccount",
    "PortalSession",
    "PortalToken",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "Quotation",
    "QuotationDecision",
    "QuotationItem",
    "QuotationLink",
    "QuotationVersion",
    "Role",
    "RolePermission",
    "ServiceBay",
    "ServiceReminder",
    "StockLevel",
    "StockLocation",
    "StockMovement",
    "StockOperation",
    "StockReservation",
    "StoredFile",
    "StoredObject",
    "Supplier",
    "SupplierPart",
    "SupplierReturn",
    "SupplierReturnLine",
    "TaxRate",
    "User",
    "UserRoleAssignment",
    "UserSession",
    "UserToken",
    "Vehicle",
    "VehicleOwnership",
]
