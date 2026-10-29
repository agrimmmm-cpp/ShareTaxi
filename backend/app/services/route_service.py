"""Routing, geocoding, polyline comparison and stop sequencing.

Providers are pluggable: ``offline`` (road skeleton + Dijkstra, no keys needed) and ``osrm``.
Everything above the provider (overlap, detour, optimisation) is provider-agnostic.
"""
from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal, Protocol, Sequence

import httpx

from app.core.config import get_settings
from app.services import geodata
from app.utils import polyline as polyline_codec
from app.utils.geo import (
    Point,
    cumulative_km,
    haversine_km,
    nearest_on_polyline,
    polyline_length_km,
    resample,
)

DWELL_MIN = 1.0  # curbside stop time at each pickup / drop-off


# --------------------------------------------------------------------------- types
@dataclass(frozen=True)
class Route:
    distance_km: float
    duration_min: float
    points: tuple[Point, ...]

    @property
    def polyline(self) -> str:
        return polyline_codec.encode(self.points)


@dataclass(frozen=True)
class GeocodedPlace:
    name: str
    point: Point


@dataclass(frozen=True)
class RouteOverlap:
    ratio: float  # shared length / length of the shorter route (0-1)
    shared_km: float
    a_in_b: float  # fraction of route A running along route B (in the same direction)
    b_in_a: float


@dataclass(frozen=True)
class Stop:
    key: str
    request_id: int
    kind: Literal["pickup", "dropoff"]
    point: Point
    party_size: int = 1


@dataclass(frozen=True)
class StopPlan:
    """An ordered visiting sequence with timings measured from the start point (minutes)."""

    stops: tuple[Stop, ...]
    arrival_min: tuple[float, ...]  # arrival (incl. dwell of earlier stops) at each stop
    total_km: float
    total_min: float
    strategy: str

    def arrival_for(self, request_id: int, kind: str) -> float:
        for s, t in zip(self.stops, self.arrival_min):
            if s.request_id == request_id and s.kind == kind:
                return t
        raise KeyError((request_id, kind))

    def onboard_min(self, request_id: int) -> float:
        return self.arrival_for(request_id, "dropoff") - self.arrival_for(request_id, "pickup")

    def sequence(self) -> list[tuple[int, str]]:
        return [(s.request_id, s.kind) for s in self.stops]


@dataclass(frozen=True)
class DetourEstimate:
    direct_km: float
    direct_min: float
    via_km: float
    via_min: float
    plan: StopPlan

    @property
    def added_km(self) -> float:
        return max(0.0, self.via_km - self.direct_km)

    @property
    def added_min(self) -> float:
        return max(0.0, self.via_min - self.direct_min)


class GeocodeError(ValueError):
    pass


# --------------------------------------------------------------------------- providers
class RoutingProvider(Protocol):
    name: str

    def route(self, origin: Point, destination: Point) -> Route: ...


