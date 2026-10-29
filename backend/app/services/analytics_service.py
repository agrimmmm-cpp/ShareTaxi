from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import (
    DriverPayout, Payment, PaymentStatus, PassengerRequest, RequestStatus, Ride, RidePassenger, RideStatus, User,
)


def platform_analytics(db: Session) -> dict:
    now = utcnow()
    month_ago = now - timedelta(days=30)
    rides = db.query(func.count(Ride.id)).scalar() or 0
    done = [RideStatus.CONFIRMED, RideStatus.DRIVER_ARRIVING, RideStatus.ACTIVE, RideStatus.COMPLETED]
    live_rides = db.query(Ride).filter(Ride.status.in_(done)).all()
    cancelled_rides = db.query(func.count(Ride.id)).filter(Ride.status == RideStatus.CANCELLED).scalar() or 0
    total_requests = db.query(func.count(PassengerRequest.id)).scalar() or 0
    cancelled_requests = db.query(func.count(PassengerRequest.id)).filter(PassengerRequest.status == RequestStatus.CANCELLED).scalar() or 0
    matched = db.query(func.count(PassengerRequest.id)).filter(PassengerRequest.status.in_(
        [RequestStatus.CONFIRMED, RequestStatus.DRIVER_ARRIVING, RequestStatus.ACTIVE, RequestStatus.COMPLETED])).scalar() or 0
    eligible = total_requests - cancelled_requests - (db.query(func.count(PassengerRequest.id)).filter(PassengerRequest.status == RequestStatus.EXPIRED).scalar() or 0)
    pax = db.query(RidePassenger).join(Ride, Ride.id == RidePassenger.ride_id).filter(Ride.status != RideStatus.CANCELLED).all()
    savings = [100 * (p.benchmark - p.fare) / p.benchmark for p in pax if p.benchmark]
    active_users = db.query(func.count(func.distinct(PassengerRequest.user_id))).filter(PassengerRequest.created_at >= month_ago).scalar() or 0
    routes = (
        db.query(PassengerRequest.origin_area, PassengerRequest.destination_area, func.count(PassengerRequest.id))
        .group_by(PassengerRequest.origin_area, PassengerRequest.destination_area)
        .order_by(func.count(PassengerRequest.id).desc()).limit(5).all()
    )
    captured = db.query(func.coalesce(func.sum(Payment.amount_cents), 0)).filter(Payment.status == PaymentStatus.CAPTURED).scalar()
    fees = db.query(func.coalesce(func.sum(Payment.platform_fee_cents), 0)).filter(Payment.status == PaymentStatus.CAPTURED).scalar()
    payouts = db.query(func.coalesce(func.sum(DriverPayout.amount_cents), 0)).scalar()
    return {
        "total_bookings": rides,
        "total_users": db.query(func.count(User.id)).scalar() or 0,
        "active_users_30d": active_users,
        "passenger_match_rate": round(matched / eligible, 3) if eligible else 0.0,
        "average_occupancy": round(sum(len([p for p in r.passengers if p.status != "cancelled"]) for r in live_rides) / len(live_rides), 2) if live_rides else 0.0,
        "average_savings_percent": round(sum(savings) / len(savings), 1) if savings else 0.0,
        "driver_earnings": round(payouts / 100, 2),
        "gross_volume": round(captured / 100, 2),
        "platform_revenue": round(fees / 100, 2),
        "cancellation_rate": round((cancelled_rides + cancelled_requests) / (rides + total_requests), 3) if (rides + total_requests) else 0.0,
        "popular_routes": [{"origin": o, "destination": d, "requests": n} for o, d, n in routes],
    }
