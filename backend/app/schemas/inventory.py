import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.schemas.common import OptionalStr, Schema, UpdateSchema
from app.schemas.job_card import Ref

Unit = Literal["each", "pair", "set", "box", "litre", "kg", "metre"]
WHOLE_UNITS = frozenset({"each", "pair", "set", "box"})
MovementKind = Literal[
    "opening",
    "adjustment",
    "transfer_out",
    "transfer_in",
    "receipt",
    "issue",
    "return",
    "supplier_return",
]
Sku = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._/\-]*$",
    ),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
Price = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
SignedQuantity = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
CountedQuantity = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


# --------------------------------------------------------------------------- catalogue


class CategoryInput(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CategoryRead(BaseModel):
    id: uuid.UUID
    name: str
    archived_at: datetime | None
    part_count: int


class PartCreate(Schema):
    sku: Sku
    name: Name
    description: OptionalStr = Field(None, max_length=2000)
    category_id: uuid.UUID | None = None
    unit: Unit = "each"
    manufacturer: OptionalStr = Field(None, max_length=100)
    manufacturer_part_number: OptionalStr = Field(None, max_length=100)
    cost_price: Price = Decimal("0")
    selling_price: Price = Decimal("0")
    tax_rate_id: uuid.UUID | None = None


class PartUpdate(UpdateSchema):
    non_nullable: ClassVar[frozenset[str]] = frozenset(
        {"sku", "name", "unit", "cost_price", "selling_price"}
    )

    sku: Sku | None = None
    name: Name | None = None
    description: OptionalStr = Field(None, max_length=2000)
    category_id: uuid.UUID | None = None
    unit: Unit | None = None
    manufacturer: OptionalStr = Field(None, max_length=100)
    manufacturer_part_number: OptionalStr = Field(None, max_length=100)
    cost_price: Price | None = None
    selling_price: Price | None = None
    tax_rate_id: uuid.UUID | None = None


class StockSummary(BaseModel):
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    low_locations: int


class PartListItem(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    category: Ref | None
    unit: Unit
    manufacturer_part_number: str | None
    selling_price: Decimal
    # Hidden (null) unless the caller manages the catalogue or adjusts stock.
    cost_price: Decimal | None
    archived_at: datetime | None
    stock: StockSummary


class LevelRead(BaseModel):
    location: Ref
    branch: Ref
    on_hand: Decimal
    reserved: Decimal
    available: Decimal
    min_quantity: Decimal | None
    is_low: bool
    can_adjust: bool
    can_transfer: bool


class PartCapabilities(BaseModel):
    edit: bool
    archive: bool


class PartRead(PartListItem):
    description: str | None
    manufacturer: str | None
    tax_rate: Ref | None
    created_at: datetime
    updated_at: datetime
    levels: list[LevelRead]
    capabilities: PartCapabilities


# --------------------------------------------------------------------------- locations


class LocationCreate(Schema):
    branch_id: uuid.UUID
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class LocationUpdate(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class LocationRead(BaseModel):
    id: uuid.UUID
    name: str
    branch: Ref
    is_default: bool
    archived_at: datetime | None
    part_count: int
    units_on_hand: Decimal


class MinLevelUpdate(Schema):
    min_quantity: CountedQuantity | None = Field(
        None, description="Alert when available stock is at or below this. Null disables."
    )


# --------------------------------------------------------------------------- operations


class AdjustmentLine(Schema):
    part_id: uuid.UUID
    counted: CountedQuantity | None = Field(
        None, description="Stocktake: the quantity physically counted. The change is derived."
    )
    change: SignedQuantity | None = Field(
        None, description="Direct correction: positive adds stock, negative removes it."
    )

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.counted is None) == (self.change is None):
            raise ValueError("Give either 'counted' or 'change'.")
        if self.change is not None and self.change == 0:
            raise ValueError("The change cannot be zero.")
        return self


class AdjustmentCreate(Schema):
    location_id: uuid.UUID
    reason: Reason
    lines: list[AdjustmentLine] = Field(min_length=1, max_length=200)


class TransferLine(Schema):
    part_id: uuid.UUID
    quantity: Quantity


class TransferCreate(Schema):
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    reason: OptionalStr = Field(None, max_length=500)
    lines: list[TransferLine] = Field(min_length=1, max_length=200)


class MovementRead(BaseModel):
    id: uuid.UUID
    operation_id: uuid.UUID
    kind: MovementKind
    part: Ref
    sku: str
    location: Ref
    branch: Ref
    quantity: Decimal
    balance_after: Decimal | None
    unit_cost: Decimal | None  # hidden unless the caller may see costs
    job_card: Ref | None
    reason: str | None
    reference: str | None
    created_by: str
    created_at: datetime


class OperationRead(BaseModel):
    id: uuid.UUID
    kind: str
    reason: str | None
    created_at: datetime
    movements: list[MovementRead]
    # Lines whose counted quantity already matched; nothing was recorded for them.
    unchanged_part_ids: list[uuid.UUID] = []
