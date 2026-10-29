"""DB-aware glue around the pure matching engine.

``rematch`` is the real-time pipeline from the spec: after any pool change it re-groups active passenger
requests, searches open driver trips for each viable group, prices the options and notifies people.
It is idempotent: groups whose membership did not change are updated in place (stable ids / no spam).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.logging import log_event
from app.db.base import utcnow
from app.models import (
    DriverTripPost, GroupStatus, Match, MatchStatus, PassengerRequest, RequestStatus, RideGroup, RideGroupMember,
    TripStatus,
)
from app.repositories.rides import GroupRepository, MatchRepository, RequestRepository, TripRepository
from app.services import matching_service as ms
from app.services import notification_service as ns
from app.services import route_service as rs
from app.services.state_machine import transition
from app.utils import polyline as pl
from app.utils.geo import Point

GEO_KEY = "geo:requests"


# --------------------------------------------------------------------------- row <-> engine data
def request_to_data(r: PassengerRequest) -> ms.RideRequestData:
    return ms.RideRequestData(
        id=r.id, user_id=r.user_id, origin=Point(r.origin_lat, r.origin_lng),
        destination=Point(r.destination_lat, r.destination_lng), preferred=r.preferred_departure,
        earliest=r.earliest_departure, latest=r.latest_departure, direct_km=r.estimated_direct_distance,
        direct_min=r.estimated_direct_duration, polyline=tuple(pl.decode(r.route_polyline)),
        passenger_count=r.passenger_count, max_detour_min=float(r.maximum_detour_minutes),
    )


def trip_to_data(t: DriverTripPost) -> ms.DriverTripData:
    return ms.DriverTripData(
        id=t.id, driver_id=t.driver.user_id if t.driver else t.driver_id, origin=Point(t.origin_lat, t.origin_lng),
        destination=Point(t.destination_lat, t.destination_lng), departure=t.departure_time, seats=t.available_seats,
        direct_km=t.estimated_distance, direct_min=t.estimated_duration, polyline=tuple(pl.decode(t.route_polyline)),
        max_detour_min=float(t.maximum_detour_minutes), min_earnings=t.minimum_earnings,
    )


def index_request(r: PassengerRequest) -> None:
    """Geospatial candidate cache (Redis GEO): quick 'how many riders near here' without touching SQL."""
    get_cache().geo_add(GEO_KEY, str(r.id), r.origin_lat, r.origin_lng)


def unindex_request(request_id: int) -> None:
    get_cache().geo_remove(GEO_KEY, str(request_id))


def riders_nearby(lat: float, lng: float, radius_km: float = 25.0) -> int:
    return len(get_cache().geo_radius(GEO_KEY, lat, lng, radius_km))


# --------------------------------------------------------------------------- plan serialisation
def _stop_dict(order: int, stop: rs.Stop, offset_min: float, depart: datetime | None, rows: dict[int, PassengerRequest]) -> dict:
    return {
        "order": order, "kind": stop.kind, "request_id": stop.request_id, "user_id": rows[stop.request_id].user_id,
        "lat": stop.point.lat, "lng": stop.point.lng, "offset_min": round(offset_min, 1),
        "eta": (depart + timedelta(minutes=offset_min)).isoformat() if depart else None,
    }


def match_plan_json(dm: ms.DriverMatch, trip: DriverTripPost, rows: dict[int, PassengerRequest]) -> dict:
    depart = trip.departure_time
    stops = [_stop_dict(i + 1, s, t, depart, rows) for i, (s, t) in enumerate(zip(dm.plan.stops, dm.plan.arrival_min))]
    via = [s.point for s in dm.plan.stops]
    route = rs.calculate_route(Point(trip.origin_lat, trip.origin_lng), Point(trip.destination_lat, trip.destination_lng), via)
    fares = {}
    for f in dm.fares:
        sv = dm.savings[f.request_id]
        fares[str(f.request_id)] = {
            "fare": f.fare, "platform_fee": f.platform_fee, "distance_part": f.distance_part, "time_part": f.time_part,
            "detour_part": f.detour_part, "benchmark": sv.solo_cost, "savings": sv.saved, "savings_percent": sv.percent,
            "detour_min": round(dm.metrics[f.request_id].detour_min, 1),
        }
    return {
        "request_ids": list(dm.request_ids), "stops": stops, "fares": fares, "route_polyline": route.polyline,
        "cost": {"lines": [{"label": k, "amount": v} for k, v in dm.cost.lines()], "total": dm.cost.total,
                 "operating_cost": dm.cost.operating_cost, "demand_multiplier": dm.cost.demand_multiplier},
        "pickup_times": {str(k): v.isoformat() for k, v in dm.pickup_times.items()},
    }


def _apply_match(row: Match, dm: ms.DriverMatch, trip: DriverTripPost, rows: dict[int, PassengerRequest]) -> None:
    row.overall_score = dm.overall
    row.scores = dict(dm.scores)
    row.total_fare = dm.payout.gross
    row.platform_fee = dm.payout.platform_fee
    row.driver_payout = dm.payout.payout
    row.driver_net_earnings = dm.payout.net_earnings
    row.added_km, row.added_min = dm.added_km, dm.driver_detour_min
    row.total_km, row.total_min = round(dm.total_km, 1), round(dm.total_min, 1)
    row.plan = match_plan_json(dm, trip, rows)


# --------------------------------------------------------------------------- the pipeline
@dataclass
class RematchResult:
    groups: int = 0
    viable_groups: int = 0
    matches: int = 0
    notified: int = 0
    group_ids: dict[int, int] = field(default_factory=dict)  # request_id -> group_id


def _headline(rows: list[PassengerRequest]) -> tuple[str, str]:
    o = max((r.origin_area for r in rows), key=[r.origin_area for r in rows].count)
    d = max((r.destination_area for r in rows), key=[r.destination_area for r in rows].count)
    return o, d


def rematch(db: Session, now: datetime | None = None) -> RematchResult:
    settings = get_settings()
    cfg, pcfg = settings.matching, settings.pricing
    now = now or utcnow()
    db.flush()  # sessions run with autoflush off; make pending status changes visible to the pool query
    reqs, trips_repo, groups_repo = RequestRepository(db), TripRepository(db), GroupRepository(db)
    reqs.expire_stale(now)
    pool_rows = reqs.active_pool(now)
    rows = {r.id: r for r in pool_rows}
    result = RematchResult()

    old_groups = groups_repo.open_groups()
    old_key = {g.id: frozenset(m.request_id for m in g.members if m.status == "active") for g in old_groups}
    old_size_of: dict[int, int] = {}
    for key in old_key.values():
        for rid in key:
            old_size_of[rid] = sum(rows[i].passenger_count for i in key if i in rows)

    data = [request_to_data(r) for r in pool_rows]
    groups = ms.create_passenger_groups(data, cfg) if data else []
    trip_rows = {t.id: t for t in trips_repo.open_for_matching(now)}
    trip_data = [trip_to_data(t) for t in trip_rows.values()]
    demand = len(pool_rows)

    kept: set[int] = set()
    for pg in groups:
        key = frozenset(pg.request_ids)
        members = [rows[i] for i in pg.request_ids]
        # keep group ids stable as groups grow/shrink: reuse the unclaimed old group with the most members in common
        best = max((g for g in old_groups if g.id not in kept), key=lambda g: len(old_key[g.id] & key), default=None)
        group = best if best is not None and old_key[best.id] & key else None
        exact = group is not None and old_key[group.id] == key
        if group is None:
            group = RideGroup(status=GroupStatus.FORMING, window_start=pg.window_start, window_end=pg.window_end,
                              suggested_departure=pg.suggested_departure)
            db.add(group)
            db.flush()
        have = {m.request_id: m for m in group.members}
        for rid, m in have.items():
            if rid not in key:
                db.delete(m)
        for r in members:
            if r.id not in have:
                db.add(RideGroupMember(group_id=group.id, request_id=r.id, user_id=r.user_id))
        db.flush()
        db.refresh(group)
        kept.add(group.id)
        group.window_start, group.window_end = pg.window_start, pg.window_end
        group.suggested_departure = pg.suggested_departure
        group.seats_used, group.seats_total = pg.seats, cfg.max_group_size
        group.avg_score = pg.avg_score
        group.origin_area, group.destination_area = _headline(members)
        cost, fares, benchmarks, savings = ms.price_group_without_driver(
            pg, pcfg, demand_count=demand, supply_seats=sum(t.seats for t in trip_data)
        )
        fare_by_id = {f.request_id: f for f in fares}
        group.estimated_total = cost.total
        group.fare_low = round(min(f.fare for f in fares) * (1 - pcfg.fare_range_pct), 2)
        group.fare_high = round(max(f.fare for f in fares) * (1 + pcfg.fare_range_pct), 2)
        seq = pg.plan.plan.sequence()
        group.plan = {"sequence": seq, "total_km": round(pg.plan.total_km, 1), "total_min": round(pg.plan.total_min, 1)}
        for m in group.members:
            if m.request_id in fare_by_id:
                m.fare_estimate = fare_by_id[m.request_id].fare
                m.benchmark_estimate = benchmarks[m.request_id]
                m.detour_min = round(pg.plan.metrics[m.request_id].detour_min, 1)
                m.status = "active"
                picks = [i for i, (rid, kind) in enumerate(seq) if rid == m.request_id and kind == "pickup"]
                drops = [i for i, (rid, kind) in enumerate(seq) if rid == m.request_id and kind == "dropoff"]
                m.pickup_order = picks[0] + 1 if picks else 0
                m.dropoff_order = drops[0] + 1 if drops else None
        for r in members:
            r.ride_group_id = group.id

        viable = pg.meets_minimum(cfg)
        proposals = ms.find_driver_for_group(pg, trip_data, cfg, pcfg, demand_count=demand)[:3] if viable and trip_data else []
        group.status = GroupStatus.DRIVER_SEARCH if viable else GroupStatus.FORMING
        result.groups += 1
        result.viable_groups += int(viable)

        existing = {m.driver_trip_id: m for m in MatchRepository(db).for_group(group.id)}
        if not exact:  # membership changed, so earlier proposals describe a different group
            for tid, m in list(existing.items()):
                db.delete(m)
                del existing[tid]
        live_trip_ids = set()
        for dm in proposals:
            trip = trip_rows[dm.trip_id]
            row = existing.get(dm.trip_id)
            if row is not None and row.status == MatchStatus.REJECTED:
                continue  # respect earlier driver rejections
            live_trip_ids.add(dm.trip_id)
            is_new = row is None
            if is_new:
                row = Match(ride_group_id=group.id, driver_trip_id=dm.trip_id, source="group", status=MatchStatus.PROPOSED)
                db.add(row)
            _apply_match(row, dm, trip, rows)
            db.flush()
            if is_new:
                result.matches += 1
                log_event("match.created", match_id=row.id, group_id=group.id, trip_id=dm.trip_id, score=dm.overall,
                          passengers=len(dm.request_ids), fare=dm.payout.gross)
                ns.notify(db, trip.driver.user_id, ns.MATCH_PROPOSED, "New passenger group",
                          f"{len(dm.request_ids)} passengers · est. earnings ${dm.payout.net_earnings:.0f}",
                          {"match_id": row.id, "trip_id": trip.id})
                result.notified += 1
        for tid, row in existing.items():
            if row.status == MatchStatus.PROPOSED and tid not in live_trip_ids:
                db.delete(row)

        live = [m for m in MatchRepository(db).for_group(group.id) if m.status == MatchStatus.PROPOSED]
        new_status = (
            RequestStatus.SEARCHING if len(members) == 1 and not viable
            else RequestStatus.DRIVER_FOUND if live
            else RequestStatus.DRIVER_SEARCH if viable
            else RequestStatus.GROUP_FOUND
        )
        for r in members:
            before = r.status
            transition("request", r, new_status)
            result.group_ids[r.id] = group.id
            prev = old_size_of.get(r.id, 0)
            now_size = pg.seats
            if now_size > prev and now_size > 1:
                if now_size >= cfg.min_group_size > prev:
                    ns.notify(db, r.user_id, ns.GROUP_READY, "Your shared ride is ready",
                              f"{now_size} riders are going your way. We're finding a driver.", {"group_id": group.id})
                elif prev <= 1:
                    ns.notify(db, r.user_id, ns.POTENTIAL_RIDERS, "Riders found on your route",
                              "Someone is heading the same way. We're building your group.", {"group_id": group.id})
                else:
                    ns.notify(db, r.user_id, ns.PASSENGER_JOINED, "A passenger joined your group",
                              f"{now_size} riders now share this trip.", {"group_id": group.id})
                result.notified += 1
            if before != new_status and new_status == RequestStatus.DRIVER_FOUND:
                ns.notify(db, r.user_id, ns.DRIVER_FOUND, "Driver found",
                          "A driver can take your group. Waiting for them to accept.", {"group_id": group.id})
            elif before != new_status and new_status == RequestStatus.DRIVER_SEARCH:
                ns.notify(db, r.user_id, ns.DRIVER_SEARCH, "Looking for a driver", "Your group is full enough. Searching now.", {"group_id": group.id})

    for group in old_groups:
        if group.id not in kept:
            for m in MatchRepository(db).for_group(group.id):
                if m.status != MatchStatus.ACCEPTED:
                    db.delete(m)
            db.query(PassengerRequest).filter(PassengerRequest.ride_group_id == group.id).update({"ride_group_id": None})
            db.flush()
            db.delete(group)  # members go with it (cascade)
    db.flush()
    log_event("rematch.done", pool=len(pool_rows), groups=result.groups, viable=result.viable_groups, matches=result.matches)
    return result


def recommend_for_trip(db: Session, trip: DriverTripPost, now: datetime | None = None, limit: int = 5) -> list[Match]:
    """Driver-posts-a-trip flow: enumerate and rank passenger combinations straight from the request pool."""
    settings = get_settings()
    cfg, pcfg = settings.matching, settings.pricing
    now = now or utcnow()
    pool = RequestRepository(db).active_pool(now)
    rows = {r.id: r for r in pool}
    repo = MatchRepository(db)
    for old in repo.for_trip(trip.id):
        if old.source == "driver_combo":
            db.delete(old)
    db.flush()
    if trip.status != TripStatus.OPEN or not pool:
        return []
    td = trip_to_data(trip)
    found = ms.recommend_groups_for_driver(td, [request_to_data(r) for r in pool], cfg, pcfg, limit=limit)
    group_match_sets = {frozenset(m.plan["request_ids"]): m for m in repo.for_trip(trip.id) if m.plan}
    out: list[Match] = []
    for dm in found:
        if frozenset(dm.request_ids) in group_match_sets:
            continue
        row = Match(ride_group_id=None, driver_trip_id=trip.id, source="driver_combo", status=MatchStatus.PROPOSED)
        db.add(row)
        _apply_match(row, dm, trip, rows)
        db.flush()
        out.append(row)
        log_event("match.created", match_id=row.id, trip_id=trip.id, source="driver_combo", score=dm.overall)
    return out


def on_new_request(db: Session, request: PassengerRequest) -> RematchResult:
    index_request(request)
    return rematch(db)


def on_new_trip(db: Session, trip: DriverTripPost) -> list[Match]:
    rematch(db)
    combos = recommend_for_trip(db, trip)
    if combos:
        ns.notify(db, trip.driver.user_id, ns.MATCH_PROPOSED, "Passengers are heading your way",
                  f"{len(combos)} recommended groups for your trip.", {"trip_id": trip.id})
    return MatchRepository(db).for_trip(trip.id)
