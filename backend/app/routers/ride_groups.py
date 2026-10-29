from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import utcnow
from app.db.session import get_db
from app.models import PassengerRequest, RequestStatus, RideGroup
from app.models import User
from app.repositories.rides import POOL_STATUSES
from app.schemas.rides import RideGroupOut
from app.services import discovery_service
from app.services import matching_orchestrator as orch
from app.services import presenters
from app.services.state_machine import transition

router = APIRouter(prefix="/ride-groups", tags=["groups"])


class JoinIn(BaseModel):
    request_id: int


@router.get("/{group_id}", response_model=RideGroupOut)
def get_group(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.get(RideGroup, group_id)
    if g is None:
        raise HTTPException(404, "Group not found")
    is_member = any(m.user_id == user.id and m.status == "active" for m in g.members)
    if not is_member and g.status not in ("forming", "driver_search") and not user.is_admin:
        raise HTTPException(404, "Group not found")  # open groups are discoverable; confirmed ones are private
    return presenters.serialize_group(db, g, user)


@router.post("/{group_id}/join", response_model=RideGroupOut)
def join(group_id: int, body: JoinIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Join a discoverable group with one of your own pending requests. Compatibility is verified first; the
    grouping engine then places the request (deterministically) and we report where it landed."""
    g = db.get(RideGroup, group_id)
    r = db.get(PassengerRequest, body.request_id)
    if g is None or g.status not in ("forming", "driver_search"):
        raise HTTPException(404, "Group not found")
    if r is None or r.user_id != user.id or r.status not in POOL_STATUSES:
        raise HTTPException(404, "Ride request not found")
    if r.ride_group_id == g.id:
        return presenters.serialize_group(db, g, user)
    if discovery_service.preview_join(db, g, orch.request_to_data(r)) is None:
        raise HTTPException(409, "This group doesn't fit your route, time or seats")
    orch.rematch(db)
    db.commit()
    db.refresh(r)
    if r.ride_group_id != g.id:
        raise HTTPException(409, "The group changed while joining; your current group is %s" % r.ride_group_id)
    return presenters.serialize_group(db, db.get(RideGroup, g.id), user)


@router.post("/{group_id}/leave", status_code=204)
def leave(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.get(RideGroup, group_id)
    member = next((m for m in g.members if m.user_id == user.id and m.status == "active"), None) if g else None
    if member is None:
        raise HTTPException(404, "You're not in this group")
    r = db.get(PassengerRequest, member.request_id)
    if r.status not in POOL_STATUSES:
        raise HTTPException(409, "Confirmed rides must be cancelled from the ride screen")
    transition("request", r, RequestStatus.CANCELLED)
    orch.unindex_request(r.id)
    orch.rematch(db)
    db.commit()
