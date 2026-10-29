"""Google encoded-polyline codec (precision 5) so routes are stored compactly in the database."""
from __future__ import annotations

from typing import Sequence

from app.utils.geo import Point


def encode(points: Sequence[Point], precision: int = 5) -> str:
    factor = 10**precision
    out: list[str] = []
    prev_lat = prev_lng = 0
    for p in points:
        lat, lng = round(p.lat * factor), round(p.lng * factor)
        for delta in (lat - prev_lat, lng - prev_lng):
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev_lat, prev_lng = lat, lng
    return "".join(out)


def decode(encoded: str, precision: int = 5) -> list[Point]:
    factor = 10**precision
    pts: list[Point] = []
    i = lat = lng = 0
    while i < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(encoded[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lng += deltas[1]
        pts.append(Point(lat / factor, lng / factor))
    return pts
