"""The ride-grouping engine. Pure, deterministic and DB-free so it can be unit-tested (and later swapped
for ML / OR-Tools implementations) without touching the API layer.

Pipeline
  passenger <-> passenger : calculate_match_score -> find_passenger_matches -> create_passenger_groups
  group      -> driver    : find_driver_for_group -> rank_driver_matches
  driver     -> passengers: recommend_groups_for_driver
All of them share ``evaluate_assignment`` which is the single place that checks seats, detours, time
windows, driver economics and fare competitiveness.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from app.core.config import MatchingConfig, PricingConfig, ScoreWeights
from app.services import pricing_service as pricing
from app.services import route_service as rs
from app.services.route_service import Stop, StopPlan
from app.utils.geo import Point, haversine_km, nearest_on_polyline


# --------------------------------------------------------------------------- inputs
@dataclass(frozen=True)
class RideRequestData:
    id: int
    user_id: int
    origin: Point
    destination: Point
    preferred: datetime
    earliest: datetime
    latest: datetime
    direct_km: float
    direct_min: float
    polyline: tuple[Point, ...]
    passenger_count: int = 1
    max_detour_min: float = 15.0


@dataclass(frozen=True)
class DriverTripData:
    id: int
    driver_id: int
    origin: Point
    destination: Point
    departure: datetime
    seats: int
    direct_km: float
    direct_min: float
    polyline: tuple[Point, ...]
    max_detour_min: float = 15.0
    min_earnings: float = 0.0


def build_request(
    id: int, user_id: int, origin: Point, destination: Point, preferred: datetime, flex_min: float = 30,
    passenger_count: int = 1, max_detour_min: float = 15.0,
) -> RideRequestData:
    route = rs.calculate_route(origin, destination)
    return RideRequestData(
        id, user_id, origin, destination, preferred, preferred - timedelta(minutes=flex_min),
        preferred + timedelta(minutes=flex_min), route.distance_km, route.duration_min, route.points,
        passenger_count, max_detour_min,
    )


def build_trip(
    id: int, driver_id: int, origin: Point, destination: Point, departure: datetime, seats: int,
    max_detour_min: float = 15.0, min_earnings: float = 0.0,
) -> DriverTripData:
    route = rs.calculate_route(origin, destination)
    return DriverTripData(
        id, driver_id, origin, destination, departure, seats, route.distance_km, route.duration_min,
        route.points, max_detour_min, min_earnings,
    )


# --------------------------------------------------------------------------- score components (0..1)
def _minutes(a: datetime, b: datetime) -> float:
    return (a - b).total_seconds() / 60.0


def calculate_time_compatibility(
    pref_a: datetime, earliest_a: datetime, latest_a: datetime,
    pref_b: datetime, earliest_b: datetime, latest_b: datetime, max_gap_min: float,
) -> float:
    """1.0 when both want the same minute, falling linearly to 0 at ``max_gap_min``. Zero if the
    flexibility windows do not intersect."""
    if max(earliest_a, earliest_b) > min(latest_a, latest_b):
        return 0.0
    gap = abs(_minutes(pref_a, pref_b))
    return max(0.0, 1.0 - gap / max_gap_min) if max_gap_min > 0 else float(gap == 0)


def _proximity(a: Point, b: Point, a_route: Sequence[Point], b_route: Sequence[Point], radius_km: float) -> float:
    """Closeness of two points, forgiving when one lies on the other's route (a pickup "on the way")."""
    d = min(
        haversine_km(a, b),
        nearest_on_polyline(b, a_route)[0] if len(a_route) > 1 else haversine_km(a, b),
        nearest_on_polyline(a, b_route)[0] if len(b_route) > 1 else haversine_km(a, b),
    )
    return max(0.0, 1.0 - d / radius_km)


def calculate_origin_similarity(a, b, cfg: MatchingConfig) -> float:
    return _proximity(a.origin, b.origin, a.polyline, b.polyline, cfg.origin_radius_km)


def calculate_destination_similarity(a, b, cfg: MatchingConfig) -> float:
    return _proximity(a.destination, b.destination, a.polyline, b.polyline, cfg.destination_radius_km)


def calculate_route_overlap(a, b, cfg: MatchingConfig) -> float:
    """Directional corridor overlap (0-1) of the shorter route with the longer."""
    return rs.calculate_route_overlap(a.polyline, b.polyline, cfg.corridor_km).ratio


