"""Recurring commutes: turn a weekly pattern into concrete requests/trips for the coming days. Because each
occurrence is a normal request, the grouping engine automatically suggests recurring ride groups."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import DriverTripPost, PassengerRequest, RecurringRequest, User
from app.schemas.rides import DriverTripIn, RideRequestIn
from app.services import posting_service as posting


def occurrences(rec: RecurringRequest, now: datetime, horizon_days: int = 7) -> list[datetime]:
    days = {int(d) for d in rec.days_of_week.split(",") if d != ""}
    hh, mm = (int(x) for x in rec.time_of_day.split(":"))
    out = []
    for i in range(horizon_days + 1):
        day = (now + timedelta(days=i)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        if day > now and day.weekday() in days:
            out.append(day)
    return out


def materialize(db: Session, rec: RecurringRequest, user: User, now: datetime, horizon_days: int = 7) -> list[object]:
    created: list[object] = []
    if not rec.active:
        return created
    for when in occurrences(rec, now, horizon_days):
        if rec.kind == "passenger":
            exists = db.query(PassengerRequest).filter(
                PassengerRequest.recurring_request_id == rec.id, PassengerRequest.preferred_departure == when).first()
            if exists:
                continue
            payload = RideRequestIn.model_validate({**rec.template, "preferred_departure": when})
            created.append(posting.create_ride_request(db, user.id, payload, recurring_id=rec.id))
        elif user.driver is not None:
            exists = db.query(DriverTripPost).filter(
                DriverTripPost.recurring_request_id == rec.id, DriverTripPost.departure_time == when).first()
            if exists:
                continue
            payload = DriverTripIn.model_validate({**rec.template, "departure_time": when})
            created.append(posting.create_driver_trip(db, user.driver, payload, recurring_id=rec.id))
    rec.last_generated_for = now
    return created