class OfflineRoadNetworkProvider:
    """Shortest-time path over a small hand-built highway skeleton; falls back to a direct line
    when a point is far from the network."""

    name = "offline"
    snap_radius_km = 30.0

    def __init__(self) -> None:
        self._adj: dict[str, list[tuple[str, float, float]]] = {n: [] for n in geodata.NODES}
        for a, b, kind in geodata.EDGES:
            km = haversine_km(geodata.NODES[a], geodata.NODES[b]) * geodata.ROAD_FACTOR[kind]
            minutes = km / geodata.SPEED_KMH[kind] * 60
            self._adj[a].append((b, km, minutes))
            self._adj[b].append((a, km, minutes))

    def route(self, origin: Point, destination: Point) -> Route:
        nodes = geodata.NODES
        adj = {k: list(v) for k, v in self._adj.items()}
        adj["__o"], adj["__d"] = [], []

        def local(p: Point, tag: str) -> int:
            near = sorted(nodes, key=lambda n: haversine_km(p, nodes[n]))[:3]
            linked = 0
            for n in near:
                d = haversine_km(p, nodes[n])
                if d > self.snap_radius_km:
                    continue
                km = d * geodata.LOCAL_ROAD_FACTOR
                mins = km / geodata.LOCAL_SPEED_KMH * 60
                adj[tag].append((n, km, mins))
                adj[n].append((tag, km, mins))
                linked += 1
            return linked

        linked = local(origin, "__o") + local(destination, "__d")
        direct_km = haversine_km(origin, destination)
        if linked < 2 or direct_km < 1.5:  # off-network or trivially short: straight-ish drive
            km = direct_km * geodata.LOCAL_ROAD_FACTOR
            speed = 40.0 if direct_km < 15 else 70.0
            return Route(km, km / speed * 60, (origin, destination))

        coords = {**nodes, "__o": origin, "__d": destination}
        dist: dict[str, tuple[float, float]] = {"__o": (0.0, 0.0)}  # minutes, km
        prev: dict[str, str] = {}
        heap = [(0.0, "__o")]
        while heap:
            t, u = heapq.heappop(heap)
            if t > dist[u][0]:
                continue
            if u == "__d":
                break
            for v, km, mins in adj[u]:
                nt = t + mins
                if v not in dist or nt < dist[v][0]:
                    dist[v] = (nt, dist[u][1] + km)
                    prev[v] = u
                    heapq.heappush(heap, (nt, v))
        if "__d" not in dist:
            km = direct_km * geodata.LOCAL_ROAD_FACTOR
            return Route(km, km / 60 * 60, (origin, destination))
        path, cur = ["__d"], "__d"
        while cur != "__o":
            cur = prev[cur]
            path.append(cur)
        pts = tuple(coords[n] for n in reversed(path))
        return Route(dist["__d"][1], dist["__d"][0], pts)


class OsrmProvider:
    name = "osrm"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._fallback = OfflineRoadNetworkProvider()

    def route(self, origin: Point, destination: Point) -> Route:
        url = (
            f"{self.base_url}/route/v1/driving/{origin.lng},{origin.lat};{destination.lng},{destination.lat}"
            "?overview=full&geometries=polyline"
        )
        try:
            data = httpx.get(url, timeout=8).json()
            r = data["routes"][0]
            return Route(r["distance"] / 1000, r["duration"] / 60, tuple(polyline_codec.decode(r["geometry"])))
        except Exception:  # network/provider failure must never break matching
            return self._fallback.route(origin, destination)


@lru_cache(maxsize=1)
def get_provider() -> RoutingProvider:
    s = get_settings()
    return OsrmProvider(s.osrm_url) if s.routing_provider == "osrm" else OfflineRoadNetworkProvider()


# --------------------------------------------------------------------------- geocoding
def _norm(text: str) -> str:
    return " ".join(text.lower().replace(",", " ").split())


def geocode_address(query: str) -> GeocodedPlace:
    """Resolve free text to a place. Gazetteer first; Nominatim fallback when enabled."""
    q = _norm(query)
    if not q:
        raise GeocodeError("empty address")
    for name, pt in geodata.PLACES.items():
        if _norm(name) in q:
            return GeocodedPlace(name, pt)
    for alias in sorted(geodata.ALIASES, key=len, reverse=True):
        if alias in q:
            name = geodata.ALIASES[alias]
            return GeocodedPlace(name, geodata.PLACES[name])
    if get_settings().geocoder == "nominatim":
        try:
            r = httpx.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1},
                headers={"User-Agent": "ShareTaxi/0.1"},
                timeout=8,
            ).json()
            if r:
                return GeocodedPlace(r[0]["display_name"], Point(float(r[0]["lat"]), float(r[0]["lon"])))
        except Exception:
            pass
    raise GeocodeError(f"could not geocode {query!r}")


def approximate_area(p: Point) -> str:
    """Privacy helper: neighbourhood-level label instead of an exact address."""
    return min(geodata.PLACES, key=lambda n: haversine_km(p, geodata.PLACES[n]))


