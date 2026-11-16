"""Organisation bootstrap, profile, preferences, tax rates and document numbering."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.core.time import utcnow
from app.models import (
    DocumentSequence,
    Organisation,
    OrganisationSettings,
    Role,
    RolePermission,
    TaxRate,
    User,
    UserRoleAssignment,
)
from app.permissions.catalogue import DEFAULT_ROLES, P
from app.permissions.principal import Principal
from app.schemas.organisation import (
    DocumentSequenceUpdate,
    OrganisationUpdate,
    SettingsUpdate,
    TaxRateCreate,
    TaxRateUpdate,
)
from app.services import audit, branches, inspection_templates, numbering
from app.services.common import apply_changes, get_scoped

# --------------------------------------------------------------------------- bootstrap


@dataclass(frozen=True)
class BootstrapResult:
    organisation: Organisation
    owner: User


def create_organisation(
    db: Session,
    *,
    name: str,
    owner_email: str,
    owner_name: str,
    owner_password: str,
    branch_name: str = "Main branch",
    branch_code: str = "MAIN",
) -> BootstrapResult:
    """Create an organisation with settings, numbering, default roles, a first branch and
    an owner account. Used by the installation CLI; there is no public sign-up."""
    if db.scalar(select(User.id).where(User.email == owner_email)) is not None:
        raise ConflictError("A user with this email already exists.")

    now = utcnow()
    org = Organisation(name=name)
    db.add(org)
    db.flush()
    db.add(OrganisationSettings(organisation_id=org.id))
    numbering.seed_sequences(db, org.id)

    owner_role_id: uuid.UUID | None = None
    for template in DEFAULT_ROLES:
        role = Role(
            organisation_id=org.id,
            name=template.name,
            description=template.description,
            template_key=template.key,
            is_owner=template.is_owner,
        )
        db.add(role)
        db.flush()
        if template.is_owner:
            owner_role_id = role.id
        else:
            db.add_all(RolePermission(role_id=role.id, permission=p) for p in template.permissions)

    owner = User(
        organisation_id=org.id,
        email=owner_email,
        full_name=owner_name,
        password_hash=hash_password(owner_password),
        activated_at=now,
        password_changed_at=now,
    )
    db.add(owner)
    db.flush()
    if owner_role_id is None:  # pragma: no cover - DEFAULT_ROLES always has an owner
        raise RuntimeError("Default roles must include an owner role.")
    db.add(
        UserRoleAssignment(
            organisation_id=org.id, user_id=owner.id, role_id=owner_role_id, branch_id=None
        )
    )
    branch = branches.create_branch_record(db, org.id, name=branch_name, code=branch_code)
    inspection_templates.seed_default(db, org.id)

    audit.record(
        db,
        organisation_id=org.id,
        actor_type="cli",
        action="organisation.created",
        entity_type="organisation",
        entity_id=org.id,
        summary=f"Organisation {name} created with owner {owner_email}",
        changes={"owner_user_id": owner.id, "branch_id": branch.id},
    )
    db.commit()
    return BootstrapResult(organisation=org, owner=owner)


# --------------------------------------------------------------------------- profile


def get_organisation(db: Session, principal: Principal) -> Organisation:
    return db.get_one(Organisation, principal.organisation_id)


def update_organisation(
    db: Session, principal: Principal, body: OrganisationUpdate
) -> Organisation:
    principal.require(P.SETTINGS_MANAGE)
    org = get_organisation(db, principal)
    changes = apply_changes(org, body.changes())
    if changes:
        audit.record(
            db,
            organisation_id=org.id,
            actor=principal,
            action="organisation.updated",
            entity_type="organisation",
            entity_id=org.id,
            summary="Organisation profile updated",
            changes=changes,
        )
    db.commit()
    return org


def get_settings(db: Session, principal: Principal) -> OrganisationSettings:
    return db.get_one(OrganisationSettings, principal.organisation_id)


def update_settings(
    db: Session, principal: Principal, body: SettingsUpdate
) -> OrganisationSettings:
    principal.require(P.SETTINGS_MANAGE)
    settings = get_settings(db, principal)
    changes = apply_changes(settings, body.changes())
    if changes:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            actor=principal,
            action="organisation.settings_updated",
            entity_type="organisation",
            entity_id=principal.organisation_id,
            summary="Organisation preferences updated",
            changes=changes,
        )
    db.commit()
    return settings


# --------------------------------------------------------------------------- tax rates


def list_tax_rates(db: Session, principal: Principal) -> list[TaxRate]:
    # People preparing quotations need to pick a rate; editing rates still needs settings.manage.
    if not (principal.can(P.SETTINGS_VIEW) or principal.can_in_any_branch(P.QUOTATIONS_MANAGE)):
        raise PermissionDeniedError("You do not have permission to view tax rates.")
    return list(
        db.scalars(
            select(TaxRate)
            .where(TaxRate.organisation_id == principal.organisation_id)
            .order_by(TaxRate.is_active.desc(), TaxRate.name)
        )
    )


def _clear_default(db: Session, organisation_id: uuid.UUID, except_id: uuid.UUID | None) -> None:
    stmt = update(TaxRate).where(TaxRate.organisation_id == organisation_id, TaxRate.is_default)
    if except_id:
        stmt = stmt.where(TaxRate.id != except_id)
    db.execute(stmt.values(is_default=False))


def create_tax_rate(db: Session, principal: Principal, body: TaxRateCreate) -> TaxRate:
    principal.require(P.SETTINGS_MANAGE)
    if body.is_default:
        _clear_default(db, principal.organisation_id, None)
    rate = TaxRate(organisation_id=principal.organisation_id, **body.model_dump())
    db.add(rate)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A tax rate with this name already exists.") from exc
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="tax_rate.created",
        entity_type="tax_rate",
        entity_id=rate.id,
        summary=f"Tax rate {rate.name} ({rate.rate_percent}%) created",
        changes=body.model_dump(),
    )
    db.commit()
    return rate


def update_tax_rate(
    db: Session, principal: Principal, tax_rate_id: uuid.UUID, body: TaxRateUpdate
) -> TaxRate:
    principal.require(P.SETTINGS_MANAGE)
    rate = get_scoped(db, TaxRate, tax_rate_id, principal.organisation_id)
    data = body.changes()
    if data.get("is_default"):
        _clear_default(db, principal.organisation_id, rate.id)
    changes = apply_changes(rate, data)
    if not rate.is_active and rate.is_default:
        rate.is_default = False
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A tax rate with this name already exists.") from exc
    if changes:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            actor=principal,
            action="tax_rate.updated",
            entity_type="tax_rate",
            entity_id=rate.id,
            summary=f"Tax rate {rate.name} updated",
            changes=changes,
        )
    db.commit()
    return rate


# --------------------------------------------------------------------------- numbering


def list_sequences(db: Session, principal: Principal) -> list[DocumentSequence]:
    principal.require(P.SETTINGS_VIEW)
    return list(
        db.scalars(
            select(DocumentSequence).where(
                DocumentSequence.organisation_id == principal.organisation_id
            )
        )
    )


def update_sequence(
    db: Session,
    principal: Principal,
    document_type: numbering.DocumentType,
    body: DocumentSequenceUpdate,
) -> DocumentSequence:
    principal.require(P.SETTINGS_MANAGE)
    seq = db.scalar(
        select(DocumentSequence)
        .where(
            DocumentSequence.organisation_id == principal.organisation_id,
            DocumentSequence.document_type == document_type.value,
        )
        .with_for_update()
    )
    if seq is None:
        raise NotFoundError("Numbering sequence not found.")
    data = body.changes()
    if "next_number" in data and data["next_number"] < seq.next_number:
        # Lowering the counter could re-issue numbers already printed on documents.
        raise ConflictError(
            f"Next number cannot be lower than the current value ({seq.next_number}).",
            details={"current_next_number": seq.next_number},
        )
    changes = apply_changes(seq, data)
    if changes:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            actor=principal,
            action="document_sequence.updated",
            entity_type="document_sequence",
            entity_id=None,
            summary=f"Numbering for {numbering.DOCUMENT_TYPE_LABELS[document_type]} updated",
            changes={"document_type": document_type.value, **changes},
        )
    db.commit()
    return seq
