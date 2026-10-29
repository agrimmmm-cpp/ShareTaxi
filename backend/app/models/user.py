from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import VerificationStatus


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    oauth_provider: Mapped[str | None] = mapped_column(String(32))
    oauth_subject: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    profile: Mapped["Profile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    driver: Mapped["Driver | None"] = relationship(back_populates="user", uselist=False)

    @property
    def is_driver(self) -> bool:
        return self.driver is not None and self.driver.verification_status == VerificationStatus.APPROVED

    @property
    def roles(self) -> list[str]:
        out = ["passenger"]
        if self.is_driver:
            out.append("driver")
        if self.is_admin:
            out.append("admin")
        return out


class Profile(IdMixin, TimestampMixin, Base):
    __tablename__ = "profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    push_token: Mapped[str | None] = mapped_column(String(255))
    rating_avg: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    cancellation_count: Mapped[int] = mapped_column(Integer, default=0)
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User] = relationship(back_populates="profile")


class Driver(IdMixin, TimestampMixin, Base):
    __tablename__ = "drivers"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    verification_status: Mapped[str] = mapped_column(String(20), default=VerificationStatus.UNSUBMITTED)
    stripe_account_id: Mapped[str | None] = mapped_column(String(120))
    trips_completed: Mapped[int] = mapped_column(Integer, default=0)
    trips_cancelled: Mapped[int] = mapped_column(Integer, default=0)
    user: Mapped[User] = relationship(back_populates="driver")
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="driver", cascade="all, delete-orphan")
    documents: Mapped[list["DriverDocument"]] = relationship(back_populates="driver", cascade="all, delete-orphan")

    @property
    def cancellation_rate(self) -> float:
        total = self.trips_completed + self.trips_cancelled
        return round(self.trips_cancelled / total, 3) if total else 0.0


class Vehicle(IdMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), index=True)
    make: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(60))
    year: Mapped[int] = mapped_column(Integer)
    color: Mapped[str] = mapped_column(String(30))
    license_plate: Mapped[str] = mapped_column(String(20))
    seats: Mapped[int] = mapped_column(Integer, default=4)  # passenger seats
    driver: Mapped[Driver] = relationship(back_populates="vehicles")


class DriverDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "driver_documents"
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[str] = mapped_column(String(40))  # drivers_licence | vehicle_registration | insurance | identity
    file_url: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default=VerificationStatus.PENDING)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    review_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    driver: Mapped[Driver] = relationship(back_populates="documents")


class EmergencyContact(IdMixin, TimestampMixin, Base):
    __tablename__ = "emergency_contacts"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32))
    relationship_label: Mapped[str | None] = mapped_column(String(40))


class SavedLocation(IdMixin, TimestampMixin, Base):
    __tablename__ = "saved_locations"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(60))
    address: Mapped[str] = mapped_column(String(300))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)


class UserBlock(IdMixin, TimestampMixin, Base):
    __tablename__ = "user_blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id"),)
    blocker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    blocked_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class RefreshToken(IdMixin, TimestampMixin, Base):
    """Rotating refresh tokens: only the SHA-256 of the token is stored; reuse revokes the family."""

    __tablename__ = "refresh_tokens"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