# --------------------------------------------------------------------------- group plans & detour
@dataclass(frozen=True)
class MemberMetrics:
    request_id: int
    pickup_offset_min: float
    dropoff_offset_min: float
    onboard_min: float
    detour_min: float  # in-vehicle time minus the direct drive
    detour_contribution_min: float = 0.0  # extra delay this passenger inflicts on everyone else


@dataclass(frozen=True)
class GroupPlan:
    start_request_id: int
    plan: StopPlan
    metrics: Mapping[int, MemberMetrics]
    total_km: float
    total_min: float

    @property
    def max_detour(self) -> float:
        return max((m.detour_min for m in self.metrics.values()), default=0.0)


def _stops_for(members: Sequence[RideRequestData], skip_pickup_of: int | None = None) -> list[Stop]:
    out: list[Stop] = []
    for m in members:
        if m.id != skip_pickup_of:
            out.append(Stop(f"p{m.id}", m.id, "pickup", m.origin, m.passenger_count))
        out.append(Stop(f"d{m.id}", m.id, "dropoff", m.destination, m.passenger_count))
    return out


def _plan_key(gp: GroupPlan) -> tuple[float, float, float]:
    return (round(gp.max_detour, 1), sum(m.detour_min for m in gp.metrics.values()), gp.total_min)


def calculate_detour(members: Sequence[RideRequestData], capacity: int | None = None) -> GroupPlan:
    """Best passenger-only route: the vehicle starts at one member's pickup (whichever gives the shortest
    overall trip) and visits the rest. Returns per-passenger in-vehicle detour."""
    best: GroupPlan | None = None
    for first in members:
        plan = rs.optimize_stops(
            first.origin, _stops_for(members, first.id), None, capacity=capacity, aboard={first.id: first.passenger_count}
        )
        metrics = {}
        for m in members:
            pick = 0.0 if m.id == first.id else plan.arrival_for(m.id, "pickup")
            drop = plan.arrival_for(m.id, "dropoff")
            onboard = drop - pick
            metrics[m.id] = MemberMetrics(m.id, pick, drop, onboard, max(0.0, onboard - m.direct_min))
        cand = GroupPlan(first.id, plan, metrics, plan.total_km, plan.total_min)
        if best is None or _plan_key(cand) < _plan_key(best):
            best = cand
    assert best is not None
    return best


def _with_contributions(members: Sequence[RideRequestData], base: GroupPlan, without_fn=None) -> GroupPlan:
    """Fill ``detour_contribution_min`` = how much *others* are delayed by each member being aboard."""
    if len(members) < 2:
        return base
    contrib: dict[int, float] = {}
    for p in members:
        rest = [m for m in members if m.id != p.id]
        without = calculate_detour(rest) if without_fn is None else without_fn(rest)
        extra = sum(max(0.0, base.metrics[m.id].detour_min - without.metrics[m.id].detour_min) for m in rest)
        if without_fn is not None:  # with a driver, their own added time counts too
            extra += max(0.0, base.total_min - without.total_min)
        contrib[p.id] = extra
    metrics = {
        k: MemberMetrics(v.request_id, v.pickup_offset_min, v.dropoff_offset_min, v.onboard_min, v.detour_min, contrib[k])
        for k, v in base.metrics.items()
    }
    return GroupPlan(base.start_request_id, base.plan, metrics, base.total_km, base.total_min)


# --------------------------------------------------------------------------- scoring
@dataclass(frozen=True)
class MatchScore:
    total: float  # 0-100
    components: Mapping[str, float]  # each 0-100
    feasible: bool
    reasons: tuple[str, ...] = ()


def _combine(components: Mapping[str, float], w: ScoreWeights) -> float:
    weights = {
        "route_overlap": w.route_overlap, "time": w.time, "origin": w.origin,
        "destination": w.destination, "detour": w.detour,
    }
    norm = sum(weights.values()) or 1.0
    return round(sum(weights[k] * components[k] for k in weights) / norm, 2)


