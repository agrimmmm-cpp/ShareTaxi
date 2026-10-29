from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_driver
from app.db.base import utcnow
from app.db.session import get_db
from app.models import (
    Driver, DriverPayout, DriverTripPost, Match, MatchStatus, Profile, Ride, RideStatus, TripStatus, User, Vehicle,
)
from app.repositories.rides import MatchRepository, TripRepository
from app.schemas.misc import DocumentIn, DocumentOut, DriverApplyIn, PayoutOut, VehicleIn
from app.schemas.rides import DriverTripIn, DriverTripOut, DriverTripUpdate, VehicleOut
from app.services import discovery_service, verification_service
from app.services import matching_orchestrator as orch
from app.services import notification_service as ns
from app.services import posting_service as posting

router = APIRouter(prefix="/driver", tags=["driver"])


def _trip_out(db: Session, t: DriverTripPost, with_recs: bool = False) -> DriverTripOut:
    out = DriverTripOut.model_validate(t)
    ride = db.query(Ride).filter(Ride.driver_trip_id == t.id, Ride.status != RideStatus.CANCELLED).first()
    out.ride_id = ride.id if ride else None
    if with_recs:
        out.recommendations = len(MatchRepository(db).for_trip(t.id))
    return out


@router.post("/apply", status_code=201)
def apply(data: DriverApplyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.driver:
        raise HTTPException(409, "You already have a driver profile")
    driver = Driver(user_id=user.id)
    db.add(driver)
    db.flush()
    db.add(Vehicle(driver_id=driver.id, **data.vehicle.model_dump()))
    db.commit()
    return {"driver_id": driver.id, "status": driver.verification_status, "required_documents": list(verification_service.REQUIRED_DOCS)}


@router.get("/me")
def driver_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = user.driver
    if d is None:
        return {"is_driver": False}
    return {
        "is_driver": True, "status": d.verification_status, "cancellation_rate": d.cancellation_rate,
        "trips_completed": d.trips_completed, "vehicles": [VehicleOut.model_validate(v) for v in d.vehicles],
        "documents": [DocumentOut.model_validate(x) for x in d.documents],
        "required_documents": list(verification_service.REQUIRED_DOCS),
    }


@router.post("/documents", response_model=DocumentOut, status_code=201)
def upload_document(data: DocumentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.driver:
        raise HTTPException(409, "Apply to drive first")
    doc = verification_service.submit_document(db, user.driver, data.doc_type, data.file_url)
    db.commit()
    return doc


@router.post("/vehicles", response_model=VehicleOut, status_code=201)
def add_vehicle(data: VehicleIn, driver: Driver = Depends(require_driver), db: Session = Depends(get_db)):
    v = Vehicle(driver_id=driver.id, **data.model_dump())
    db.add(v)
    db.commit()
    return v


@router.get("/vehicles", response_model=list[VehicleOut])
def vehicles(driver: Driver = Depends(require_driver)):
    return driver.vehicles


@router.post("/trips", response_model=DriverTripOut, status_code=201)
def post_trip(data: DriverTripIn, bg: BackgroundTasks, driver: Driver = Depends(require_driver), db: Session = Depends(get_db)):
    try:
        trip = posting.create_driver_trip(db, driver, data)
    except posting.PostingError as exc:
        raise HTTPException(422, str(exc))
    if trip.departure_time < utcnow():
        raise HTTPException(422, "Departure time is in the past")
    orch.on_new_trip(db, trip)
    db.commit()
    bg.add_task(ns.drain_push_queue)
    return _trip_out(db, trip, True)


@router.get("/trips", response_model=list[DriverTripOut])
def list_trips(driver: Driver = Depends(require_driver), db: Session = Depends(get_db)):
    return [_trip_out(db, t, True) for t in TripRepository(db).for_driver(driver.id)]


def _own_trip(db: Session, trip_id: int, driver: Driver) -> DriverTripPost:
    t = db.get(DriverTripPost, trip_id)
    if t is None or t.driver_id != driver.id:
        raise HTTPException(404, "Trip not found")
    return t


@router.get("/trips/{trip_id}", response_model=DriverTripOut)
def get_trip(trip_id: int, driver: Driver = Depends(require_driver), db: Session = Depends(get_db)):
    return _trip_out(db, _own_trip(db, trip_id, driver), True)


@router.patch("/trips/{trip_id}", response_model=DriverTripOut)
def patch_trip(trip_id: int, data: DriverTripUpdate, driver: Driver = Depends(require_driver), db: Session = Depends(get_db)):
    t = _own_trip(db, trip_id, driver)
    patch = data.model_dump(exclude_unset=True)
    if t.status != TripStatus.OPEN:
        raise HTTPException(409, "Confirmed trips must be cancelled from the ride screen")
    if patch.pop("status", None) == "cancelled":
        t.status = TripStatus.CANCELLED
        for m in MatchRepository(db).for_trip(t.id):
            db.delete(m)
    else:
        if "available_seats" in patch:
            v = db.get(Vehicle, t.vehicle_id)
            if patch["available_seats"] > v.seats:
                raise HTTPException(422, f"Vehicle has only {v.seats} seats")
        if "departure_time" in patch:
            from app.utils.time import to_naive_utc
            patch["departure_time"] = to_naive_utc(patch["departure_time"])
        for k, v in patch.items():
            setattr(t, {"maximum_detour_minutes": "maximum_detour_minutes"}.get(k, k), v)
        orch.on_new_trip(db, t)  # flexibility or seats changed: recompute everything
    db.commit()
    return _trip_out(db, t, True)


@router.get("/dashboard")
def dashboard(driver: Driver = Depends(require_driver), db: Session = Depends(get_db)):
    now = utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)

    def earned(since):
        return round((db.query(func.coalesce(func.sum(DriverPayout.amount_cents), 0))
                      .filter(DriverPayout.driver_id == driver.id, DriverPayout.created_at >= since).scalar()) / 100, 2)

    trips = TripRepository(db).for_driver(driver.id)
    upcoming = [t for t in trips if t.departure_time >= now and t.status in (TripStatus.OPEN, TripStatus.CONFIRMED)]
    today = [t for t in trips if t.departure_time.date() == now.date()]
    profile = db.query(Profile).filter(Profile.user_id == driver.user_id).one()
    clusters = discovery_service.demand_clusters(db, now)
    return {
        "today_trips": len(today), "earnings_today": earned(start), "earnings_week": earned(week),
        "available_seats": sum(t.available_seats for t in upcoming if t.status == TripStatus.OPEN),
        "upcoming_trips": [_trip_out(db, t, True) for t in sorted(upcoming, key=lambda t: t.departure_time)[:5]],
        "nearby_requests": sum(c["requests"] for c in clusters), "route_demand": clusters[:5],
        "rating": profile.rating_avg, "rating_count": profile.rating_count, "cancellation_rate": driver.cancellation_rate,
    }


@router.get("/earnings")
def earnings(driver: Driver = Depends(require_driver), db: Session = Depends(get_db)):
    rows = db.query(DriverPayout).filter(DriverPayout.driver_id == driver.id).order_by(DriverPayout.created_at.desc()).limit(100).all()
    return {
        "total": round(sum(r.amount_cents for r in rows) / 100, 2),
        "pending": round(sum(r.amount_cents for r in rows if r.status == "pending") / 100, 2),
        "payouts": [PayoutOut.model_validate(r) for r in rows],
    }