# --------------------------------------------------------------------------- routes
_route_cache = None  # optional shared cache (Redis) injected at start-up


def set_route_cache(cache) -> None:
    global _route_cache
    _route_cache = cache


def _key(p: Point) -> tuple[float, float]:
    return round(p.lat, 4), round(p.lng, 4)


@lru_cache(maxsize=20000)
def _route_cached(o: tuple[float, float], d: tuple[float, float]) -> Route:
    ckey = f"route:{o[0]},{o[1]}:{d[0]},{d[1]}"
    if _route_cache is not None:
        hit = _route_cache.get_json(ckey)
        if hit:
            return Route(hit["km"], hit["min"], tuple(polyline_codec.decode(hit["poly"])))
    route = get_provider().route(Point(*o), Point(*d))
    if _route_cache is not None:
        _route_cache.set_json(ckey, {"km": route.distance_km, "min": route.duration_min, "poly": route.polyline}, 86400)
    return route


def calculate_route(origin: Point, destination: Point, via: Sequence[Point] = ()) -> Route:
    waypoints = [origin, *via, destination]
    legs = [_route_cached(_key(a), _key(b)) for a, b in zip(waypoints, waypoints[1:])]
    if len(legs) == 1:
        return legs[0]
    pts: list[Point] = []
    for leg in legs:
        pts.extend(leg.points if not pts else leg.points[1:])
    return Route(sum(l.distance_km for l in legs), sum(l.duration_min for l in legs), tuple(pts))


def calculate_route_distance(origin: Point, destination: Point) -> float:
    return calculate_route(origin, destination).distance_km


def calculate_route_duration(origin: Point, destination: Point) -> float:
    return calculate_route(origin, destination).duration_min


# --------------------------------------------------------------------------- overlap
def _fraction_along(sample: Sequence[Point], ref: Sequence[Point], ref_cum: Sequence[float], corridor_km: float):
    """Fraction of ``sample`` (resampled A) lying inside the corridor around ``ref`` in ref's direction."""
    hits: list[tuple[int, float]] = []
    for i, p in enumerate(sample):
        d, along = nearest_on_polyline(p, ref, ref_cum)
        if d <= corridor_km:
            hits.append((i, along))
    if len(hits) < 2 or hits[-1][1] - hits[0][1] <= 0.5:  # not travelling the same direction
        return 0.0, 0.0
    seg_km = polyline_length_km(sample) / max(1, len(sample) - 1)
    shared = 0.0
    for (i, a1), (j, a2) in zip(hits, hits[1:]):
        if j == i + 1 and a2 >= a1 - 0.5:
            shared += seg_km
    total = seg_km * (len(sample) - 1)
    return (shared / total if total else 0.0), shared


def calculate_route_overlap(a: Sequence[Point], b: Sequence[Point], corridor_km: float = 5.0) -> RouteOverlap:
    """Directional corridor overlap between two route polylines."""
    if len(a) < 2 or len(b) < 2:
        return RouteOverlap(0.0, 0.0, 0.0, 0.0)
    ra, rb = resample(a, 1.5), resample(b, 1.5)
    a_in_b, shared_a = _fraction_along(ra, b, cumulative_km(b), corridor_km)
    b_in_a, shared_b = _fraction_along(rb, a, cumulative_km(a), corridor_km)
    len_a, len_b = polyline_length_km(a), polyline_length_km(b)
    shared = max(shared_a, shared_b)
    ratio = min(1.0, shared / min(len_a, len_b)) if min(len_a, len_b) > 0 else 0.0
    return RouteOverlap(ratio, shared, a_in_b, b_in_a)


# --------------------------------------------------------------------------- stop sequencing
def _leg(a: Point, b: Point) -> tuple[float, float]:
    r = _route_cached(_key(a), _key(b))
    return r.distance_km, r.duration_min


