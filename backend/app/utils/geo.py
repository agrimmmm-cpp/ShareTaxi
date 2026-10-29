"""Small, dependency-free geometry helpers (WGS84, local equirectangular approximations)."""
from __future__ import annotations

import math
from typing import NamedTuple, Sequence

EARTH_RADIUS_KM = 6371.0088


class Point(NamedTuple):
    lat: float
    lng: float


def haversine_km(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlng = math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def polyline_length_km(poly: Sequence[Point]) -> float:
    return sum(haversine_km(poly[i], poly[i + 1]) for i in range(len(poly) - 1))


def cumulative_km(poly: Sequence[Point]) -> list[float]:
    out = [0.0]
    for i in range(len(poly) - 1):
        out.append(out[-1] + haversine_km(poly[i], poly[i + 1]))
    return out


def _xy(p: Point, ref_lat: float) -> tuple[float, float]:
    return p.lng * 111.320 * math.cos(math.radians(ref_lat)), p.lat * 110.574


def nearest_on_polyline(
    p: Point, poly: Sequence[Point], cum: Sequence[float] | None = None
) -> tuple[float, float]:
    """Return (distance_km, distance_along_polyline_km) of the closest point on ``poly`` to ``p``."""
    if not poly:
        raise ValueError("empty polyline")
    if len(poly) == 1:
        return haversine_km(p, poly[0]), 0.0
    cum = cum or cumulative_km(poly)
    px, py = _xy(p, p.lat)
    best = (math.inf, 0.0)
    for i in range(len(poly) - 1):
        ax, ay = _xy(poly[i], p.lat)
        bx, by = _xy(poly[i + 1], p.lat)
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
        d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
        if d < best[0]:
            best = (d, cum[i] + t * (cum[i + 1] - cum[i]))
    return best


def resample(poly: Sequence[Point], step_km: float) -> list[Point]:
    """Return points spaced roughly ``step_km`` apart along the polyline (endpoints included)."""
    if len(poly) < 2:
        return list(poly)
    cum = cumulative_km(poly)
    total = cum[-1]
    if total == 0:
        return [poly[0]]
    n = max(1, math.ceil(total / step_km))
    out: list[Point] = []
    seg = 0
    for k in range(n + 1):
        target = total * k / n
        while seg < len(poly) - 2 and cum[seg + 1] < target:
            seg += 1
        span = cum[seg + 1] - cum[seg]
        t = 0.0 if span == 0 else (target - cum[seg]) / span
        out.append(
            Point(
                poly[seg].lat + t * (poly[seg + 1].lat - poly[seg].lat),
                poly[seg].lng + t * (poly[seg + 1].lng - poly[seg].lng),
            )
        )
    return out


def bounding_box(points: Sequence[Point], pad_km: float = 0.0) -> tuple[float, float, float, float]:
    """(min_lat, min_lng, max_lat, max_lng) padded by ``pad_km``."""
    lats = [p.lat for p in points]
    lngs = [p.lng for p in points]
    mid = sum(lats) / len(lats)
    dlat = pad_km / 110.574
    dlng = pad_km / (111.320 * max(0.1, math.cos(math.radians(mid))))
    return min(lats) - dlat, min(lngs) - dlng, max(lats) + dlat, max(lngs) + dlng
