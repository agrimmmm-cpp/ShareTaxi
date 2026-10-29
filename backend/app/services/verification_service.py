"""Pluggable verification. ``ManualReviewProvider`` queues documents for admin review; implement
``VerificationProvider`` for Persona / Onfido / Stripe Identity and register it in ``get_provider``."""
from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.logging import log_event
from app.db.base import utcnow
from app.models import Driver, DriverDocument, User, VerificationStatus as V

REQUIRED_DOCS = ("drivers_licence", "vehicle_registration", "insurance", "identity")


class VerificationProvider(Protocol):
    def submit(self, driver: Driver, doc: DriverDocument) -> str: ...


class ManualReviewProvider:
    def submit(self, driver, doc):
        return V.PENDING  # a human approves it in the admin dashboard


def get_provider() -> VerificationProvider:
    return ManualReviewProvider()


def submit_document(db: Session, driver: Driver, doc_type: str, file_url: str) -> DriverDocument:
    doc = DriverDocument(driver_id=driver.id, doc_type=doc_type, file_url=file_url)
    doc.status = get_provider().submit(driver, doc)
    db.add(doc)
    db.flush()
    evaluate_driver(db, driver)
    return doc


def evaluate_driver(db: Session, driver: Driver) -> str:
    """Approved only when every required document type has an approved copy and a vehicle exists."""
    db.refresh(driver)
    latest: dict[str, DriverDocument] = {}
    for d in sorted(driver.documents, key=lambda d: d.id):
        latest[d.doc_type] = d
    if any(d.status == V.REJECTED for d in latest.values()):
        status = V.REJECTED
    elif all(t in latest and latest[t].status == V.APPROVED for t in REQUIRED_DOCS) and driver.vehicles:
        status = V.APPROVED
    elif latest:
        status = V.PENDING
    else:
        status = V.UNSUBMITTED
    if status != driver.verification_status:
        log_event("driver.verification_changed", driver_id=driver.id, old=str(driver.verification_status), new=str(status))
    driver.verification_status = status
    return status


def review_document(db: Session, doc: DriverDocument, reviewer: User, approve: bool, notes: str | None) -> str:
    doc.status = V.APPROVED if approve else V.REJECTED
    doc.reviewer_id, doc.review_notes, doc.reviewed_at = reviewer.id, notes, utcnow()
    return evaluate_driver(db, doc.driver)


# Passenger verification: email + phone one-time codes (SMS/email delivery is a provider seam).
def start_phone_verification(user_id: int) -> str:
    code = "000000"  # replace with random code + SMS provider; fixed in dev so the flow is testable
    get_cache().set_json(f"verify:phone:{user_id}", code, 600)
    return code


def confirm_phone(db: Session, user: User, code: str) -> bool:
    if get_cache().get_json(f"verify:phone:{user.id}") == code:
        user.phone_verified = True
        get_cache().delete(f"verify:phone:{user.id}")
        return True
    return False
