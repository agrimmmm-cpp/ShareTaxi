"""Ride lifecycle: confirmation, start, completion, cancellations (with fees) and ratings aggregation."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.db.base import utcnow
from app.models import (
    Driver, DriverTripPost, GroupStatus, Match, MatchStatus, Message, Payment, PaymentStatus, PassengerRequest, Profile,
    Rating, RequestStatus, Ride, RideGroup, RideGroupMember, RidePassenger, RideStatus, RideStop, TripStatus, User,
)
from app.repositories.rides import POOL_STATUSES
from app.services import notification_service as ns
from app.services import payment_service as pay
from app.services import pricing_service as pricing
from app.services.route_service import approximate_area
from app.services.state_machine import transition
from app.utils.geo import Point


class RideError(Exception):
    """Business-rule violation; routers translate it to HTTP 409/403."""

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


def _system_message(db: Session, ride: Ride, sender_id: int, body: str) -> None:
    db.add(Message(ride_id=ride.id, sender_id=sender_id, body=body, kind="system"))


# --------------------------------------------------------------------------- confirmation
def confirm_match(db: Session, match: Match) -> Ride:
    plan = match.plan or {}
    ids: list[int] = plan.get("request_ids", [])
    trip = match.trip
    if match.status != MatchStatus.PROPOSED:
        raise RideError("This match is no longer available")
    if trip.status != TripStatus.OPEN:
        raise RideError("This trip is no longer open")
    reqs = [db.get(PassengerRequest, i) for i in ids]
    if any(r is None or r.status not in POOL_STATUSES for r in reqs):
        raise RideError("One of the passengers is no longer available")
    if sum(r.passenger_count for r in reqs) > trip.available_seats:
        raise RideError("Not enough seats on this trip")

    group = match.group
    if group is None or {m.request_id for m in group.members if m.status == "active"} != set(ids):
        group = RideGroup(
            status=GroupStatus.CONFIRMED, origin_area=reqs[0].origin_area, destination_area=reqs[0].destination_area,
            window_start=min(r.earliest_departure for r in reqs), window_end=max(r.latest_departure for r in reqs),
            suggested_departure=trip.departure_time, seats_used=sum(r.passenger_count for r in reqs),
            seats_total=trip.available_seats,
        )
        db.add(group)
        db.flush()
        for r in reqs:
            db.add(RideGroupMember(group_id=group.id, request_id=r.id, user_id=r.user_id))
        db.flush()
    group.status = GroupStatus.CONFIRMED

    ride = Ride(
        match_id=match.id, ride_group_id=group.id, driver_trip_id=trip.id, driver_id=trip.driver_id, vehicle_id=trip.vehicle_id,
        status=RideStatus.CONFIRMED, scheduled_departure=trip.departure_time, total_fare=match.total_fare,
        platform_fee=match.platform_fee, driver_payout=match.driver_payout, total_km=match.total_km,
        total_min=match.total_min, route_polyline=plan.get("route_polyline", ""), share_token=secrets.token_urlsafe(24),
    )
    db.add(ride)
    db.flush()
    by_id = {r.id: r for r in reqs}
    for r in reqs:
        f = plan["fares"][str(r.id)]
        db.add(RidePassenger(ride_id=ride.id, user_id=r.user_id, request_id=r.id, fare=f["fare"], platform_fee=f["platform_fee"],
                             benchmark=f["benchmark"], fare_breakdown=f))
        r.ride_group_id = group.id
    for s in plan["stops"]:
        r = by_id[s["request_id"]]
        exact = (r.origin_lat, r.origin_lng, r.origin_address, r.origin_area) if s["kind"] == "pickup" else (
            r.destination_lat, r.destination_lng, r.destination_address, r.destination_area)
        db.add(RideStop(ride_id=ride.id, user_id=r.user_id, request_id=r.id, kind=s["kind"], sequence=s["order"],
                        lat=exact[0], lng=exact[1], address=exact[2], area=exact[3],
                        eta=datetime.fromisoformat(s["eta"]) if s.get("eta") else None))
    db.flush()

    match.status = MatchStatus.ACCEPTED
    transition("trip", trip, TripStatus.CONFIRMED)
    for r in reqs:
        transition("request", r, RequestStatus.CONFIRMED)
    # any other proposal touching these passengers or this trip is now void
    for m in db.query(Match).filter(Match.status == MatchStatus.PROPOSED, Match.id != match.id).all():
        if m.driver_trip_id == trip.id or set((m.plan or {}).get("request_ids", [])) & set(ids):
            db.delete(m)
    db.flush()
    pay.ensure_payment_rows(db, ride)

    driver_user = db.get(Driver, trip.driver_id).user_id
    drv_name = db.query(Profile).filter(Profile.user_id == driver_user).one().full_name.split()[0]
    for r in reqs:
        ns.notify(db, r.user_id, ns.DRIVER_ACCEPTED, "Driver accepted", f"{drv_name} will pick you up.", {"ride_id": ride.id})
        ns.notify(db, r.user_id, ns.RIDE_CONFIRMED, "Ride confirmed",
                  f"{trip.departure_time:%b %d, %H:%M} · ${plan['fares'][str(r.id)]['fare']:.2f}. Add your payment method to secure your seat.",
                  {"ride_id": ride.id})
    ns.notify(db, driver_user, ns.RIDE_CONFIRMED, "Ride confirmed", f"{len(reqs)} passengers · you earn ${match.driver_payout:.2f}", {"ride_id": ride.id})
    _system_message(db, ride, driver_user, "Ride confirmed. Say hi and share your pickup details here.")
    log_event("match.accepted", match_id=match.id, ride_id=ride.id, trip_id=trip.id, passengers=len(reqs))
    return ride


def reject_match(db: Session, match: Match) -> None:
    if match.status != MatchStatus.PROPOSED:
        raise RideError("This match is no longer pending")
    match.status = MatchStatus.REJECTED
    log_event("match.rejected", match_id=match.id, trip_id=match.driver_trip_id)


# --------------------------------------------------------------------------- lifecycle
def _requests_of(db: Session, ride: Ride) -> list[PassengerRequest]:
    return [db.get(PassengerRequest, rp.request_id) for rp in ride.passengers if rp.status != "cancelled"]


def mark_arriving(db: Session, ride: Ride) -> None:
    transition("ride", ride, RideStatus.DRIVER_ARRIVING)
    for r in _requests_of(db, ride):
        transition("request", r, RequestStatus.DRIVER_ARRIVING)
        ns.notify(db, r.user_id, ns.DRIVER_APPROACHING, "Your driver is approaching", "Head to your pickup point.", {"ride_id": ride.id})


def start_ride(db: Session, ride: Ride) -> None:
    transition("ride", ride, RideStatus.ACTIVE)
    ride.started_at = utcnow()
    transition("trip", db.get(DriverTripPost, ride.driver_trip_id), TripStatus.ACTIVE)
    for r in _requests_of(db, ride):
        transition("request", r, RequestStatus.ACTIVE)
        ns.notify(db, r.user_id, ns.RIDE_STARTED, "Ride started", "Have a safe trip!", {"ride_id": ride.id})


def complete_ride(db: Session, ride: Ride) -> None:
    transition("ride", ride, RideStatus.COMPLETED)
    ride.completed_at = utcnow()
    transition("trip", db.get(DriverTripPost, ride.driver_trip_id), TripStatus.COMPLETED)
    driver = db.get(Driver, ride.driver_id)
    driver.trips_completed += 1
    captured, payout = pay.capture_ride(db, ride)
    for rp in ride.passengers:
        if rp.status == "confirmed":
            rp.status = "completed"
    for r in _requests_of(db, ride):
        transition("request", r, RequestStatus.COMPLETED)
        ns.notify(db, r.user_id, ns.RIDE_COMPLETED, "You've arrived", "Thanks for sharing the ride.", {"ride_id": ride.id})
        ns.notify(db, r.user_id, ns.PAYMENT_RECEIPT, "Payment receipt", "Your receipt is available in Payment history.", {"ride_id": ride.id})
        ns.notify(db, r.user_id, ns.RATING_REMINDER, "How was your ride?", "Rate your driver in one tap.", {"ride_id": ride.id})
    ns.notify(db, driver.user_id, ns.RATING_REMINDER, "Rate your passengers", "Help keep ShareTaxi safe and friendly.", {"ride_id": ride.id})
    log_event("ride.completed", ride_id=ride.id, captured_cents=captured, payout_cents=payout)


def cancel_by_passenger(db: Session, ride: Ride, user: User, reason: str | None = None) -> float:
    """Returns the cancellation fee charged (dollars)."""
    rp = next((p for p in ride.passengers if p.user_id == user.id and p.status == "confirmed"), None)
    if rp is None:
        raise RideError("You are not an active passenger on this ride", 403)
    if ride.status not in (RideStatus.CONFIRMED, RideStatus.DRIVER_ARRIVING):
        raise RideError("This ride can no longer be cancelled")
    hours = (ride.scheduled_departure - utcnow()).total_seconds() / 3600
    fee = pricing.cancellation_fee(rp.fare, hours, get_settings().cancellation)
    rp.status = "cancelled"
    payment = db.query(Payment).filter(Payment.ride_id == ride.id, Payment.user_id == user.id).first()
    if payment:
        pay.void_or_charge_fee(db, payment, pay.cents(fee))
    req = db.get(PassengerRequest, rp.request_id)
    transition("request", req, RequestStatus.CANCELLED)
    profile = db.query(Profile).filter(Profile.user_id == user.id).one()
    profile.cancellation_count += 1
    group = db.get(RideGroup, ride.ride_group_id)
    member = db.query(RideGroupMember).filter(RideGroupMember.group_id == ride.ride_group_id, RideGroupMember.user_id == user.id).first()
    if member:
        member.status = "left"
    driver_user = db.get(Driver, ride.driver_id).user_id
    remaining = [p for p in ride.passengers if p.status == "confirmed"]
    if not remaining:
        ride.status, ride.cancelled_at, ride.cancelled_by = RideStatus.CANCELLED, utcnow(), user.id
        trip = db.get(DriverTripPost, ride.driver_trip_id)
        transition("trip", trip, TripStatus.OPEN)
        if group:
            group.status = GroupStatus.CANCELLED
    ns.notify(db, driver_user, ns.CANCELLATION, "A passenger cancelled",
              "Your trip is open again." if not remaining else f"{len(remaining)} passenger(s) remain.", {"ride_id": ride.id})
    log_event("ride.passenger_cancelled", ride_id=ride.id, user_id=user.id, fee=fee, reason=reason)
    return fee


def cancel_by_driver(db: Session, ride: Ride, driver: Driver, reason: str | None = None) -> None:
    """Driver cancels: ride dies, passengers go back into the pool so the engine finds them another driver."""
    if ride.driver_id != driver.id:
        raise RideError("Not your ride", 403)
    if ride.status not in (RideStatus.CONFIRMED, RideStatus.DRIVER_ARRIVING):
        raise RideError("This ride can no longer be cancelled")
    transition("ride", ride, RideStatus.CANCELLED)
    ride.cancelled_at, ride.cancelled_by = utcnow(), driver.user_id
    transition("trip", db.get(DriverTripPost, ride.driver_trip_id), TripStatus.CANCELLED)
    driver.trips_cancelled += 1
    pay.release_all(db, ride)
    group = db.get(RideGroup, ride.ride_group_id)
    if group:
        group.status = GroupStatus.CANCELLED
    for rp in ride.passengers:
        if rp.status != "confirmed":
            continue
        rp.status = "cancelled"
        req = db.get(PassengerRequest, rp.request_id)
        transition("request", req, RequestStatus.SEARCHING)
        ns.notify(db, rp.user_id, ns.CANCELLATION, "Your driver cancelled",
                  "No charge. We're already looking for another driver.", {"ride_id": ride.id})
    log_event("ride.driver_cancelled", ride_id=ride.id, driver_id=driver.id, reason=reason, cancel_rate=driver.cancellation_rate)


# --------------------------------------------------------------------------- ratings
def apply_rating(db: Session, rating: Rating) -> None:
    profile = db.query(Profile).filter(Profile.user_id == rating.ratee_id).one()
    avg, n = db.query(func.avg(Rating.overall), func.count(Rating.id)).filter(Rating.ratee_id == rating.ratee_id).one()
    profile.rating_avg, profile.rating_count = round(float(avg or 0), 2), int(n or 0)
