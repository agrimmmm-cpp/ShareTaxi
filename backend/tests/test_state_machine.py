import pytest

from app.models.enums import RequestStatus as R, RideStatus as S, TripStatus as T
from app.services.state_machine import InvalidTransition, can_transition, transition


class Obj:
    def __init__(self, status):
        self.status = status
        self.id = 1


def test_ride_happy_path():
    r = Obj(S.CONFIRMED)
    for nxt in (S.DRIVER_ARRIVING, S.ACTIVE, S.COMPLETED):
        transition("ride", r, nxt)
    assert r.status == S.COMPLETED


@pytest.mark.parametrize("start,bad", [
    (S.COMPLETED, S.ACTIVE), (S.CANCELLED, S.CONFIRMED), (S.CONFIRMED, S.COMPLETED), (S.ACTIVE, S.CANCELLED),
])
def test_ride_illegal_transitions(start, bad):
    with pytest.raises(InvalidTransition):
        transition("ride", Obj(start), bad)


def test_request_lifecycle_and_reentry_after_driver_cancel():
    r = Obj(R.SEARCHING)
    for nxt in (R.GROUP_FOUND, R.DRIVER_SEARCH, R.DRIVER_FOUND, R.CONFIRMED):
        transition("request", r, nxt)
    transition("request", r, R.SEARCHING)  # driver cancelled -> back in the pool
    assert r.status == R.SEARCHING


def test_terminal_states_are_final():
    for kind, s in (("request", R.COMPLETED), ("request", R.CANCELLED), ("trip", T.COMPLETED), ("trip", T.CANCELLED)):
        assert not can_transition(kind, s, R.SEARCHING if kind == "request" else T.OPEN)


def test_same_state_is_noop():
    r = Obj(T.OPEN)
    transition("trip", r, T.OPEN)
    assert r.status == T.OPEN
