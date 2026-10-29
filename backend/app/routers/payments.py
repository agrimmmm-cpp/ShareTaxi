from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Payment, Ride, User
from app.schemas.misc import PaymentConfirmIn, PaymentCreateIn, PaymentOut
from app.services import payment_service as pay

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/create", response_model=PaymentOut)
def create(data: PaymentCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ride = db.get(Ride, data.ride_id)
    if ride is None:
        raise HTTPException(404, "Ride not found")
    try:
        p = pay.create_for_user(db, ride, user)
    except pay.PaymentError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    return p


@router.post("/confirm", response_model=PaymentOut)
def confirm(data: PaymentConfirmIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(Payment, data.payment_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(404, "Payment not found")
    try:
        pay.confirm(db, p)
    except pay.PaymentError as exc:
        raise HTTPException(409, str(exc))
    db.commit()
    return p


@router.get("/history", response_model=list[PaymentOut])
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Passengers see what they paid; drivers see payouts via /driver/earnings."""
    return db.query(Payment).filter(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(100).all()
