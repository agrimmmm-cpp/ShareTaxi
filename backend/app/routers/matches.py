from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_driver
from app.db.base import utcnow
from app.db.session import get_db
from app.models import Driver, DriverTripPost, Match, MatchStatus, PassengerRequest, User
from app.repositories.rides import MatchRepository
from app.schemas.rides import MatchOut, RideOut
from app.services import matching_orchestrator as orch
from app.services import notification_service as ns
from app.services import presenters, ride_service

router = APIRouter(prefix="/matches", tags=["matching"])


@router.get("/ride-request/{request_id}", response_model=list[MatchOut])
def matches_for_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(PassengerRequest, request_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Ride request not found")
    out = []
    for m in db.query(Match).filter(Match.status == MatchStatus.PROPOSED).order_by(Match.overall_score.desc()).all():
        if request_id in (m.plan or {}).get("request_ids", []):
            out.append(presenters.serialize_match(db, m, user, as_driver=False))
    return out


@router.get("/driver-trip/{trip_id}", response_model=list[MatchOut])
def matches_for_trip(trip_id: int, refresh: bool = True, driver: Driver = Depends(require_driver),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    trip = db.get(DriverTripPost, trip_id)
    if trip is None or trip.driver_id != driver.id:
        raise HTTPException(404, "Trip not found")
    if refresh:
        orch.recommend_for_trip(db, trip)
        db.commit()
    return [presenters.serialize_match(db, m, user, as_driver=True) for m in MatchRepository(db).for_trip(trip_id)]


def _driver_match(db: Session, match_id: int, driver: Driver) -> Match:
    m = db.get(Match, match_id)
    if m is None or m.trip.driver_id != driver.id:
        raise HTTPException(404, "Match not found")
    return m


@router.post("/{match_id}/accept", response_model=RideOut)
def accept(match_id: int, bg: BackgroundTasks, driver: Driver = Depends(require_driver),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = _driver_match(db, match_id, driver)
    try:
        ride = ride_service.confirm_match(db, m)
    except ride_service.RideError as exc:
        db.rollback()
        raise HTTPException(exc.status, str(exc))
    orch.rematch(db)  # the pool changed: rebuild the remaining groups
    db.commit()
    bg.add_task(ns.drain_push_queue)
    return presenters.serialize_ride(db, ride, user)


@router.post("/{match_id}/reject", status_code=204)
def reject(match_id: int, driver: Driver = Depends(require_driver), db: Session = Depends(get_db)):
    m = _driver_match(db, match_id, driver)
    try:
        ride_service.reject_match(db, m)
    except ride_service.RideError as exc:
        raise HTTPException(exc.status, str(exc))
    db.commit()
