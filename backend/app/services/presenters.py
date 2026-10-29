"""Turns DB rows into API shapes while enforcing passenger privacy.

Rules: exact addresses/coordinates are shown only to the person they belong to (and to the driver once a
ride is confirmed). Everyone else sees a neighbourhood label and coordinates snapped to a ~1 km grid.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Driver, DriverTripPost, Match, PassengerRequest, Profile, Ride, RideGroup, RideStop, User, Rating,
)
from app.schemas.rides import (
    CostLine, DriverPublic, FareBreakdown, GroupMemberPublic, MatchOut, RideGroupOut, RideOut, RidePassengerOut,
    RideRequestOut, SearchSummary, StopOut, VehicleOut,
)
from app.services import matching_service as ms
from app.services import pricing_service as pricing
from app.services.route_service import approximate_area
from app.utils.geo import Point

STAGE = {
    "searching": "Searching for riders", "group_found": "Potential group found", "driver_search": "Driver search started",
    "driver_found": "Driver found", "confirmed": "Ride confirmed", "driver_arriving": "Driver arriving",
    "active": "Ride active", "completed": "Completed", "cancelled": "Cancelled", "expired": "Expired",
}


def fuzz(lat: float, lng: float) -> tuple[float, float]:
    return round(lat, 2), round(lng, 2)


def _first_name(db: Session, user_id: int) -> str:
    p = db.query(Profile).filter(Profile.user_id == user_id).first()
    return p.full_name.split()[0] if p else "Rider"


def serialize_request(db: Session, r: PassengerRequest, summary: SearchSummary | None = None, ride_id: int | None = None) -> RideRequestOut:
    out = RideRequestOut.model_validate(r)
    out.search = summary
    out.ride_id = ride_id
    return out


def request_summary(db: Session, r: PassengerRequest, potential: int = 0) -> SearchSummary:
    pcfg = get_settings().pricing
    group = db.get(RideGroup, r.ride_group_id) if r.ride_group_id else None
    member = next((m for m in group.members if m.request_id == r.id), None) if group else None
    bench = pricing.estimate_market_benchmark(r.estimated_direct_distance, r.estimated_direct_duration, pcfg) * r.passenger_count
    fare = member.fare_estimate if member and group and group.seats_used > 1 else None
    lo, hi = pricing.fare_range(fare, pcfg) if fare else (None, None)
    return SearchSummary(
        potential_matches=potential, likely_passengers=group.seats_used if group else r.passenger_count,
        group_id=group.id if group else None, seats_used=group.seats_used if group else r.passenger_count,
        estimated_fare=fare, fare_low=lo, fare_high=hi, solo_benchmark=round(bench, 2),
        estimated_savings=round(bench - fare, 2) if fare else None,
        savings_percent=round(100 * (bench - fare) / bench, 1) if fare and bench else None,
        departure_from=group.window_start if group else r.earliest_departure,
        departure_to=group.window_end if group else r.latest_departure,
        estimated_duration_min=round(r.estimated_direct_duration, 0), stage=STAGE.get(r.status, r.status),
    )


def serialize_group(db: Session, g: RideGroup, viewer: User | None) -> RideGroupOut:
    members, you_fare, bench = [], None, None
    active = [m for m in g.members if m.status == "active"]
    for i, m in enumerate(active, start=1):
        you = viewer is not None and m.user_id == viewer.id
        members.append(GroupMemberPublic(label="You" if you else f"Passenger {i}", is_you=you,
                                         area=approximate_area(Point(m.request.origin_lat, m.request.origin_lng)),
                                         seats=m.request.passenger_count))
        if you:
            you_fare, bench = m.fare_estimate or None, m.benchmark_estimate or None
    seats_left = max(0, g.seats_total - g.seats_used)
    status_label = "Ride confirmed" if g.status == "confirmed" else ("Finding a driver…" if g.status == "driver_search" else "Shared ride forming")
    return RideGroupOut(
        id=g.id, status=g.status, headline=f"{g.origin_area} → {g.destination_area}", origin_area=g.origin_area,
        destination_area=g.destination_area, suggested_departure=g.suggested_departure, window_start=g.window_start,
        window_end=g.window_end, seats_used=g.seats_used, seats_total=g.seats_total, seats_left=seats_left, members=members,
        fare_low=g.fare_low, fare_high=g.fare_high, your_fare=you_fare, solo_benchmark=bench,
        your_savings=round(bench - you_fare, 2) if you_fare and bench else None, stage=status_label,
    )


def serialize_match(db: Session, m: Match, viewer: User, *, as_driver: bool) -> MatchOut:
    plan = m.plan or {}
    ids = plan.get("request_ids", [])
    labels: dict[int, str] = {}
    for s in plan.get("stops", []):
        labels.setdefault(s["request_id"], f"Passenger {len(labels) + 1}")
    stops: list[StopOut] = []
    for s in plan.get("stops", []):
        mine = (not as_driver) and s["user_id"] == viewer.id
        lat, lng = (s["lat"], s["lng"]) if mine else fuzz(s["lat"], s["lng"])
        stops.append(StopOut(order=s["order"], kind=s["kind"], label="You" if mine else labels[s["request_id"]],
                             area=approximate_area(Point(s["lat"], s["lng"])), lat=lat, lng=lng,
                             eta=datetime.fromisoformat(s["eta"]) if s.get("eta") else None))
    mine_fare = None
    if not as_driver:
        req_id = next((s["request_id"] for s in plan.get("stops", []) if s["user_id"] == viewer.id), None)
        mine_fare = plan.get("fares", {}).get(str(req_id)) if req_id else None
    trip = m.trip
    return MatchOut(
        id=m.id, status=m.status, source=m.source, trip_id=m.driver_trip_id, group_id=m.ride_group_id, overall_score=m.overall_score,
        scores=m.scores or {}, passengers=len(ids), seats_used=sum(1 for _ in ids), seats_total=trip.available_seats,
        total_fare=m.total_fare, platform_fee=m.platform_fee, driver_payout=m.driver_payout if as_driver else 0.0,
        driver_net_earnings=m.driver_net_earnings if as_driver else 0.0,
        operating_cost=plan.get("cost", {}).get("operating_cost", 0.0) if as_driver else 0.0,
        added_km=m.added_km, added_min=m.added_min, total_km=m.total_km, total_min=m.total_min, stops=stops,
        route_polyline=plan.get("route_polyline", ""), direct_polyline=trip.route_polyline,
        cost_lines=[CostLine(**l) for l in plan.get("cost", {}).get("lines", [])] if as_driver else [],
        your_fare=mine_fare["fare"] if mine_fare else None, your_savings=mine_fare["savings"] if mine_fare else None,
        your_savings_percent=mine_fare["savings_percent"] if mine_fare else None,
        solo_benchmark=mine_fare["benchmark"] if mine_fare else None, departure=trip.departure_time, created_at=m.created_at,
    )


def serialize_ride(db: Session, ride: Ride, viewer: User) -> RideOut:
    driver: Driver = db.get(Driver, ride.driver_id)
    dprofile = db.query(Profile).filter(Profile.user_id == driver.user_id).one()
    is_driver = driver.user_id == viewer.id
    me = next((p for p in ride.passengers if p.user_id == viewer.id), None)
    if not (is_driver or me or viewer.is_admin):
        raise PermissionError
    labels: dict[int, str] = {}
    pax = []
    for i, p in enumerate([p for p in ride.passengers if p.status != "cancelled"], start=1):
        you = p.user_id == viewer.id
        labels[p.user_id] = "You" if you else f"Passenger {i}"
        prof = db.query(Profile).filter(Profile.user_id == p.user_id).one()
        first_stop = next(s for s in ride.stops if s.user_id == p.user_id and s.kind == "pickup")
        pax.append(RidePassengerOut(user_id=p.user_id, label=labels[p.user_id], is_you=you, first_name=prof.full_name.split()[0],
                                    area=first_stop.area, rating=prof.rating_avg or None))
    stops = []
    for s in ride.stops:
        if s.user_id not in labels:
            continue
        exact = is_driver or s.user_id == viewer.id
        lat, lng = (s.lat, s.lng) if exact else fuzz(s.lat, s.lng)
        stops.append(StopOut(order=s.sequence, kind=s.kind, label=labels[s.user_id], area=s.area,
                             lat=lat, lng=lng, eta=s.eta, address=s.address if exact else None))
    fare = None
    my_pickup = my_drop = None
    if me:
        f = me.fare_breakdown or {}
        fare = FareBreakdown(fare=me.fare, platform_fee=me.platform_fee, distance_part=f.get("distance_part", 0), time_part=f.get("time_part", 0),
                             detour_part=f.get("detour_part", 0), solo_benchmark=me.benchmark, savings=round(me.benchmark - me.fare, 2),
                             savings_percent=round(100 * (me.benchmark - me.fare) / me.benchmark, 1) if me.benchmark else 0.0)
        my_pickup = next((s.eta for s in ride.stops if s.user_id == viewer.id and s.kind == "pickup"), None)
        my_drop = next((s.eta for s in ride.stops if s.user_id == viewer.id and s.kind == "dropoff"), None)
    first, last = ride.stops[0], ride.stops[-1]
    already_rated = db.query(Rating).filter(Rating.ride_id == ride.id, Rating.rater_id == viewer.id).count() > 0
    return RideOut(
        id=ride.id, status=ride.status, scheduled_departure=ride.scheduled_departure, started_at=ride.started_at,
        completed_at=ride.completed_at, headline=f"{first.area} → {last.area}",
        driver=DriverPublic(user_id=driver.user_id, name=dprofile.full_name.split()[0], rating=dprofile.rating_avg, rating_count=dprofile.rating_count,
                            trips_completed=driver.trips_completed, vehicle=VehicleOut.model_validate(ride.vehicle)),
        passengers=pax, passenger_count=len(pax), stops=stops, route_polyline=ride.route_polyline, total_km=ride.total_km,
        total_min=ride.total_min, your_fare=fare, total_fare=ride.total_fare if is_driver else None,
        driver_payout=ride.driver_payout if is_driver else None, your_pickup_eta=my_pickup, your_dropoff_eta=my_drop,
        share_token=ride.share_token if (me or is_driver) else None, is_driver=is_driver,
        can_rate=ride.status == "completed" and not already_rated,
    )
