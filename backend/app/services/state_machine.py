"""Explicit state transitions. Every status change goes through ``transition`` so illegal jumps fail loudly
and every legal one is logged."""
from __future__ import annotations

from app.core.logging import log_event
from app.models.enums import RequestStatus as R, RideStatus as S, TripStatus as T


class InvalidTransition(ValueError):
    pass


RIDE: dict[str, set[str]] = {
    S.CONFIRMED: {S.DRIVER_ARRIVING, S.ACTIVE, S.CANCELLED},
    S.DRIVER_ARRIVING: {S.ACTIVE, S.CANCELLED},
    S.ACTIVE: {S.COMPLETED},
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}

REQUEST: dict[str, set[str]] = {
    R.SEARCHING: {R.GROUP_FOUND, R.DRIVER_SEARCH, R.DRIVER_FOUND, R.CONFIRMED, R.CANCELLED, R.EXPIRED},
    R.GROUP_FOUND: {R.SEARCHING, R.DRIVER_SEARCH, R.DRIVER_FOUND, R.CONFIRMED, R.CANCELLED, R.EXPIRED},
    R.DRIVER_SEARCH: {R.SEARCHING, R.GROUP_FOUND, R.DRIVER_FOUND, R.CONFIRMED, R.CANCELLED, R.EXPIRED},
    R.DRIVER_FOUND: {R.SEARCHING, R.GROUP_FOUND, R.DRIVER_SEARCH, R.CONFIRMED, R.CANCELLED, R.EXPIRED},
    R.CONFIRMED: {R.SEARCHING, R.GROUP_FOUND, R.DRIVER_ARRIVING, R.ACTIVE, R.CANCELLED},  # back to searching if driver cancels
    R.DRIVER_ARRIVING: {R.ACTIVE, R.CANCELLED, R.SEARCHING},
    R.ACTIVE: {R.COMPLETED},
    R.COMPLETED: set(),
    R.CANCELLED: set(),
    R.EXPIRED: set(),
}

TRIP: dict[str, set[str]] = {
    T.OPEN: {T.MATCHED, T.CONFIRMED, T.CANCELLED},
    T.MATCHED: {T.OPEN, T.CONFIRMED, T.CANCELLED},
    T.CONFIRMED: {T.ACTIVE, T.OPEN, T.CANCELLED},
    T.ACTIVE: {T.COMPLETED},
    T.COMPLETED: set(),
    T.CANCELLED: set(),
}

TABLES = {"ride": RIDE, "request": REQUEST, "trip": TRIP}


def can_transition(kind: str, current: str, new: str) -> bool:
    return current == new or new in TABLES[kind].get(current, set())


def transition(kind: str, obj, new: str) -> None:
    current = obj.status
    if current == new:
        return
    if not can_transition(kind, current, new):
        raise InvalidTransition(f"{kind}: {current} -> {new} is not allowed")
    obj.status = new
    log_event(f"{kind}.state_changed", id=getattr(obj, "id", None), old=str(current), new=str(new))
