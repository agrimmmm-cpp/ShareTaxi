"""In-app notifications + push. Push messages are queued in Redis and drained by a background task so a
slow push provider can never block a request."""
from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.logging import log_event
from app.core.ws import manager
from app.models import Notification, Profile

PUSH_QUEUE = "queue:push"

# notification types (see spec section 24)
POTENTIAL_RIDERS = "potential_riders_found"
PASSENGER_JOINED = "passenger_joined"
GROUP_READY = "third_passenger_joined"
DRIVER_SEARCH = "driver_search_started"
DRIVER_FOUND = "driver_found"
MATCH_PROPOSED = "match_proposed"
DRIVER_ACCEPTED = "driver_accepted"
RIDE_CONFIRMED = "ride_confirmed"
DRIVER_APPROACHING = "driver_approaching"
PICKUP_REMINDER = "pickup_reminder"
RIDE_STARTED = "ride_started"
RIDE_COMPLETED = "ride_completed"
CANCELLATION = "cancellation"
PAYMENT_RECEIPT = "payment_receipt"
RATING_REMINDER = "rating_reminder"


def notify(db: Session, user_id: int, type_: str, title: str, body: str, data: dict | None = None) -> Notification:
    n = Notification(user_id=user_id, type=type_, title=title, body=body, data=data or {})
    db.add(n)
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    if profile and profile.push_token:
        get_cache().push(PUSH_QUEUE, {"to": profile.push_token, "title": title, "body": body, "data": {"type": type_, **(data or {})}})
    manager.broadcast_from_sync(f"user:{user_id}", {"type": "notification", "kind": type_, "title": title, "body": body})
    log_event("notification.queued", user_id=user_id, type=type_)
    return n


def drain_push_queue(limit: int = 100) -> int:
    """Send queued pushes via Expo. No-op (messages dropped, logged) unless PUSH_ENABLED=true."""
    s, cache, sent = get_settings(), get_cache(), 0
    batch = []
    while len(batch) < limit and (item := cache.pop(PUSH_QUEUE)) is not None:
        batch.append(item)
    if batch and s.push_enabled:
        try:
            httpx.post(s.expo_push_url, json=batch, timeout=10)
            sent = len(batch)
        except Exception as exc:  # re-queue so we retry on the next drain
            for item in batch:
                cache.push(PUSH_QUEUE, item)
            log_event("push.failed", error=str(exc))
    elif batch:
        log_event("push.skipped", count=len(batch))
    return sent
