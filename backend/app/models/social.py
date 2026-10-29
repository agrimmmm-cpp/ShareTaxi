from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import PaymentStatus


class Payment(IdMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    ride_id: Mapped[int] = mapped_column(ForeignKey("rides.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    platform_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    cancellation_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="cad")
    status: Mapped[str] = mapped_column(String(30), default=PaymentStatus.REQUIRES_CONFIRMATION, index=True)
    provider: Mapped[str] = mapped_column(String(20), default="fake")
    provider_ref: Mapped[str | None] = mapped_column(String(120))
    client_secret: Mapped[str | None] = mapped_column(String(200))
    refunded_cents: Mapped[int] = mapped_column(Integer, default=0)


class DriverPayout(IdMixin, TimestampMixin, Base):
    __tablename__ = "driver_payouts"
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    ride_id: Mapped[int] = mapped_column(ForeignKey("rides.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | paid | failed
    provider_ref: Mapped[str | None] = mapped_column(String(120))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)


class Rating(IdMixin, TimestampMixin, Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("ride_id", "rater_id", "ratee_id"),)
    ride_id: Mapped[int] = mapped_column(ForeignKey("rides.id"), index=True)
    rater_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ratee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    overall: Mapped[int] = mapped_column(Integer)
    communication: Mapped[int | None] = mapped_column(Integer)
    punctuality: Mapped[int | None] = mapped_column(Integer)
    safety: Mapped[int | None] = mapped_column(Integer)  # driving quality (driver only)
    comment: Mapped[str | None] = mapped_column(Text)


class Message(IdMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    ride_id: Mapped[int] = mapped_column(ForeignKey("rides.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(10), default="text")  # text | quick | system


class Notification(IdMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)


class Report(IdMixin, TimestampMixin, Base):
    __tablename__ = "reports"
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reported_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    ride_id: Mapped[int | None] = mapped_column(ForeignKey("rides.id"))
    category: Mapped[str] = mapped_column(String(40))  # safety | conduct | payment | other | sos
    details: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    is_sos: Mapped[bool] = mapped_column(Boolean, default=False)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    resolution: Mapped[str | None] = mapped_column(Text)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