def evaluate_sequence(
    start: Point, seq: Sequence[Stop], end: Point | None = None
) -> tuple[float, float, tuple[float, ...]]:
    km = minutes = 0.0
    cur = start
    arrivals: list[float] = []
    for i, s in enumerate(seq):
        dk, dm = _leg(cur, s.point)
        km += dk
        minutes += dm
        arrivals.append(minutes)
        minutes += DWELL_MIN
        cur = s.point
    if end is not None:
        dk, dm = _leg(cur, end)
        km += dk
        minutes += dm
    return km, minutes, tuple(arrivals)


def _valid(seq: Sequence[Stop], capacity: int | None, aboard: dict[int, int] | None = None) -> bool:
    onboard = sum((aboard or {}).values())
    picked: set[int] = set(aboard or {})
    for s in seq:
        if s.kind == "pickup":
            picked.add(s.request_id)
            onboard += s.party_size
            if capacity is not None and onboard > capacity:
                return False
        else:
            if s.request_id not in picked:
                return False
            onboard -= s.party_size
    return True


def optimize_stops(
    start: Point,
    stops: Sequence[Stop],
    end: Point | None = None,
    *,
    capacity: int | None = None,
    improve: bool = True,
    aboard: dict[int, int] | None = None,
) -> StopPlan:
    """Nearest-neighbour sequencing with pickup-before-dropoff and capacity constraints, followed by an
    optional relocate-improvement pass. The ``StopPlan`` shape is solver-agnostic so an OR-Tools VRP
    solver can replace this function without touching callers."""
    remaining = list(stops)
    picked: set[int] = set(aboard or {})  # request_id -> party size already in the vehicle at ``start``
    onboard = sum((aboard or {}).values())
    seq: list[Stop] = []
    cur = start
    while remaining:
        avail = [
            s for s in remaining
            if (s.kind == "pickup" and (capacity is None or onboard + s.party_size <= capacity))
            or (s.kind == "dropoff" and s.request_id in picked)
        ]
        if not avail:  # capacity deadlock: force a drop-off or fail loudly
            avail = [s for s in remaining if s.kind == "dropoff" and s.request_id in picked]
            if not avail:
                raise ValueError("stops cannot be sequenced within capacity")
        nxt = min(avail, key=lambda s: _leg(cur, s.point)[1])
        seq.append(nxt)
        remaining.remove(nxt)
        cur = nxt.point
        if nxt.kind == "pickup":
            picked.add(nxt.request_id)
            onboard += nxt.party_size
        else:
            onboard -= nxt.party_size
    strategy = "nearest_neighbor"
    km, minutes, arrivals = evaluate_sequence(start, seq, end)
    if improve and len(seq) > 2:
        improved = True
        while improved:
            improved = False
            for i, j in itertools.permutations(range(len(seq)), 2):
                cand = list(seq)
                cand.insert(j, cand.pop(i))
                if not _valid(cand, capacity, aboard):
                    continue
                ck, cm, ca = evaluate_sequence(start, cand, end)
                if cm < minutes - 0.05:
                    seq, km, minutes, arrivals, improved = cand, ck, cm, ca, True
                    strategy = "nearest_neighbor+relocate"
                    break
    return StopPlan(tuple(seq), arrivals, km, minutes, strategy)


def estimate_detour(
    start: Point, end: Point, stops: Sequence[Stop], *, capacity: int | None = None
) -> DetourEstimate:
    """How much longer is start -> stops -> end than driving start -> end directly."""
    direct_km, direct_min = _leg(start, end)
    plan = optimize_stops(start, stops, end, capacity=capacity)
    return DetourEstimate(direct_km, direct_min, plan.total_km, plan.total_min, plan)


def route_efficiency(plan: StopPlan, direct_min: float) -> float:
    """0-100 score of how little a plan deviates from the direct drive (route scoring for the MVP)."""
    if plan.total_min <= 0:
        return 100.0
    return max(0.0, min(100.0, 100.0 * direct_min / plan.total_min))
