from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Driver, Profile, Ride, RidePassenger, User
from app.repositories.rides import RideRepository
from app.schemas.rides import CancelIn, RideOut
from app.services import matching_orchestrator as orch
from app.services import notification_service as ns
from app.services import presenters, ride_service
from app.services.state_machine import InvalidTransition

router = APIRouter(prefix="/rides", tags=["rides"])


def _ride(db: Session, ride_id: int, user: User) -> Ride:
    ride = db.get(Ride, ride_id)
    if ride is None:
        raise HTTPException(404, "Ride not found")
    is_pax = any(p.user_id == user.id for p in ride.passengers)
    is_driver = user.driver is not None and ride.driver_id == user.driver.id
    if not (is_pax or is_driver or user.is_admin):
        raise HTTPException(404, "Ride not found")  # don't leak existence
    return ride


def _driver_ride(db: Session, ride_id: int, user: User) -> tuple[Ride, Driver]:
    ride = _ride(db, ride_id, user)
    if user.driver is None or ride.driver_id != user.driver.id:
        raise HTTPException(403, "Only the driver can do this")
    return ride, user.driver


@router.get("", response_model=list[RideOut])
def list_rides(role: str = "passenger", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = RideRepository(db)
    rides = repo.for_driver(user.driver.id) if role == "driver" and user.driver else repo.for_user(user.id)
    return [presenters.serialize_ride(db, r, user) for r in rides]


@router.get("/{ride_id}", response_model=RideOut)
def get_ride(ride_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return presenters.serialize_ride(db, _ride(db, ride_id, user), user)


def _transition(db: Session, ride: Ride, user: User, fn, *args) -> RideOut:
    try:
        fn(db, ride, *args)
    except (InvalidTransition, ride_service.RideError) as exc:
        db.rollback()
        raise HTTPException(409, str(exc))
    db.commit()
    return presenters.serialize_ride(db, ride, user)


@router.post("/{ride_id}/arriving", response_model=RideOut)
def arriving(ride_id: int, bg: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ride, _ = _driver_ride(db, ride_id, user)
    out = _transition(db, ride, user, ride_service.mark_arriving)
    bg.add_task(ns.drain_push_queue)
    return out


@router.post("/{ride_id}/start", response_model=RideOut)
def start(ride_id: int, bg: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ride, _ = _driver_ride(db, ride_id, user)
    out = _transition(db, ride, user, ride_service.start_ride)
    bg.add_task(ns.drain_push_queue)
    return out


@router.post("/{ride_id}/complete", response_model=RideOut)
def complete(ride_id: int, bg: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ride, _ = _driver_ride(db, ride_id, user)
    out = _transition(db, ride, user, ride_service.complete_ride)
    bg.add_task(ns.drain_push_queue)
    return out


@router.post("/{ride_id}/cancel", response_model=RideOut)
def cancel(ride_id: int, body: CancelIn, bg: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ride = _ride(db, ride_id, user)
    try:
        if user.driver is not None and ride.driver_id == user.driver.id:
            ride_service.cancel_by_driver(db, ride, user.driver, body.reason)
            db.flush()
            orch.rematch(db)  # automatically look for another driver for the stranded passengers
        else:
            ride_service.cancel_by_passenger(db, ride, user, body.reason)
            db.flush()
            orch.rematch(db)
    except (InvalidTransition, ride_service.RideError) as exc:
        db.rollback()
        raise HTTPException(getattr(exc, "status", 409), str(exc))
    db.commit()
    bg.add_task(ns.drain_push_queue)
    return presenters.serialize_ride(db, ride, user)
