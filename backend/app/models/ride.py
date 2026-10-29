from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import GroupStatus, MatchStatus, RequestStatus, RideStatus, TripStatus


class PassengerRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "passenger_requests"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_lng: Mapped[float] = mapped_column(Float)
    origin_address: Mapped[str] = mapped_column(String(300))
    destination_lat: Mapped[float] = mapped_column(Float)
    destination_lng: Mapped[float] = mapped_column(Float)
    destination_address: Mapped[str] = mapped_column(String(300))
    origin_area: Mapped[str] = mapped_column(String(80), default="")  # privacy-safe label
    destination_area: Mapped[str] = mapped_column(String(80), default="")
    preferred_departure: Mapped[datetime] = mapped_column(DateTime, index=True)
    earliest_departure: Mapped[datetime] = mapped_column(DateTime)
    latest_departure: Mapped[datetime] = mapped_column(DateTime)
    passenger_count: Mapped[int] = mapped_column(Integer, default=1)
    luggage_count: Mapped[int] = mapped_column(Integer, default=0)
    accessibility_needs: Mapped[str | None] = mapped_column(String(200))
    max_pickup_deviation_min: Mapped[int] = mapped_column(Integer, default=10)
    maximum_detour_minutes: Mapped[int] = mapped_column(Integer, default=25)
    ride_type: Mapped[str] = mapped_column(String(20), default="shared")  # shared | request
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=RequestStatus.SEARCHING, index=True)
    estimated_direct_distance: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_direct_duration: Mapped[float] = mapped_column(Float, default=0.0)
    route_polyline: Mapped[str] = mapped_column(Text, default="")
    ride_group_id: Mapped[int | None] = mapped_column(ForeignKey("ride_groups.id"))
    recurring_request_id: Mapped[int | None] = mapped_column(ForeignKey("recurring_requests.id"))


class DriverTripPost(IdMixin, TimestampMixin, Base):
    __tablename__ = "driver_trip_posts"
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_lng: Mapped[float] = mapped_column(Float)
    origin_address: Mapped[str] = mapped_column(String(300))
    destination_lat: Mapped[float] = mapped_column(Float)
    destination_lng: Mapped[float] = mapped_column(Float)
    destination_address: Mapped[str] = mapped_column(String(300))
    departure_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    available_seats: Mapped[int] = mapped_column(Integer)
    maximum_detour_minutes: Mapped[int] = mapped_column(Integer, default=15)
    minimum_earnings: Mapped[float] = mapped_column(Float, default=0.0)
    auto_match: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_route_note: Mapped[str | None] = mapped_column(String(200))
    route_polyline: Mapped[str] = mapped_column(Text, default="")
    estimated_distance: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_duration: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default=TripStatus.OPEN, index=True)
    recurring_request_id: Mapped[int | None] = mapped_column(ForeignKey("recurring_requests.id"))
    driver = relationship("Driver")
    vehicle = relationship("Vehicle")


