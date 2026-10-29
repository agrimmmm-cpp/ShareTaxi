from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VehicleIn(BaseModel):
    make: str = Field(max_length=60)
    model: str = Field(max_length=60)
    year: int = Field(ge=1990, le=2100)
    color: str = Field(max_length=30)
    license_plate: str = Field(max_length=20)
    seats: int = Field(default=4, ge=1, le=7)


class DriverApplyIn(BaseModel):
    vehicle: VehicleIn


class DocumentIn(BaseModel):
    doc_type: str = Field(pattern="^(drivers_licence|vehicle_registration|insurance|identity)$")
    file_url: str = Field(max_length=500)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doc_type: str
    status: str
    review_notes: str | None


class PaymentCreateIn(BaseModel):
    ride_id: int


class PaymentConfirmIn(BaseModel):
    payment_id: int


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ride_id: int
    amount_cents: int
    platform_fee_cents: int
    cancellation_fee_cents: int
    currency: str
    status: str
    provider: str
    client_secret: str | None
    refunded_cents: int
    created_at: datetime


class PayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ride_id: int
    amount_cents: int
    status: str
    created_at: datetime


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    kind: str = Field(default="text", pattern="^(text|quick)$")


class MessageOut(BaseModel):
    id: int
    ride_id: int
    sender_id: int
    sender_label: str
    body: str
    kind: str
    created_at: datetime
    mine: bool = False


class RatingIn(BaseModel):
    ride_id: int
    ratee_id: int
    overall: int = Field(ge=1, le=5)
    communication: int | None = Field(default=None, ge=1, le=5)
    punctuality: int | None = Field(default=None, ge=1, le=5)
    safety: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class RatingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ride_id: int
    overall: int
    communication: int | None
    punctuality: int | None
    safety: int | None
    comment: str | None
    created_at: datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    title: str
    body: str
    data: dict | None
    read_at: datetime | None
    created_at: datetime


class EmergencyContactIn(BaseModel):
    name: str = Field(max_length=120)
    phone: str = Field(max_length=32)
    relationship_label: str | None = Field(default=None, max_length=40)


class EmergencyContactOut(EmergencyContactIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class SavedLocationIn(BaseModel):
    label: str = Field(max_length=60)
    address: str = Field(max_length=300)
    lat: float | None = None
    lng: float | None = None


class SavedLocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str
    address: str
    lat: float
    lng: float


class ReportIn(BaseModel):
    reported_user_id: int | None = None
    ride_id: int | None = None
    category: str = Field(pattern="^(safety|conduct|payment|other)$")
    details: str = Field(default="", max_length=2000)


class SosIn(BaseModel):
    ride_id: int | None = None
    lat: float | None = None
    lng: float | None = None


class RecurringIn(BaseModel):
    kind: str = Field(default="passenger", pattern="^(passenger|driver)$")
    days_of_week: list[int] = Field(min_length=1)
    time_of_day: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    template: dict


class RecurringOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    days_of_week: str
    time_of_day: str
    active: bool
    template: dict
    last_generated_for: datetime | None


class PlatformFeeIn(BaseModel):
    platform_commission_rate: float = Field(ge=0, le=0.5)


class ResolveIn(BaseModel):
    status: str = Field(pattern="^(investigating|resolved|dismissed)$")
    resolution: str | None = None


class RefundIn(BaseModel):
    amount_cents: int | None = Field(default=None, gt=0)