def calculate_match_score(a: RideRequestData, b: RideRequestData, cfg: MatchingConfig) -> MatchScore:
    """Compatibility (0-100) of two passenger requests, plus hard feasibility checks."""
    reasons: list[str] = []
    gap = abs(_minutes(a.preferred, b.preferred))
    if gap > cfg.max_departure_gap_min:
        reasons.append("departure_gap")
    time_c = calculate_time_compatibility(
        a.preferred, a.earliest, a.latest, b.preferred, b.earliest, b.latest, cfg.max_departure_gap_min
    )
    if time_c == 0.0 and not reasons:
        reasons.append("time_windows_disjoint")
    if a.passenger_count + b.passenger_count > cfg.max_group_size:
        reasons.append("capacity")
    overlap = calculate_route_overlap(a, b, cfg)
    if overlap < cfg.min_route_overlap:
        reasons.append("route_overlap")
    origin = calculate_origin_similarity(a, b, cfg)
    dest = calculate_destination_similarity(a, b, cfg)
    detour_c = 0.0
    if not reasons:
        gp = calculate_detour([a, b])
        if any(gp.metrics[r.id].detour_min > min(r.max_detour_min, cfg.max_passenger_detour_min) for r in (a, b)):
            reasons.append("detour")
        detour_c = max(0.0, 1.0 - gp.max_detour / cfg.max_passenger_detour_min)
    comps = {
        "route_overlap": overlap * 100, "time": time_c * 100, "origin": origin * 100,
        "destination": dest * 100, "detour": detour_c * 100,
    }
    total = _combine(comps, cfg.weights)
    return MatchScore(total, comps, not reasons and total >= cfg.score_threshold, tuple(reasons))


def find_passenger_matches(
    target: RideRequestData, pool: Sequence[RideRequestData], cfg: MatchingConfig
) -> list[tuple[RideRequestData, MatchScore]]:
    """Feasible companions for ``target`` ordered by compatibility."""
    out = []
    for cand in pool:
        if cand.id == target.id or cand.user_id == target.user_id:
            continue
        if abs(_minutes(cand.preferred, target.preferred)) > cfg.max_departure_gap_min:
            continue  # cheap pre-filter before polyline maths
        score = calculate_match_score(target, cand, cfg)
        if score.feasible:
            out.append((cand, score))
    return sorted(out, key=lambda t: (-t[1].total, t[0].id))


@dataclass(frozen=True)
class PassengerGroup:
    members: tuple[RideRequestData, ...]
    plan: GroupPlan
    avg_score: float
    window_start: datetime
    window_end: datetime
    suggested_departure: datetime

    @property
    def seats(self) -> int:
        return sum(m.passenger_count for m in self.members)

    @property
    def request_ids(self) -> tuple[int, ...]:
        return tuple(m.id for m in self.members)

    def meets_minimum(self, cfg: MatchingConfig) -> bool:
        return self.seats >= cfg.min_group_size


def evaluate_group(members: Sequence[RideRequestData], cfg: MatchingConfig, avg_score: float = 0.0) -> PassengerGroup | None:
    """Validate a candidate group as a whole: capacity, intersecting windows, everyone's detour."""
    if sum(m.passenger_count for m in members) > cfg.max_group_size:
        return None
    start = max(m.earliest for m in members)
    end = min(m.latest for m in members)
    if start > end:
        return None
    prefs = sorted(m.preferred for m in members)
    if _minutes(prefs[-1], prefs[0]) > cfg.max_departure_gap_min:
        return None
    gp = calculate_detour(members, capacity=cfg.max_group_size)
    for m in members:
        if gp.metrics[m.id].detour_min > min(m.max_detour_min, cfg.max_passenger_detour_min):
            return None
    mean_pref = prefs[0] + (prefs[-1] - prefs[0]) / 2
    return PassengerGroup(tuple(members), gp, avg_score, start, end, min(max(mean_pref, start), end))


def _avg_pair_score(members: Sequence[RideRequestData], nb: Mapping[int, Mapping[int, MatchScore]]) -> float:
    pairs = [nb[a.id][b.id].total for a, b in itertools.combinations(members, 2) if b.id in nb[a.id]]
    return round(sum(pairs) / len(pairs), 2) if pairs else 0.0


