"""Admin API (role-protected). The web dashboard in app/admin_ui consumes exactly these endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import require_admin
from app.core.logging import log_event
from app.db.session import get_db
from app.models import (
    Driver, DriverDocument, DriverTripPost, Match, PassengerRequest, Payment, Rating, Report, Ride, User,
)
from app.schemas.misc import PlatformFeeIn, RefundIn, ResolveIn
from app.services import analytics_service, payment_service as pay, platform_settings, verification_service
from app.services import matching_orchestrator as orch

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _page(q, limit: int, offset: int):
    return q.offset(offset).limit(min(limit, 200)).all()


@router.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    return analytics_service.platform_analytics(db)


@router.get("/users")
def users(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return [{"id": u.id, "email": u.email, "name": u.profile.full_name, "roles": u.roles, "suspended": u.is_suspended,
             "rating": u.profile.rating_avg, "created_at": u.created_at} for u in _page(db.query(User).order_by(User.id.desc()), limit, offset)]


@router.post("/users/{user_id}/suspend")
def suspend(user_id: int, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    u.is_suspended = True
    db.commit()
    log_event("admin.user_suspended", user_id=user_id)
    return {"id": u.id, "suspended": True}


@router.post("/users/{user_id}/unsuspend")
def unsuspend(user_id: int, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    u.is_suspended = False
    db.commit()
    return {"id": u.id, "suspended": False}


@router.get("/drivers")
def drivers(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Driver)
    if status:
        q = q.filter(Driver.verification_status == status)
    return [{"id": d.id, "user_id": d.user_id, "name": d.user.profile.full_name, "status": d.verification_status,
             "cancellation_rate": d.cancellation_rate, "trips_completed": d.trips_completed,
             "documents": [{"id": x.id, "type": x.doc_type, "status": x.status, "file_url": x.file_url} for x in d.documents]}
            for d in q.order_by(Driver.id.desc()).limit(200)]


@router.post("/documents/{doc_id}/review")
def review_doc(doc_id: int, approve: bool, notes: str | None = None, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    doc = db.get(DriverDocument, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    status = verification_service.review_document(db, doc, admin, approve, notes)
    db.commit()
    return {"document": doc.status, "driver_status": status}


@router.get("/rides")
def rides(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return [{"id": r.id, "status": r.status, "departure": r.scheduled_departure, "passengers": len(r.passengers),
             "total_fare": r.total_fare, "platform_fee": r.platform_fee, "driver_payout": r.driver_payout}
            for r in _page(db.query(Ride).order_by(Ride.id.desc()), limit, offset)]


@router.get("/trips")
def trips(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return [{"id": t.id, "status": t.status, "from": t.origin_address, "to": t.destination_address, "departure": t.departure_time,
             "seats": t.available_seats, "driver_id": t.driver_id} for t in _page(db.query(DriverTripPost).order_by(DriverTripPost.id.desc()), limit, offset)]


@router.get("/requests")
def requests(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return [{"id": r.id, "status": r.status, "from": r.origin_area, "to": r.destination_area, "departure": r.preferred_departure,
             "passengers": r.passenger_count, "group_id": r.ride_group_id} for r in _page(db.query(PassengerRequest).order_by(PassengerRequest.id.desc()), limit, offset)]


@router.get("/matches")
def matches(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return [{"id": m.id, "status": m.status, "source": m.source, "trip_id": m.driver_trip_id, "group_id": m.ride_group_id,
             "score": m.overall_score, "scores": m.scores, "total_fare": m.total_fare, "driver_net": m.driver_net_earnings}
            for m in _page(db.query(Match).order_by(Match.id.desc()), limit, offset)]


@router.post("/rematch")
def rematch(db: Session = Depends(get_db)):
    res = orch.rematch(db)
    db.commit()
    return {"groups": res.groups, "viable": res.viable_groups, "new_matches": res.matches}


@router.get("/payments")
def payments(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return [{"id": p.id, "ride_id": p.ride_id, "user_id": p.user_id, "amount": p.amount_cents / 100, "fee": p.platform_fee_cents / 100,
             "status": p.status, "refunded": p.refunded_cents / 100} for p in _page(db.query(Payment).order_by(Payment.id.desc()), limit, offset)]


@router.post("/payments/{payment_id}/refund")
def refund(payment_id: int, body: RefundIn, db: Session = Depends(get_db)):
    p = db.get(Payment, payment_id)
    if p is None:
        raise HTTPException(404, "Payment not found")
    try:
        pay.refund(db, p, body.amount_cents)
    except pay.PaymentError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    return {"id": p.id, "status": p.status, "refunded": p.refunded_cents / 100}


@router.get("/reports")
def reports(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Report)
    if status:
        q = q.filter(Report.status == status)
    return [{"id": r.id, "category": r.category, "sos": r.is_sos, "status": r.status, "reporter_id": r.reporter_id,
             "reported_user_id": r.reported_user_id, "ride_id": r.ride_id, "details": r.details, "created_at": r.created_at,
             "lat": r.lat, "lng": r.lng} for r in q.order_by(Report.is_sos.desc(), Report.id.desc()).limit(200)]


@router.post("/reports/{report_id}/resolve")
def resolve(report_id: int, body: ResolveIn, db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    r.status, r.resolution = body.status, body.resolution
    db.commit()
    return {"id": r.id, "status": r.status}


@router.get("/ratings")
def ratings(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return [{"id": r.id, "ride_id": r.ride_id, "rater_id": r.rater_id, "ratee_id": r.ratee_id, "overall": r.overall, "comment": r.comment}
            for r in _page(db.query(Rating).order_by(Rating.id.desc()), limit, offset)]


@router.get("/settings")
def get_platform_settings():
    s = get_settings()
    return {"platform_commission_rate": s.pricing.platform_commission_rate, "matching": s.matching.model_dump(), "pricing": s.pricing.model_dump()}


@router.put("/settings/fees")
def set_fee(body: PlatformFeeIn, db: Session = Depends(get_db)):
    platform_settings.set_commission(db, body.platform_commission_rate)
    db.commit()
    log_event("admin.fee_changed", rate=body.platform_commission_rate)
    return {"platform_commission_rate": body.platform_commission_rate}
