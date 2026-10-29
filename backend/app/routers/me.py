"""Account-level resources: notifications, saved places, emergency contacts, blocking, reports, recurring
commutes, safety (SOS / trip sharing)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.logging import log_event
from app.db.base import utcnow
from app.db.session import get_db
from app.models import (
    EmergencyContact, Notification, RecurringRequest, Report, Ride, RideStatus, SavedLocation, User, UserBlock,
)
from app.schemas.misc import (
    EmergencyContactIn, EmergencyContactOut, NotificationOut, RecurringIn, RecurringOut, ReportIn, SavedLocationIn,
    SavedLocationOut, SosIn,
)
from app.services import matching_orchestrator as orch
from app.services import posting_service as posting
from app.services import recurring_service

router = APIRouter(tags=["account"])


# notifications ---------------------------------------------------------------------------------
@router.get("/notifications", response_model=list[NotificationOut])
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(100).all()


@router.post("/notifications/read-all", status_code=204)
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.read_at.is_(None)).update({"read_at": utcnow()})
    db.commit()


# saved locations -------------------------------------------------------------------------------
@router.get("/saved-locations", response_model=list[SavedLocationOut])
def saved(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(SavedLocation).filter(SavedLocation.user_id == user.id).all()


@router.post("/saved-locations", response_model=SavedLocationOut, status_code=201)
def add_saved(data: SavedLocationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        pt, _ = posting.resolve_point(data.address, data.lat, data.lng)
    except posting.PostingError as exc:
        raise HTTPException(422, str(exc))
    row = SavedLocation(user_id=user.id, label=data.label, address=data.address, lat=pt.lat, lng=pt.lng)
    db.add(row)
    db.commit()
    return row


@router.delete("/saved-locations/{loc_id}", status_code=204)
def del_saved(loc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SavedLocation, loc_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()


# safety ----------------------------------------------------------------------------------------
@router.get("/safety/contacts", response_model=list[EmergencyContactOut])
def contacts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(EmergencyContact).filter(EmergencyContact.user_id == user.id).all()


@router.post("/safety/contacts", response_model=EmergencyContactOut, status_code=201)
def add_contact(data: EmergencyContactIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = EmergencyContact(user_id=user.id, **data.model_dump())
    db.add(row)
    db.commit()
    return row


@router.delete("/safety/contacts/{cid}", status_code=204)
def del_contact(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(EmergencyContact, cid)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()


@router.post("/safety/block/{user_id}", status_code=204)
def block(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user_id == user.id or db.get(User, user_id) is None:
        raise HTTPException(422, "Invalid user")
    if not db.query(UserBlock).filter_by(blocker_id=user.id, blocked_id=user_id).first():
        db.add(UserBlock(blocker_id=user.id, blocked_id=user_id))
        db.commit()


@router.delete("/safety/block/{user_id}", status_code=204)
def unblock(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(UserBlock).filter_by(blocker_id=user.id, blocked_id=user_id).delete()
    db.commit()


@router.post("/safety/report", status_code=201)
def report(data: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = Report(reporter_id=user.id, **data.model_dump())
    db.add(row)
    db.commit()
    log_event("safety.report", report_id=row.id, category=data.category)
    return {"id": row.id, "status": row.status}


@router.post("/safety/sos", status_code=201)
def sos(data: SosIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Records an SOS incident for admins immediately; the app also offers a one-tap call to local emergency
    services and texts the user's emergency contacts the live-trip link."""
    row = Report(reporter_id=user.id, ride_id=data.ride_id, category="sos", is_sos=True, lat=data.lat, lng=data.lng, details="SOS triggered")
    db.add(row)
    contacts_ = db.query(EmergencyContact).filter(EmergencyContact.user_id == user.id).all()
    share = db.get(Ride, data.ride_id).share_token if data.ride_id and db.get(Ride, data.ride_id) else None
    db.commit()
    log_event("safety.sos", report_id=row.id, user_id=user.id, ride_id=data.ride_id)
    return {"id": row.id, "notified_contacts": [c.name for c in contacts_], "share_token": share}


@router.get("/share/{token}")
def shared_trip(token: str, db: Session = Depends(get_db)):
    """Public live-trip page for friends/family (no auth, minimal data, token is unguessable)."""
    ride = db.query(Ride).filter(Ride.share_token == token).first()
    if ride is None:
        raise HTTPException(404, "Link not found")
    nxt = next((s for s in ride.stops if s.arrived_at is None), None)
    return {
        "status": ride.status, "departure": ride.scheduled_departure, "polyline": ride.route_polyline,
        "driver": {"first_name": ride.driver.user.profile.full_name.split()[0], "vehicle": f"{ride.vehicle.color} {ride.vehicle.make} {ride.vehicle.model}",
                   "plate": ride.vehicle.license_plate},
        "next_stop_area": nxt.area if nxt else None, "live": ride.status in (RideStatus.ACTIVE, RideStatus.DRIVER_ARRIVING),
    }


# recurring -------------------------------------------------------------------------------------
@router.post("/recurring", response_model=RecurringOut, status_code=201)
def create_recurring(data: RecurringIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.kind == "driver" and not user.is_driver:
        raise HTTPException(403, "Verified driver account required")
    rec = RecurringRequest(user_id=user.id, kind=data.kind, days_of_week=",".join(str(d) for d in sorted(set(data.days_of_week))),
                           time_of_day=data.time_of_day, template=data.template)
    db.add(rec)
    db.flush()
    try:
        recurring_service.materialize(db, rec, user, utcnow())
    except Exception as exc:  # bad template: reject the recurring rule itself
        db.rollback()
        raise HTTPException(422, f"Invalid template: {exc}")
    orch.rematch(db)
    db.commit()
    return rec


@router.get("/recurring", response_model=list[RecurringOut])
def list_recurring(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(RecurringRequest).filter(RecurringRequest.user_id == user.id).all()


@router.delete("/recurring/{rid}", status_code=204)
def stop_recurring(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = db.get(RecurringRequest, rid)
    if rec is None or rec.user_id != user.id:
        raise HTTPException(404, "Not found")
    rec.active = False
    db.commit()