def create_passenger_groups(requests: Sequence[RideRequestData], cfg: MatchingConfig) -> list[PassengerGroup]:
    """Greedy best-first clustering. Every request ends up in exactly one group (possibly alone).

    Seeds are the requests with the most feasible neighbours; each group grows by the candidate with the
    highest mean pairwise score as long as the *whole group* stays within detour/time/seat limits, so we
    never stretch a route just to fill seats.
    """
    by_id = {r.id: r for r in requests}
    nb: dict[int, dict[int, MatchScore]] = {r.id: {} for r in requests}
    for r in requests:
        for cand, score in find_passenger_matches(r, requests, cfg):
            nb[r.id][cand.id] = score
    unassigned = set(by_id)
    groups: list[PassengerGroup] = []
    while unassigned:
        seed = max(unassigned, key=lambda i: (len(nb[i].keys() & unassigned), -by_id[i].preferred.timestamp(), -i))
        members = [by_id[seed]]
        group = evaluate_group(members, cfg) or PassengerGroup(
            tuple(members), calculate_detour(members), 0.0, members[0].earliest, members[0].latest, members[0].preferred
        )
        while True:
            ids = {m.id for m in members}
            cands = [c for c in unassigned - ids if all(c in nb[m.id] and m.id in nb[c] for m in members)]
            ranked = sorted(cands, key=lambda c: (-sum(nb[m.id][c].total for m in members) / len(members), c))
            for c in ranked:
                trial = members + [by_id[c]]
                evaluated = evaluate_group(trial, cfg, _avg_pair_score(trial, nb))
                if evaluated is not None:
                    members, group = trial, evaluated
                    break
            else:
                break
        if len(members) > 1:
            group = PassengerGroup(
                group.members, _with_contributions(members, group.plan), _avg_pair_score(members, nb),
                group.window_start, group.window_end, group.suggested_departure,
            )
        groups.append(group)
        unassigned -= {m.id for m in members}
    return sorted(groups, key=lambda g: (-g.seats, -g.avg_score, g.members[0].id))


# --------------------------------------------------------------------------- driver assignment
@dataclass(frozen=True)
class DriverMatch:
    trip_id: int
    request_ids: tuple[int, ...]
    plan: StopPlan
    metrics: Mapping[int, MemberMetrics]
    pickup_times: Mapping[int, datetime]
    dropoff_times: Mapping[int, datetime]
    seats_used: int
    seats_total: int
    driver_detour_min: float
    added_km: float
    total_km: float
    total_min: float
    cost: pricing.TripCost
    payout: pricing.DriverPayout
    fares: tuple[pricing.PassengerFare, ...]
    benchmarks: Mapping[int, float]
    savings: Mapping[int, pricing.Savings]
    scores: Mapping[str, float]
    overall: float


def score_request_against_trip(trip: DriverTripData, req: RideRequestData, cfg: MatchingConfig) -> MatchScore:
    """Compatibility of a single passenger request with a driver's planned route (0-100)."""
    reasons: list[str] = []
    overlap = rs.calculate_route_overlap(req.polyline, trip.polyline, cfg.corridor_km).a_in_b
    if overlap < cfg.min_route_overlap:
        reasons.append("route_overlap")
    est_pickup = trip.departure + timedelta(minutes=rs.calculate_route_duration(trip.origin, req.origin))
    time_c = calculate_time_compatibility(
        req.preferred, req.earliest, req.latest, est_pickup, est_pickup, est_pickup, cfg.max_departure_gap_min
    )
    if est_pickup > req.latest or est_pickup < req.earliest - timedelta(minutes=cfg.max_driver_wait_min):
        reasons.append("time_windows_disjoint")
    origin = max(0.0, 1.0 - nearest_on_polyline(req.origin, trip.polyline)[0] / cfg.origin_radius_km)
    dest = max(0.0, 1.0 - nearest_on_polyline(req.destination, trip.polyline)[0] / cfg.destination_radius_km)
    est = rs.estimate_detour(trip.origin, trip.destination, _stops_for([req]), capacity=trip.seats)
    if est.added_min > min(trip.max_detour_min, cfg.max_driver_detour_min):
        reasons.append("driver_detour")
    comps = {
        "route_overlap": overlap * 100, "time": time_c * 100, "origin": origin * 100,
        "destination": dest * 100, "detour": max(0.0, 1.0 - est.added_min / cfg.max_driver_detour_min) * 100,
    }
    return MatchScore(_combine(comps, cfg.weights), comps, not reasons, tuple(reasons))


