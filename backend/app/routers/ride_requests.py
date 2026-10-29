from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.logging import log_event
from app.db.base import utcnow
from app.db.session import get_db
from app.models import PassengerRequest, RequestStatus, RidePassenger, User
from app.repositories.rides import POOL_STATUSES, RequestRepository
from app.schemas.rides import RideRequestIn, RideRequestOut, RideRequestUpdate
from app.services import matching_orchestrator as orch
from app.services import matching_service as ms
from app.services import notification_service as ns
from app.services import posting_service as posting
from app.services import presenters
from app.services.state_machine import transition
from app.utils.time import to_naive_utc

router = APIRouter(prefix="/ride-requests", tags=["passenger"])


def _owned(db: Session, request_id: int, user: User) -> PassengerRequest:
    r = db.get(PassengerRequest, request_id)
    if r is None or (r.user_id != user.id and not user.is_admin):
        raise HTTPException(404, "Ride request not found")
    return r


def _ride_id(db: Session, r: PassengerRequest) -> int | None:
    rp = db.query(RidePassenger).filter(RidePassenger.request_id == r.id, RidePassenger.status != "cancelled").first()
    return rp.ride_id if rp else None


def _potential(db: Session, r: PassengerRequest) -> int:
    cfg = get_settings().matching
    pool = RequestRepository(db).active_pool(utcnow())
    me = orch.request_to_data(r)
    return len(ms.find_passenger_matches(me, [orch.request_to_data(x) for x in pool], cfg))


@router.post("", response_model=RideRequestOut, status_code=201)
def create_request(data: RideRequestIn, bg: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        req = posting.create_ride_request(db, user.id, data)
    except posting.PostingError as exc:
        raise HTTPException(422, str(exc))
    if req.latest_departure < utcnow():
        raise HTTPException(422, "Departure time is in the past")
    log_event("request.created", request_id=req.id, user_id=user.id)
    orch.on_new_request(db, req)
    db.commit()
    db.refresh(req)
    bg.add_task(ns.drain_push_queue)
    return presenters.serialize_request(db, req, presenters.request_summary(db, req, _potential(db, req)))


@router.get("", response_model=list[RideRequestOut])
def list_requests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [presenters.serialize_request(db, r, ride_id=_ride_id(db, r)) for r in RequestRepository(db).for_user(user.id)]


@router.get("/{request_id}", response_model=RideRequestOut)
def get_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _owned(db, request_id, user)
    summary = presenters.request_summary(db, r, _potential(db, r) if r.status in POOL_STATUSES else 0)
    return presenters.serialize_request(db, r, summary, _ride_id(db, r))


@router.put("/{request_id}", response_model=RideRequestOut)
def update_request(request_id: int, data: RideRequestUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _owned(db, request_id, user)
    if r.status not in POOL_STATUSES:
        raise HTTPException(409, "This request can no longer be edited")
    patch = data.model_dump(exclude_unset=True)
    if "preferred_departure" in patch or "flexible_minutes" in patch:
        preferred = to_naive_utc(patch.get("preferred_departure") or r.preferred_departure)
        flex = timedelta(minutes=patch.get("flexible_minutes", int((r.latest_departure - r.preferred_departure).total_seconds() // 60)))
        r.preferred_departure, r.earliest_departure, r.latest_departure = preferred, preferred - flex, preferred + flex
    for k in ("passenger_count", "maximum_detour_minutes", "notes"):
        if k in patch:
            setattr(r, k, patch[k])
    orch.rematch(db)
    db.commit()
    db.refresh(r)
    return presenters.serialize_request(db, r, presenters.request_summary(db, r, _potential(db, r)))


@router.delete("/{request_id}", status_code=204)
def cancel_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _owned(db, request_id, user)
    if r.status not in POOL_STATUSES:
        raise HTTPException(409, "Confirmed rides must be cancelled from the ride screen (a fee may apply)")
    transition("request", r, RequestStatus.CANCELLED)
    orch.unindex_request(r.id)
    orch.rematch(db)
    db.commit()
