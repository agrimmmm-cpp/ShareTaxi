"""Ride discovery (passenger mode), demand marketplace (driver mode) and popular routes."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import PassengerRequest, RideGroup
from app.repositories.rides import GroupRepository, RequestRepository
from app.services import matching_service as ms
from app.services import pricing_service as pricing
from app.services import route_service as rs
from app.services.matching_orchestrator import request_to_data
from app.services.route_service import approximate_area
from app.utils.geo import Point


def preview_join(db: Session, group: RideGroup, newcomer: ms.RideRequestData):
    """Would ``newcomer`` fit this group? Returns (PassengerGroup, fare, benchmark) or None."""
    cfg, pcfg = get_settings().matching, get_settings().pricing
    members = [request_to_data(m.request) for m in group.members if m.status == "active"]
    if any(m.user_id == newcomer.user_id for m in members):
        return None
    for m in members:  # every member must be pairwise compatible with the newcomer
        if not ms.calculate_match_score(newcomer, m, cfg).feasible:
            return None
    pg = ms.evaluate_group(members + [newcomer], cfg)
    if pg is None:
        return None
    _, fares, benchmarks, _ = ms.price_group_without_driver(pg, pcfg)
    fare = next(f.fare for f in fares if f.request_id == newcomer.id)
    return pg, fare, benchmarks[newcomer.id]


def discover_groups(db: Session, newcomer: ms.RideRequestData, now: datetime, limit: int = 20) -> list[dict]:
    """Cards for Passenger Mode: existing forming groups this passenger could join, with their personal price."""
    pool = GroupRepository(db).discoverable(now, newcomer.earliest - timedelta(hours=1), newcomer.latest + timedelta(hours=1))
    cards = []
    for g in pool:
        res = preview_join(db, g, newcomer)
        if res is None:
            continue
        pg, fare, bench = res
        cards.append({
            "group": g, "fare": fare, "benchmark": bench, "savings": round(bench - fare, 2),
            "detour_min": round(pg.plan.metrics[newcomer.id].detour_min, 1),
            "seats_left": g.seats_total - g.seats_used,
        })
    cards.sort(key=lambda c: -c["savings"])
    return cards[:limit]


def demand_clusters(db: Session, now: datetime, bucket_hours: int = 2) -> list[dict]:
    """Reverse marketplace: where are riders waiting? Clustered by area pair and time bucket."""
    buckets: dict[tuple, list[PassengerRequest]] = defaultdict(list)
    for r in RequestRepository(db).active_pool(now):
        b = r.preferred_departure.replace(minute=0, second=0, microsecond=0)
        b = b.replace(hour=(b.hour // bucket_hours) * bucket_hours)
        buckets[(r.origin_area, r.destination_area, b)].append(r)
    out = []
    for (o, d, start), rows in buckets.items():
        seats = sum(r.passenger_count for r in rows)
        out.append({
            "origin_area": o, "destination_area": d, "passengers": seats, "requests": len(rows),
            "window_start": min(r.earliest_departure for r in rows), "window_end": max(r.latest_departure for r in rows),
            "origin_lat": rows[0].origin_lat, "origin_lng": rows[0].origin_lng,
            "destination_lat": rows[0].destination_lat, "destination_lng": rows[0].destination_lng,
            "level": "high" if seats >= 4 else "medium" if seats >= 2 else "low",
        })
    return sorted(out, key=lambda c: (-c["passengers"], c["window_start"]))


def popular_routes(db: Session, limit: int = 6) -> list[dict]:
    rows = (
        db.query(PassengerRequest.origin_area, PassengerRequest.destination_area, func.count(PassengerRequest.id).label("n"))
        .group_by(PassengerRequest.origin_area, PassengerRequest.destination_area)
        .order_by(func.count(PassengerRequest.id).desc()).limit(limit).all()
    )
    pcfg = get_settings().pricing
    out = []
    for o, d, n in rows:
        a = rs.geocode_address(o).point if o else None
        b = rs.geocode_address(d).point if d else None
        if a is None or b is None:
            continue
        r = rs.calculate_route(a, b)
        shared = round(pricing.estimate_market_benchmark(r.distance_km, r.duration_min, pcfg) * 0.35, 2)
        out.append({"origin": o, "destination": d, "requests": n, "distance_km": round(r.distance_km, 1),
                    "typical_shared_fare": shared,
                    "typical_solo_benchmark": pricing.estimate_market_benchmark(r.distance_km, r.duration_min, pcfg)})
    return out
