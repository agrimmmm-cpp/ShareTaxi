"""Demo data: the exact scenario from the product brief.

    python -m app.seed            # idempotent; prints how the engine evaluated everything

Passenger A  Burnaby    -> Abbotsford  tomorrow 10:00
Passenger B  Coquitlam  -> Abbotsford  tomorrow  9:50
Passenger C  Burnaby    -> Langley     tomorrow 10:10
Driver       Vancouver  -> Abbotsford  tomorrow  9:30, 4 seats, min earnings $55
All demo accounts use the password ``password123``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base, utcnow
from app.db.session import SessionLocal, engine
from app.models import Driver, DriverTripPost, Match, PassengerRequest, Profile, RideGroup, User, Vehicle, VerificationStatus
from app.repositories.users import UserRepository
from app.schemas.rides import DriverTripIn, RideRequestIn
from app.services import matching_orchestrator as orch
from app.services import posting_service as posting

PASSWORD = "password123"
LOCAL_TZ = ZoneInfo("America/Vancouver")


def tomorrow_local(hour: int, minute: int = 0, days: int = 1) -> datetime:
    """A wall-clock time in Vancouver, returned as an aware UTC datetime."""
    day = (datetime.now(LOCAL_TZ) + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return day.astimezone(timezone.utc)


def _user(db: Session, email: str, name: str, admin: bool = False) -> User:
    repo = UserRepository(db)
    u = repo.by_email(email)
    if u is None:
        u = repo.create(email, hash_password(PASSWORD), name, "+1604555%04d" % (abs(hash(email)) % 10000),
                        is_admin=admin, email_verified=True, phone_verified=True)
    return u


def _driver(db: Session, user: User, make: str, model: str, color: str, plate: str, seats: int = 4) -> Driver:
    d = UserRepository(db).driver_for(user.id)
    if d is None:
        d = Driver(user_id=user.id, verification_status=VerificationStatus.APPROVED, trips_completed=42)
        db.add(d)
        db.flush()
        db.add(Vehicle(driver_id=d.id, make=make, model=model, year=2021, color=color, license_plate=plate, seats=seats))
        user.profile.rating_avg, user.profile.rating_count = 4.9, 128
        db.flush()
        db.refresh(d)
    return d


def req(origin: str, dest: str, when: datetime, **kw) -> RideRequestIn:
    return RideRequestIn(origin_address=origin, destination_address=dest, preferred_departure=when, maximum_detour_minutes=25, **kw)


def seed(db: Session) -> dict:
    if UserRepository(db).by_email("admin@sharetaxi.dev"):
        return {"seeded": False}
    _user(db, "admin@sharetaxi.dev", "Ada Admin", admin=True)
    a, b, c = (_user(db, f"{n}@sharetaxi.dev", f"{n.title()} {s}") for n, s in (("alice", "Chen"), ("bob", "Singh"), ("carol", "Martin")))
    dave = _user(db, "dave@sharetaxi.dev", "Dave Okafor")
    erin = _user(db, "erin@sharetaxi.dev", "Erin Tremblay")
    d_dave = _driver(db, dave, "Toyota", "Prius", "Silver", "BC 4TX 921")
    d_erin = _driver(db, erin, "Honda", "CR-V", "Blue", "BC 8KM 330", seats=4)
    db.flush()

    # passengers first, so the driver's post demonstrates "driver compares against existing requests"
    for user, o, d, h, m in ((a, "Burnaby", "Abbotsford", 10, 0), (b, "Coquitlam", "Abbotsford", 9, 50), (c, "Burnaby", "Langley", 10, 10)):
        r = posting.create_ride_request(db, user.id, req(o, d, tomorrow_local(h, m)))
        orch.on_new_request(db, r)
    # extra demand so the marketplace map has clusters
    for i, (o, d, h) in enumerate((("Richmond", "Downtown Vancouver", 8), ("Richmond", "Downtown Vancouver", 8), ("Surrey", "Downtown Vancouver", 8))):
        u = _user(db, f"rider{i}@sharetaxi.dev", f"Rider {i}")
        r = posting.create_ride_request(db, u.id, req(o, d, tomorrow_local(h, 15 + i * 5)))
        orch.on_new_request(db, r)

    trip = posting.create_driver_trip(db, d_dave, DriverTripIn(
        vehicle_id=d_dave.vehicles[0].id, origin_address="Vancouver", destination_address="Abbotsford",
        departure_time=tomorrow_local(9, 30), available_seats=4, maximum_detour_minutes=30, minimum_earnings=55))
    orch.on_new_trip(db, trip)
    db.commit()
    return {"seeded": True}


def report(db: Session) -> None:
    print("\n=== Ride groups ===")
    for g in db.query(RideGroup).order_by(RideGroup.id):
        names = [m.request.origin_area + "→" + m.request.destination_area + f" (${m.fare_estimate:.2f} vs ${m.benchmark_estimate:.2f})" for m in g.members]
        print(f"group {g.id} [{g.status}] seats {g.seats_used}/{g.seats_total} avg compat {g.avg_score}:")
        for n in names:
            print("   -", n)
    print("\n=== Driver matches ===")
    for m in db.query(Match).order_by(Match.overall_score.desc()):
        print(f"match {m.id} ({m.source}) trip {m.driver_trip_id}: score {m.overall_score} {m.scores} | pax {len(m.plan['request_ids'])} "
              f"fare ${m.total_fare:.2f} driver net ${m.driver_net_earnings:.2f} +{m.added_min:.0f} min detour")


if __name__ == "__main__":
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        print(seed(session))
        report(session)
