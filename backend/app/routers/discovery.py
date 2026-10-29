from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.db.base import utcnow
from app.db.session import get_db
from app.models import User
from app.schemas.rides import RideGroupOut
from app.services import discovery_service, matching_service as ms, posting_service as posting, pricing_service as pricing
from app.services import presenters, route_service as rs
from app.utils.time import to_naive_utc

router = APIRouter(tags=["discovery"])


class QuoteIn(BaseModel):
    origin_address: str
    origin_lat: float | None = None
    origin_lng: float | None = None
    destination_address: str
    destination_lat: float | None = None
    destination_lng: float | None = None
    passenger_count: int = Field(default=1, ge=1, le=4)


@router.post("/quote")
def quote(q: QuoteIn, _: User = Depends(get_current_user)):
    """Home-screen estimate: solo benchmark vs what a 3-rider shared trip typically costs."""
    try:
        o, _a = posting.resolve_point(q.origin_address, q.origin_lat, q.origin_lng)
        d, _b = posting.resolve_point(q.destination_address, q.destination_lat, q.destination_lng)
    except posting.PostingError as exc:
        raise HTTPException(422, str(exc))
    route = rs.calculate_route(o, d)
    pcfg = get_settings().pricing
    solo = pricing.estimate_market_benchmark(route.distance_km, route.duration_min, pcfg) * q.passenger_count
    cost = pricing.estimate_trip_cost(pricing.TripCostInputs(route.distance_km, route.duration_min, 3, 5.0), pcfg)
    shared = round(cost.total / 3 * q.passenger_count, 2)
    sv = pricing.calculate_savings(shared, solo)
    return {"distance_km": round(route.distance_km, 1), "duration_min": round(route.duration_min), "solo_benchmark": solo,
            "typical_shared_fare": shared, "savings": sv.saved, "savings_percent": sv.percent,
            "polyline": route.polyline, "origin_area": rs.approximate_area(o), "destination_area": rs.approximate_area(d)}


@router.get("/geocode")
def geocode(q: str = Query(min_length=2), _: User = Depends(get_current_user)):
    try:
        p = rs.geocode_address(q)
    except rs.GeocodeError as exc:
        raise HTTPException(404, str(exc))
    return {"name": p.name, "lat": p.point.lat, "lng": p.point.lng}


@router.get("/places")
def places(_: User = Depends(get_current_user)):
    from app.services.geodata import PLACES
    return [{"name": n, "lat": p.lat, "lng": p.lng} for n, p in PLACES.items()]


@router.get("/explore/rides")
def explore(origin_address: str, destination_address: str, departure: datetime, flexible_minutes: int = 30,
            passenger_count: int = 1, origin_lat: float | None = None, origin_lng: float | None = None,
            destination_lat: float | None = None, destination_lng: float | None = None,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Passenger Mode: rides already forming that fit this journey, each priced for *you*."""
    try:
        o, _a = posting.resolve_point(origin_address, origin_lat, origin_lng)
        d, _b = posting.resolve_point(destination_address, destination_lat, destination_lng)
    except posting.PostingError as exc:
        raise HTTPException(422, str(exc))
    when = to_naive_utc(departure)
    me = ms.build_request(-1, user.id, o, d, when, flexible_minutes, passenger_count, get_settings().matching.max_passenger_detour_min)
    cards = discovery_service.discover_groups(db, me, utcnow())
    return [
        {**presenters.serialize_group(db, c["group"], user).model_dump(mode="json"), "your_fare": c["fare"],
         "solo_benchmark": c["benchmark"], "your_savings": c["savings"], "pickup_deviation_min": c["detour_min"]}
        for c in cards
    ]


@router.get("/demand")
def demand(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Driver Mode / reverse marketplace: where riders are waiting right now."""
    return discovery_service.demand_clusters(db, utcnow())


@router.get("/popular-routes")
def popular(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return discovery_service.popular_routes(db)
