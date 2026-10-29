from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Rating, Ride, RideStatus, User
from app.schemas.misc import RatingIn, RatingOut
from app.services import ride_service

router = APIRouter(tags=["ratings"])


@router.post("/ratings", response_model=RatingOut, status_code=201)
def create_rating(data: RatingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ride = db.get(Ride, data.ride_id)
    if ride is None or ride.status != RideStatus.COMPLETED:
        raise HTTPException(409, "You can rate a ride once it's completed")
    driver_uid = ride.driver.user_id
    pax_uids = {p.user_id for p in ride.passengers if p.status == "completed"}
    if user.id == driver_uid:
        if data.ratee_id not in pax_uids:
            raise HTTPException(403, "You can only rate passengers from this ride")
    elif user.id in pax_uids:
        if data.ratee_id != driver_uid:
            raise HTTPException(403, "Passengers rate the driver")
    else:
        raise HTTPException(403, "You weren't on this ride")
    if user.id != driver_uid and data.safety is None and False:
        pass
    if db.query(Rating).filter_by(ride_id=ride.id, rater_id=user.id, ratee_id=data.ratee_id).first():
        raise HTTPException(409, "You've already rated this person for this ride")
    r = Rating(rater_id=user.id, **data.model_dump(exclude={"safety"}), safety=data.safety if data.ratee_id == driver_uid else None)
    db.add(r)
    db.flush()
    ride_service.apply_rating(db, r)
    db.commit()
    return r


@router.get("/users/{user_id}/ratings")
def user_ratings(user_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Rating).filter(Rating.ratee_id == user_id).order_by(Rating.id.desc()).limit(50).all()
    if not rows:
        return {"count": 0, "average": None, "categories": {}, "recent": []}
    def avg(attr):
        vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None
    return {
        "count": len(rows), "average": avg("overall"),
        "categories": {"communication": avg("communication"), "punctuality": avg("punctuality"), "safety": avg("safety")},
        "recent": [{"overall": r.overall, "comment": r.comment, "created_at": r.created_at} for r in rows if r.comment][:10],
    }
