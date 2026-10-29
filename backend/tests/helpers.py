from __future__ import annotations

from datetime import datetime, timedelta

from app.models import Driver, User, Vehicle, VerificationStatus
from tests.conftest import auth_headers


def when(hour: int, minute: int = 0, days: int = 1) -> str:
    t = (datetime.utcnow() + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return t.isoformat() + "Z"


def ride_payload(origin, dest, hour, minute, **kw):
    return {"origin_address": origin, "destination_address": dest, "preferred_departure": when(hour, minute),
            "maximum_detour_minutes": 25, **kw}


def make_driver(client, db, email="driver@t.dev", seats=4):
    h = auth_headers(client, email, name="Dana Driver")
    user = db.query(User).filter(User.email == email).one()
    d = Driver(user_id=user.id, verification_status=VerificationStatus.APPROVED)
    db.add(d)
    db.flush()
    v = Vehicle(driver_id=d.id, make="Toyota", model="Prius", year=2021, color="Silver", license_plate="ABC 123", seats=seats)
    db.add(v)
    db.commit()
    return h, d, v


def trip_payload(vehicle_id, hour=9, minute=30, **kw):
    return {"vehicle_id": vehicle_id, "origin_address": "Vancouver", "destination_address": "Abbotsford",
            "departure_time": when(hour, minute), "available_seats": 4, "maximum_detour_minutes": 30, "minimum_earnings": 55, **kw}


def post_trio(client):
    hs = []
    for email, (o, d, h, m) in (("a@t.dev", ("Burnaby", "Abbotsford", 10, 0)), ("b@t.dev", ("Coquitlam", "Abbotsford", 9, 50)),
                                ("c@t.dev", ("Burnaby", "Langley", 10, 10))):
        hs.append(auth_headers(client, email))
        r = client.post("/ride-requests", json=ride_payload(o, d, h, m), headers=hs[-1])
        assert r.status_code == 201, r.text
    return hs
