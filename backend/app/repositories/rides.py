from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    DriverTripPost, GroupStatus, Match, MatchStatus, PassengerRequest, RequestStatus, Ride, RideGroup,
    RidePassenger, TripStatus,
)
from app.repositories.base import Repository

POOL_STATUSES = (RequestStatus.SEARCHING, RequestStatus.GROUP_FOUND, RequestStatus.DRIVER_SEARCH, RequestStatus.DRIVER_FOUND)


class RequestRepository(Repository[PassengerRequest]):
    model = PassengerRequest

    def active_pool(self, now: datetime) -> list[PassengerRequest]:
        return (
            self.db.query(PassengerRequest)
            .filter(PassengerRequest.status.in_(POOL_STATUSES), PassengerRequest.latest_departure >= now)
            .order_by(PassengerRequest.id)
            .all()
        )

    def expire_stale(self, now: datetime) -> int:
        stale = (
            self.db.query(PassengerRequest)
            .filter(PassengerRequest.status.in_(POOL_STATUSES), PassengerRequest.latest_departure < now)
            .all()
        )
        for r in stale:
            r.status = RequestStatus.EXPIRED
        return len(stale)

    def for_user(self, user_id: int) -> list[PassengerRequest]:
        return (
            self.db.query(PassengerRequest).filter(PassengerRequest.user_id == user_id)
            .order_by(PassengerRequest.preferred_departure.desc()).all()
        )


class TripRepository(Repository[DriverTripPost]):
    model = DriverTripPost

    def open_for_matching(self, now: datetime) -> list[DriverTripPost]:
        return (
            self.db.query(DriverTripPost)
            .filter(DriverTripPost.status == TripStatus.OPEN, DriverTripPost.auto_match.is_(True), DriverTripPost.departure_time >= now)
            .order_by(DriverTripPost.id).all()
        )

    def for_driver(self, driver_id: int) -> list[DriverTripPost]:
        return (
            self.db.query(DriverTripPost).filter(DriverTripPost.driver_id == driver_id)
            .order_by(DriverTripPost.departure_time.desc()).all()
        )


class GroupRepository(Repository[RideGroup]):
    model = RideGroup

    def open_groups(self) -> list[RideGroup]:
        return self.db.query(RideGroup).filter(RideGroup.status.in_((GroupStatus.FORMING, GroupStatus.DRIVER_SEARCH))).all()

    def discoverable(self, now: datetime, since: datetime, until: datetime) -> list[RideGroup]:
        return (
            self.db.query(RideGroup)
            .filter(RideGroup.status.in_((GroupStatus.FORMING, GroupStatus.DRIVER_SEARCH)),
                    RideGroup.suggested_departure.between(since, until), RideGroup.seats_used < RideGroup.seats_total)
            .order_by(RideGroup.suggested_departure).all()
        )


class MatchRepository(Repository[Match]):
    model = Match

    def for_trip(self, trip_id: int, statuses=(MatchStatus.PROPOSED,)) -> list[Match]:
        return (
            self.db.query(Match).filter(Match.driver_trip_id == trip_id, Match.status.in_(statuses))
            .order_by(Match.overall_score.desc()).all()
        )

    def for_group(self, group_id: int) -> list[Match]:
        return self.db.query(Match).filter(Match.ride_group_id == group_id).all()


class RideRepository(Repository[Ride]):
    model = Ride

    def for_user(self, user_id: int) -> list[Ride]:
        return (
            self.db.query(Ride).join(RidePassenger, RidePassenger.ride_id == Ride.id, isouter=True)
            .filter(or_(RidePassenger.user_id == user_id))
            .order_by(Ride.scheduled_departure.desc()).all()
        )

    def for_driver(self, driver_id: int) -> list[Ride]:
        return self.db.query(Ride).filter(Ride.driver_id == driver_id).order_by(Ride.scheduled_departure.desc()).all()