def evaluate_assignment(
    trip: DriverTripData, members: Sequence[RideRequestData], cfg: MatchingConfig, pcfg: PricingConfig,
    *, demand_count: int = 0, supply_seats: int = 0, precise: bool = True,
) -> DriverMatch | None:
    """Can this driver serve exactly these passengers, sensibly and profitably? ``None`` if not."""
    seats = sum(m.passenger_count for m in members)
    if not members or seats > trip.seats:
        return None
    plan = rs.optimize_stops(trip.origin, _stops_for(members), trip.destination, capacity=trip.seats)

    pickup_times, dropoff_times, metrics = {}, {}, {}
    wait = 0.0
    for m in members:
        pick_off = plan.arrival_for(m.id, "pickup")
        drop_off = plan.arrival_for(m.id, "dropoff")
        pick_t = trip.departure + timedelta(minutes=pick_off)
        if pick_t > m.latest:
            return None  # driver would arrive after the passenger's window closes
        early = _minutes(m.earliest, pick_t)
        if early > cfg.max_driver_wait_min:
            return None
        wait = max(wait, early, 0.0)
        onboard = drop_off - pick_off
        detour = max(0.0, onboard - m.direct_min)
        if detour > min(m.max_detour_min, cfg.max_passenger_detour_min):
            return None
        shift = timedelta(minutes=max(0.0, early))
        pickup_times[m.id] = pick_t + shift
        dropoff_times[m.id] = trip.departure + timedelta(minutes=drop_off) + shift
        metrics[m.id] = MemberMetrics(m.id, pick_off, drop_off, onboard, detour)

    total_min = plan.total_min + wait
    driver_detour = max(0.0, total_min - trip.direct_min)
    if driver_detour > min(trip.max_detour_min, cfg.max_driver_detour_min):
        return None
    added_km = max(0.0, plan.total_km - trip.direct_km)

    if precise and len(members) > 1:
        def without(rest):
            p = rs.optimize_stops(trip.origin, _stops_for(rest), trip.destination, capacity=trip.seats)
            mm = {}
            for m in rest:
                pk, dr = p.arrival_for(m.id, "pickup"), p.arrival_for(m.id, "dropoff")
                mm[m.id] = MemberMetrics(m.id, pk, dr, dr - pk, max(0.0, dr - pk - m.direct_min))
            return GroupPlan(rest[0].id, p, mm, p.total_km, p.total_min)

        metrics = _with_contributions(members, GroupPlan(members[0].id, plan, metrics, plan.total_km, total_min), without).metrics

    cost = pricing.estimate_trip_cost(
        pricing.TripCostInputs(plan.total_km, total_min, len(members), driver_detour, demand_count, supply_seats, trip.min_earnings),
        pcfg,
    )
    payout = pricing.calculate_driver_payout(cost.total, cost.operating_cost, pcfg)
    if payout.net_earnings < trip.min_earnings - 0.01:
        return None
    fares = pricing.calculate_passenger_share(
        cost.total,
        [pricing.PassengerShareInput(m.id, m.direct_km, metrics[m.id].onboard_min, metrics[m.id].detour_contribution_min, m.passenger_count) for m in members],
        pcfg,
    )
    benchmarks = {m.id: pricing.estimate_market_benchmark(m.direct_km, m.direct_min, pcfg) * m.passenger_count for m in members}
    fare_by_id = {f.request_id: f for f in fares}
    if any(fare_by_id[m.id].fare > benchmarks[m.id] * pcfg.max_fraction_of_benchmark for m in members):
        return None  # not competitive enough to be worth offering
    savings = {m.id: pricing.calculate_savings(fare_by_id[m.id].fare, benchmarks[m.id]) for m in members}

    route_c = sum(score_request_against_trip(trip, m, cfg).total for m in members) / len(members)
    hourly = payout.net_earnings / max(total_min / 60.0, 0.25)
    profit_c = min(100.0, 100.0 * hourly / cfg.target_driver_hourly)
    avg_saving = sum(s.percent for s in savings.values()) / len(savings) / 100.0
    save_c = min(100.0, 100.0 * avg_saving / cfg.target_savings_ratio)
    seat_c = 100.0 * seats / trip.seats
    completion_c = min(95.0, 60.0 + 12.0 * len(members) + 0.15 * route_c)
    w = cfg.driver_rank_weights
    norm = w.route_compatibility + w.profitability + w.passenger_savings + w.seat_utilization + w.completion_probability
    overall = round(
        (w.route_compatibility * route_c + w.profitability * profit_c + w.passenger_savings * save_c
         + w.seat_utilization * seat_c + w.completion_probability * completion_c) / norm, 1,
    )
    scores = {
        "route_compatibility": round(route_c, 1), "driver_profitability": round(profit_c, 1),
        "passenger_savings": round(save_c, 1), "seat_utilization": round(seat_c, 1),
        "completion_probability": round(completion_c, 1),
    }
    return DriverMatch(
        trip.id, tuple(m.id for m in members), plan, metrics, pickup_times, dropoff_times, seats, trip.seats,
        round(driver_detour, 1), round(added_km, 1), plan.total_km, total_min, cost, payout, tuple(fares),
        benchmarks, savings, scores, overall,
    )


