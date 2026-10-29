"""Payment authorisation -> capture -> payout, behind a gateway interface.

``FakeGateway`` (default) lets the whole flow run offline. ``StripeGateway`` uses PaymentIntents with
manual capture (authorise at confirmation, capture on completion) and Stripe Connect transfers for payouts.
No card data ever touches this server: the mobile app confirms the intent with Stripe's SDK.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.db.base import utcnow
from app.models import Driver, DriverPayout, Payment, PaymentStatus, Ride, RidePassenger, User


class PaymentError(Exception):
    pass


class Gateway(Protocol):
    name: str

    def create_intent(self, amount_cents: int, currency: str, metadata: dict) -> tuple[str, str]: ...
    def is_authorized(self, ref: str) -> bool: ...
    def capture(self, ref: str, amount_cents: int | None = None) -> None: ...
    def cancel(self, ref: str) -> None: ...
    def refund(self, ref: str, amount_cents: int | None = None) -> None: ...
    def transfer(self, amount_cents: int, currency: str, destination: str, group: str) -> str: ...


class FakeGateway:
    name = "fake"
    _intents: dict[str, str] = {}

    def create_intent(self, amount_cents, currency, metadata):
        ref = f"pi_fake_{uuid.uuid4().hex[:16]}"
        self._intents[ref] = "requires_payment_method"
        return ref, f"{ref}_secret_{uuid.uuid4().hex[:8]}"

    def is_authorized(self, ref):  # the fake "payment sheet" always succeeds when confirmed
        self._intents[ref] = "requires_capture"
        return True

    def capture(self, ref, amount_cents=None):
        self._intents[ref] = "succeeded"

    def cancel(self, ref):
        self._intents[ref] = "canceled"

    def refund(self, ref, amount_cents=None):
        pass

    def transfer(self, amount_cents, currency, destination, group):
        return f"tr_fake_{uuid.uuid4().hex[:12]}"


class StripeGateway:
    name = "stripe"

    def __init__(self, key: str) -> None:
        import stripe

        stripe.api_key = key
        self.stripe = stripe

    def create_intent(self, amount_cents, currency, metadata):
        pi = self.stripe.PaymentIntent.create(
            amount=amount_cents, currency=currency, capture_method="manual",
            automatic_payment_methods={"enabled": True}, metadata=metadata,
        )
        return pi.id, pi.client_secret

    def is_authorized(self, ref):
        return self.stripe.PaymentIntent.retrieve(ref).status == "requires_capture"

    def capture(self, ref, amount_cents=None):
        kw = {"amount_to_capture": amount_cents} if amount_cents else {}
        self.stripe.PaymentIntent.capture(ref, **kw)

    def cancel(self, ref):
        self.stripe.PaymentIntent.cancel(ref)

    def refund(self, ref, amount_cents=None):
        kw = {"amount": amount_cents} if amount_cents else {}
        self.stripe.Refund.create(payment_intent=ref, **kw)

    def transfer(self, amount_cents, currency, destination, group):
        return self.stripe.Transfer.create(amount=amount_cents, currency=currency, destination=destination, transfer_group=group).id


_gateway: Gateway | None = None


def get_gateway() -> Gateway:
    global _gateway
    if _gateway is None:
        s = get_settings()
        _gateway = StripeGateway(s.stripe_secret_key) if s.payment_provider == "stripe" and s.stripe_secret_key else FakeGateway()
    return _gateway


def set_gateway(g: Gateway | None) -> None:  # for tests
    global _gateway
    _gateway = g


def cents(amount: float) -> int:
    return int(round(amount * 100))


def ensure_payment_rows(db: Session, ride: Ride) -> list[Payment]:
    """One Payment per confirmed passenger, created when the ride is confirmed."""
    out = []
    for rp in ride.passengers:
        p = db.query(Payment).filter(Payment.ride_id == ride.id, Payment.user_id == rp.user_id).first()
        if p is None:
            p = Payment(ride_id=ride.id, user_id=rp.user_id, amount_cents=cents(rp.fare), platform_fee_cents=cents(rp.platform_fee),
                        provider=get_gateway().name)
            db.add(p)
        out.append(p)
    db.flush()
    return out


def create_for_user(db: Session, ride: Ride, user: User) -> Payment:
    rp = next((x for x in ride.passengers if x.user_id == user.id and x.status == "confirmed"), None)
    if rp is None:
        raise PaymentError("You are not a passenger on this ride")
    payment = next((p for p in ensure_payment_rows(db, ride) if p.user_id == user.id), None)
    assert payment is not None
    if payment.provider_ref is None:
        ref, secret = get_gateway().create_intent(
            payment.amount_cents, payment.currency, {"ride_id": str(ride.id), "user_id": str(user.id), "payment_id": str(payment.id)}
        )
        payment.provider_ref, payment.client_secret = ref, secret
        log_event("payment.intent_created", payment_id=payment.id, ride_id=ride.id, amount_cents=payment.amount_cents)
    return payment


def confirm(db: Session, payment: Payment) -> Payment:
    if payment.status in (PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED):
        return payment
    if not payment.provider_ref:
        raise PaymentError("Payment has not been created yet")
    if get_gateway().is_authorized(payment.provider_ref):
        payment.status = PaymentStatus.AUTHORIZED
        log_event("payment.authorized", payment_id=payment.id, ride_id=payment.ride_id)
    else:
        payment.status = PaymentStatus.FAILED
        log_event("payment.failed", payment_id=payment.id, ride_id=payment.ride_id)
    return payment


def capture_ride(db: Session, ride: Ride) -> tuple[int, int]:
    """Capture authorised payments and create the driver payout. Returns (captured_cents, payout_cents)."""
    gw, captured, fees = get_gateway(), 0, 0
    for p in db.query(Payment).filter(Payment.ride_id == ride.id).all():
        rp = next((x for x in ride.passengers if x.user_id == p.user_id), None)
        if rp is None or rp.status == "cancelled":
            continue
        if p.status == PaymentStatus.AUTHORIZED and p.provider_ref:
            try:
                gw.capture(p.provider_ref)
                p.status = PaymentStatus.CAPTURED
                captured += p.amount_cents
                fees += p.platform_fee_cents
                log_event("payment.captured", payment_id=p.id, ride_id=ride.id, amount_cents=p.amount_cents)
            except Exception as exc:
                p.status = PaymentStatus.FAILED
                log_event("payment.capture_failed", payment_id=p.id, error=str(exc))
        elif p.status != PaymentStatus.CAPTURED:
            log_event("payment.unpaid_at_completion", payment_id=p.id, status=str(p.status))
    payout_cents = captured - fees
    if payout_cents > 0:
        payout = DriverPayout(driver_id=ride.driver_id, ride_id=ride.id, amount_cents=payout_cents)
        driver = db.get(Driver, ride.driver_id)
        if driver and driver.stripe_account_id or get_gateway().name == "fake":
            try:
                payout.provider_ref = gw.transfer(payout_cents, "cad", driver.stripe_account_id or "acct_fake", f"ride_{ride.id}")
                payout.status, payout.paid_at = "paid", utcnow()
            except Exception as exc:
                payout.status = "failed"
                log_event("payout.failed", ride_id=ride.id, error=str(exc))
        db.add(payout)
        log_event("payout.created", ride_id=ride.id, amount_cents=payout_cents, status=payout.status)
    return captured, payout_cents


def void_or_charge_fee(db: Session, payment: Payment, fee_cents: int) -> None:
    """Passenger cancelled: charge only the cancellation fee (if any) and release the rest."""
    gw = get_gateway()
    if payment.status == PaymentStatus.AUTHORIZED and payment.provider_ref:
        if fee_cents > 0:
            gw.capture(payment.provider_ref, fee_cents)
            payment.cancellation_fee_cents = fee_cents
            payment.amount_cents = fee_cents
            payment.platform_fee_cents = fee_cents
            payment.status = PaymentStatus.CAPTURED
        else:
            gw.cancel(payment.provider_ref)
            payment.status = PaymentStatus.CANCELLED
    else:
        payment.status = PaymentStatus.CANCELLED
        if fee_cents > 0:
            payment.cancellation_fee_cents = fee_cents  # owed; collected on next booking
    log_event("payment.cancelled", payment_id=payment.id, fee_cents=fee_cents)


def release_all(db: Session, ride: Ride) -> None:
    for p in db.query(Payment).filter(Payment.ride_id == ride.id).all():
        if p.status == PaymentStatus.AUTHORIZED and p.provider_ref:
            get_gateway().cancel(p.provider_ref)
        if p.status in (PaymentStatus.AUTHORIZED, PaymentStatus.REQUIRES_CONFIRMATION):
            p.status = PaymentStatus.CANCELLED


def refund(db: Session, payment: Payment, amount_cents: int | None = None) -> Payment:
    if payment.status != PaymentStatus.CAPTURED:
        raise PaymentError("Only captured payments can be refunded")
    remaining = payment.amount_cents - payment.refunded_cents
    amt = min(amount_cents or remaining, remaining)
    if amt <= 0:
        raise PaymentError("Nothing left to refund")
    if payment.provider_ref:
        get_gateway().refund(payment.provider_ref, amt)
    payment.refunded_cents += amt
    if payment.refunded_cents >= payment.amount_cents:
        payment.status = PaymentStatus.REFUNDED
    log_event("payment.refunded", payment_id=payment.id, amount_cents=amt)
    return payment