class RideGroup(IdMixin, TimestampMixin, Base):
    __tablename__ = "ride_groups"
    status: Mapped[str] = mapped_column(String(20), default=GroupStatus.FORMING, index=True)
    origin_area: Mapped[str] = mapped_column(String(80), default="")
    destination_area: Mapped[str] = mapped_column(String(80), default="")
    window_start: Mapped[datetime] = mapped_column(DateTime)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    suggested_departure: Mapped[datetime] = mapped_column(DateTime, index=True)
    seats_used: Mapped[int] = mapped_column(Integer, default=0)
    seats_total: Mapped[int] = mapped_column(Integer, default=4)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_total: Mapped[float] = mapped_column(Float, default=0.0)
    fare_low: Mapped[float] = mapped_column(Float, default=0.0)
    fare_high: Mapped[float] = mapped_column(Float, default=0.0)
    plan: Mapped[dict | None] = mapped_column(JSON)
    members: Mapped[list["RideGroupMember"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class RideGroupMember(IdMixin, TimestampMixin, Base):
    __tablename__ = "ride_group_members"
    group_id: Mapped[int] = mapped_column(ForeignKey("ride_groups.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("passenger_requests.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | left
    fare_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    benchmark_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    detour_min: Mapped[float] = mapped_column(Float, default=0.0)
    pickup_order: Mapped[int | None] = mapped_column(Integer)
    dropoff_order: Mapped[int | None] = mapped_column(Integer)
    group: Mapped[RideGroup] = relationship(back_populates="members")
    request: Mapped[PassengerRequest] = relationship()


class Match(IdMixin, TimestampMixin, Base):
    """A proposal: this driver trip can serve this ride group, at this price, with this route."""

    __tablename__ = "matches"
    ride_group_id: Mapped[int | None] = mapped_column(ForeignKey("ride_groups.id", ondelete="CASCADE"), index=True)
    driver_trip_id: Mapped[int] = mapped_column(ForeignKey("driver_trip_posts.id"), index=True)
    source: Mapped[str] = mapped_column(String(20), default="group")  # group | driver_combo
    status: Mapped[str] = mapped_column(String(20), default=MatchStatus.PROPOSED, index=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    scores: Mapped[dict | None] = mapped_column(JSON)
    total_fare: Mapped[float] = mapped_column(Float, default=0.0)
    platform_fee: Mapped[float] = mapped_column(Float, default=0.0)
    driver_payout: Mapped[float] = mapped_column(Float, default=0.0)
    driver_net_earnings: Mapped[float] = mapped_column(Float, default=0.0)
    added_km: Mapped[float] = mapped_column(Float, default=0.0)
    added_min: Mapped[float] = mapped_column(Float, default=0.0)
    total_km: Mapped[float] = mapped_column(Float, default=0.0)
    total_min: Mapped[float] = mapped_column(Float, default=0.0)
    plan: Mapped[dict | None] = mapped_column(JSON)  # stops, per-passenger fares, cost breakdown
    group: Mapped[RideGroup | None] = relationship()
    trip: Mapped[DriverTripPost] = relationship()


class Ride(IdMixin, TimestampMixin, Base):
    __tablename__ = "rides"
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"))
    ride_group_id: Mapped[int | None] = mapped_column(ForeignKey("ride_groups.id"))
    driver_trip_id: Mapped[int | None] = mapped_column(ForeignKey("driver_trip_posts.id"))
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    status: Mapped[str] = mapped_column(String(20), default=RideStatus.CONFIRMED, index=True)
    scheduled_departure: Mapped[datetime] = mapped_column(DateTime, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_by: Mapped[int | None] = mapped_column(Integer)
    total_fare: Mapped[float] = mapped_column(Float, default=0.0)
    platform_fee: Mapped[float] = mapped_column(Float, default=0.0)
    driver_payout: Mapped[float] = mapped_column(Float, default=0.0)
    total_km: Mapped[float] = mapped_column(Float, default=0.0)
    total_min: Mapped[float] = mapped_column(Float, default=0.0)
    route_polyline: Mapped[str] = mapped_column(Text, default="")
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    driver = relationship("Driver")
    vehicle = relationship("Vehicle")
    stops: Mapped[list["RideStop"]] = relationship(back_populates="ride", cascade="all, delete-orphan", order_by="RideStop.sequence")
    passengers: Mapped[list["RidePassenger"]] = relationship(back_populates="ride", cascade="all, delete-orphan")


class RidePassenger(IdMixin, TimestampMixin, Base):
    __tablename__ = "ride_passengers"
    ride_id: Mapped[int] = mapped_column(ForeignKey("rides.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("passenger_requests.id"))
    fare: Mapped[float] = mapped_column(Float, default=0.0)
    platform_fee: Mapped[float] = mapped_column(Float, default=0.0)
    benchmark: Mapped[float] = mapped_column(Float, default=0.0)
    fare_breakdown: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")  # confirmed | cancelled | completed
    ride: Mapped[Ride] = relationship(back_populates="passengers")


class RideStop(IdMixin, TimestampMixin, Base):
    __tablename__ = "ride_stops"
    ride_id: Mapped[int] = mapped_column(ForeignKey("rides.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[int | None] = mapped_column(ForeignKey("passenger_requests.id"))
    kind: Mapped[str] = mapped_column(String(10))  # pickup | dropoff
    sequence: Mapped[int] = mapped_column(Integer)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    address: Mapped[str] = mapped_column(String(300), default="")
    area: Mapped[str] = mapped_column(String(80), default="")
    eta: Mapped[datetime | None] = mapped_column(DateTime)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime)
    ride: Mapped[Ride] = relationship(back_populates="stops")


class RecurringRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "recurring_requests"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="passenger")  # passenger | driver
    days_of_week: Mapped[str] = mapped_column(String(20))  # "0,2,4" (Mon=0)
    time_of_day: Mapped[str] = mapped_column(String(5))  # "08:00"
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    template: Mapped[dict] = mapped_column(JSON)  # the request / trip fields to replay
    last_generated_for: Mapped[datetime | None] = mapped_column(DateTime)