def rank_driver_matches(matches: Sequence[DriverMatch]) -> list[DriverMatch]:
    return sorted(matches, key=lambda m: (-m.overall, -m.seats_used, m.driver_detour_min, m.trip_id))


def find_driver_for_group(
    group: PassengerGroup, trips: Sequence[DriverTripData], cfg: MatchingConfig, pcfg: PricingConfig,
    *, demand_count: int = 0,
) -> list[DriverMatch]:
    supply = sum(t.seats for t in trips)
    out = []
    for trip in trips:
        if abs(_minutes(trip.departure, group.suggested_departure)) > cfg.max_departure_gap_min + 60:
            continue  # hopelessly far apart in time; skip before routing
        m = evaluate_assignment(trip, group.members, cfg, pcfg, demand_count=demand_count, supply_seats=supply)
        if m:
            out.append(m)
    return rank_driver_matches(out)


def recommend_groups_for_driver(
    trip: DriverTripData, requests: Sequence[RideRequestData], cfg: MatchingConfig, pcfg: PricingConfig,
    *, limit: int = 5, demand_count: int | None = None,
) -> list[DriverMatch]:
    """Best passenger combinations for a driver's planned trip (reverse marketplace)."""
    cands = []
    for r in requests:
        if r.user_id == trip.driver_id:
            continue
        s = score_request_against_trip(trip, r, cfg)
        if s.feasible and s.total >= cfg.score_threshold * 0.8:
            cands.append((s.total, r))
    cands.sort(key=lambda t: (-t[0], t[1].id))
    top = [r for _, r in cands[: cfg.max_combo_candidates]]
    demand = len(requests) if demand_count is None else demand_count
    found: list[DriverMatch] = []
    for k in range(1, min(trip.seats, len(top)) + 1):
        for combo in itertools.combinations(top, k):
            if sum(c.passenger_count for c in combo) > trip.seats:
                continue
            if _minutes(max(c.preferred for c in combo), min(c.preferred for c in combo)) > cfg.max_departure_gap_min:
                continue
            m = evaluate_assignment(trip, combo, cfg, pcfg, demand_count=demand, supply_seats=trip.seats, precise=False)
            if m:
                found.append(m)
    by_id = {r.id: r for r in top}
    final = []
    for m in rank_driver_matches(found)[:limit]:  # re-price the short list with fairness-aware shares
        precise = evaluate_assignment(
            trip, [by_id[i] for i in m.request_ids], cfg, pcfg, demand_count=demand, supply_seats=trip.seats
        )
        final.append(precise or m)
    return rank_driver_matches(final)


def price_group_without_driver(
    group: PassengerGroup, pcfg: PricingConfig, *, demand_count: int = 0, supply_seats: int = 0
):
    """Indicative fares for a forming group (before any driver is attached)."""
    gp = group.plan
    cost = pricing.estimate_trip_cost(
        pricing.TripCostInputs(gp.total_km, gp.total_min, len(group.members), gp.max_detour, demand_count, supply_seats), pcfg
    )
    fares = pricing.calculate_passenger_share(
        cost.total,
        [
            pricing.PassengerShareInput(
                m.id, m.direct_km, gp.metrics[m.id].onboard_min, gp.metrics[m.id].detour_contribution_min, m.passenger_count
            )
            for m in group.members
        ],
        pcfg,
    )
    benchmarks = {m.id: pricing.estimate_market_benchmark(m.direct_km, m.direct_min, pcfg) * m.passenger_count for m in group.members}
    savings = {f.request_id: pricing.calculate_savings(f.fare, benchmarks[f.request_id]) for f in fares}
    return cost, fares, benchmarks, savings
