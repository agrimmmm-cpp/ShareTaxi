from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------- passenger requests
class RideRequestIn(BaseModel):
    origin_address: str = Field(min_length=2, max_length=300)
    origin_lat: float | None = Field(default=None, ge=-90, le=90)
    origin_lng: float | None = Field(default=None, ge=-180, le=180)
    destination_address: str = Field(min_length=2, max_length=300)
    destination_lat: float | None = Field(default=None, ge=-90, le=90)
    destination_lng: float | None = Field(default=None, ge=-180, le=180)
    preferred_departure: datetime
    flexible_minutes: int = Field(default=30, ge=0, le=180)
    passenger_count: int = Field(default=1, ge=1, le=4)
    luggage_count: int = Field(default=0, ge=0, le=10)
    accessibility_needs: str | None = Field(default=None, max_length=200)
    max_pickup_deviation_min: int = Field(default=10, ge=0, le=60)
    maximum_detour_minutes: int = Field(default=25, ge=0, le=90)
    ride_type: str = Field(default="shared", pattern="^(shared|request)$")
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _coords_in_pairs(self):
        for a, b in (("origin_lat", "origin_lng"), ("destination_lat", "destination_lng")):
            if (getattr(self, a) is None) != (getattr(self, b) is None):
                raise ValueError(f"{a} and {b} must be provided together")
        return self


class RideRequestUpdate(BaseModel):
    preferred_departure: datetime | None = None
    flexible_minutes: int | None = Field(default=None, ge=0, le=180)
    passenger_count: int | None = Field(default=None, ge=1, le=4)
    maximum_detour_minutes: int | None = Field(default=None, ge=0, le=90)
    notes: str | None = Field(default=None, max_length=500)


class Money(BaseModel):
    amount: float
    currency: str = "CAD"


class SearchSummary(BaseModel):
    """What the passenger sees right after posting."""

    potential_matches: int
    likely_passengers: int
    group_id: int | None
    seats_used: int
    estimated_fare: float | None
    fare_low: float | None
    fare_high: float | None
    solo_benchmark: float
    estimated_savings: float | None
    savings_percent: float | None
    departure_from: datetime | None
    departure_to: datetime | None
    estimated_duration_min: float
    stage: str  # human-readable state label


class RideRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    origin_address: str
    destination_address: str
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    preferred_departure: datetime
    earliest_departure: datetime
    latest_departure: datetime
    passenger_count: int
    luggage_count: int
    accessibility_needs: str | None
    maximum_detour_minutes: int
    max_pickup_deviation_min: int
    ride_type: str
    notes: str | None
    estimated_direct_distance: float
    estimated_direct_duration: float
    route_polyline: str
    ride_group_id: int | None
    created_at: datetime
    search: SearchSummary | None = None
    ride_id: int | None = None


# ---------------------------------------------------------------- groups
class GroupMemberPublic(BaseModel):
    label: str  # "You", "Passenger 2"
    is_you: bool
    area: str  # approximate pickup area, never an address
    seats: int
    confirmed: bool = True


class RideGroupOut(BaseModel):
    id: int
    status: str
    headline: str  # "Burnaby → Abbotsford"
    origin_area: str
    destination_area: str
    suggested_departure: datetime
    window_start: datetime
    window_end: datetime
    seats_used: int
    seats_total: int
    seats_left: int
    members: list[GroupMemberPublic]
    fare_low: float
    fare_high: float
    your_fare: float | None
    solo_benchmark: float | None
    your_savings: float | None
    stage: str


# ---------------------------------------------------------------- driver trips
class DriverTripIn(BaseModel):
    vehicle_id: int
    origin_address: str = Field(min_length=2, max_length=300)
    origin_lat: float | None = Field(default=None, ge=-90, le=90)
    origin_lng: float | None = Field(default=None, ge=-180, le=180)
    destination_address: str = Field(min_length=2, max_length=300)
    destination_lat: float | None = Field(default=None, ge=-90, le=90)
    destination_lng: float | None = Field(default=None, ge=-180, le=180)
    departure_time: datetime
    available_seats: int = Field(ge=1, le=7)
    maximum_detour_minutes: int = Field(default=30, ge=0, le=90)
    minimum_earnings: float = Field(default=0.0, ge=0, le=2000)
    auto_match: bool = True
    preferred_route_note: str | None = Field(default=None, max_length=200)


class DriverTripUpdate(BaseModel):
    available_seats: int | None = Field(default=None, ge=1, le=7)
    maximum_detour_minutes: int | None = Field(default=None, ge=0, le=90)
    minimum_earnings: float | None = Field(default=None, ge=0, le=2000)
    auto_match: bool | None = None
    status: str | None = Field(default=None, pattern="^cancelled$")
    departure_time: datetime | None = None


class DriverTripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    vehicle_id: int
    origin_address: str
    destination_address: str
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    departure_time: datetime
    available_seats: int
    maximum_detour_minutes: int
    minimum_earnings: float
    auto_match: bool
    estimated_distance: float
    estimated_duration: float
    route_polyline: str
    created_at: datetime
    recommendations: int | None = None
    ride_id: int | None = None


# ---------------------------------------------------------------- matches
class StopOut(BaseModel):
    order: int
    kind: str
    label: str  # "Passenger 1"
    area: str
    lat: float
    lng: float
    eta: datetime | None = None
    address: str | None = None  # only revealed once confirmed and only to those who need it


class CostLine(BaseModel):
    label: str
    amount: float


class MatchOut(BaseModel):
    id: int
    status: str
    source: str
    trip_id: int
    group_id: int | None
    overall_score: float
    scores: dict[str, float]
    passengers: int
    seats_used: int
    seats_total: int
    total_fare: float
    platform_fee: float
    driver_payout: float
    driver_net_earnings: float
    operating_cost: float
    added_km: float
    added_min: float
    total_km: float
    total_min: float
    stops: list[StopOut]
    route_polyline: str
    direct_polyline: str
    cost_lines: list[CostLine]
    # passenger-facing
    your_fare: float | None = None
    your_savings: float | None = None
    your_savings_percent: float | None = None
    solo_benchmark: float | None = None
    departure: datetime
    created_at: datetime


# ---------------------------------------------------------------- rides
class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    make: str
    model: str
    year: int
    color: str
    license_plate: str
    seats: int


class DriverPublic(BaseModel):
    user_id: int
    name: str
    rating: float
    rating_count: int
    trips_completed: int
    vehicle: VehicleOut


class RidePassengerOut(BaseModel):
    user_id: int
    label: str
    is_you: bool
    first_name: str | None
    area: str
    rating: float | None = None


class FareBreakdown(BaseModel):
    fare: float
    platform_fee: float
    distance_part: float
    time_part: float
    detour_part: float
    solo_benchmark: float
    savings: float
    savings_percent: float


class RideOut(BaseModel):
    id: int
    status: str
    scheduled_departure: datetime
    started_at: datetime | None
    completed_at: datetime | None
    headline: str
    driver: DriverPublic
    passengers: list[RidePassengerOut]
    passenger_count: int
    stops: list[StopOut]
    route_polyline: str
    total_km: float
    total_min: float
    your_fare: FareBreakdown | None
    total_fare: float | None  # driver view
    driver_payout: float | None
    your_pickup_eta: datetime | None
    your_dropoff_eta: datetime | None
    chat_enabled: bool = True
    share_token: str | None = None
    is_driver: bool = False
    can_rate: bool = False


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)
