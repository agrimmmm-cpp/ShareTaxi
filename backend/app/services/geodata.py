"""Static gazetteer + road skeleton for Metro Vancouver / Fraser Valley.

Used by the offline routing provider and geocoder so the whole product works (and tests are
deterministic) with no API keys. Production swaps in OSRM / Google / Mapbox via ``route_service``.
"""
from __future__ import annotations

from app.utils.geo import Point

# name -> (lat, lng). Names double as the "approximate area" labels shown to other passengers.
PLACES: dict[str, Point] = {
    "Downtown Vancouver": Point(49.2827, -123.1207),
    "Vancouver East": Point(49.2815, -123.0250),
    "Broadway-Commercial": Point(49.2625, -123.0695),
    "UBC": Point(49.2606, -123.2460),
    "YVR Airport": Point(49.1967, -123.1815),
    "Richmond": Point(49.1666, -123.1336),
    "Metrotown": Point(49.2276, -123.0076),
    "Brentwood": Point(49.2663, -123.0003),
    "SFU Burnaby": Point(49.2781, -122.9199),
    "Lougheed": Point(49.2488, -122.8970),
    "New Westminster": Point(49.2057, -122.9110),
    "Coquitlam Centre": Point(49.2776, -122.8010),
    "Port Moody": Point(49.2837, -122.8312),
    "Surrey Central": Point(49.1913, -122.8490),
    "Guildford": Point(49.1906, -122.8007),
    "Delta": Point(49.1470, -122.9100),
    "White Rock": Point(49.0253, -122.8026),
    "Langley": Point(49.1520, -122.6600),
    "Maple Ridge": Point(49.2194, -122.5984),
    "Abbotsford": Point(49.0504, -122.3045),
    "Chilliwack": Point(49.1579, -121.9514),
}

# Aliases used by geocode_address (lower-case substring -> canonical place).
ALIASES: dict[str, str] = {
    "sfu": "SFU Burnaby",
    "simon fraser": "SFU Burnaby",
    "burnaby mountain": "SFU Burnaby",
    "burnaby": "Lougheed",
    "vancouver": "Downtown Vancouver",
    "downtown": "Downtown Vancouver",
    "yvr": "YVR Airport",
    "airport": "YVR Airport",
    "ubc": "UBC",
    "coquitlam": "Coquitlam Centre",
    "surrey": "Surrey Central",
    "new west": "New Westminster",
    "metro town": "Metrotown",
}

# Non-place junction nodes that make highway routes look and behave like real ones.
JUNCTIONS: dict[str, Point] = {
    "Hwy1 Brunette": Point(49.2590, -122.8950),
    "Hwy1 Port Mann": Point(49.2150, -122.8120),
    "Hwy1 Surrey": Point(49.1930, -122.7450),
    "Hwy1 Langley": Point(49.1740, -122.6600),
    "Hwy1 Aldergrove": Point(49.1330, -122.4850),
    "Hwy1 Abbotsford": Point(49.0575, -122.3350),
    "Hwy1 Sumas": Point(49.0900, -122.1500),
    "Hwy1 Chilliwack": Point(49.1450, -122.0200),
    "Hwy99 Massey": Point(49.1200, -123.0620),
}

NODES: dict[str, Point] = {**PLACES, **JUNCTIONS}

HWY, ART, CONN = "hwy", "art", "conn"
EDGES: list[tuple[str, str, str]] = [
    ("Downtown Vancouver", "Vancouver East", ART), ("Downtown Vancouver", "Broadway-Commercial", ART),
    ("Downtown Vancouver", "YVR Airport", ART), ("Downtown Vancouver", "UBC", ART),
    ("UBC", "Broadway-Commercial", ART), ("Broadway-Commercial", "Metrotown", ART),
    ("Broadway-Commercial", "Vancouver East", ART), ("YVR Airport", "Richmond", ART),
    ("Richmond", "Metrotown", ART), ("Richmond", "Hwy99 Massey", HWY),
    ("Hwy99 Massey", "Delta", HWY), ("Delta", "New Westminster", HWY), ("Delta", "Surrey Central", ART),
    ("Hwy99 Massey", "Surrey Central", HWY), ("Vancouver East", "Brentwood", HWY),
    ("Brentwood", "Hwy1 Brunette", HWY), ("Brentwood", "SFU Burnaby", ART), ("Brentwood", "Metrotown", ART),
    ("SFU Burnaby", "Lougheed", ART), ("SFU Burnaby", "Hwy1 Brunette", ART), ("SFU Burnaby", "Port Moody", ART),
    ("Lougheed", "Hwy1 Brunette", ART), ("Lougheed", "New Westminster", ART),
    ("Hwy1 Brunette", "Hwy1 Port Mann", HWY), ("Hwy1 Port Mann", "Hwy1 Surrey", HWY),
    ("Hwy1 Surrey", "Hwy1 Langley", HWY), ("Hwy1 Langley", "Hwy1 Aldergrove", HWY),
    ("Hwy1 Aldergrove", "Hwy1 Abbotsford", HWY), ("Hwy1 Abbotsford", "Abbotsford", ART),
    ("Hwy1 Abbotsford", "Hwy1 Sumas", HWY), ("Hwy1 Sumas", "Hwy1 Chilliwack", HWY),
    ("Hwy1 Chilliwack", "Chilliwack", ART), ("Coquitlam Centre", "Port Moody", ART),
    ("Coquitlam Centre", "Hwy1 Port Mann", CONN), ("Coquitlam Centre", "Hwy1 Brunette", CONN),
    ("Coquitlam Centre", "SFU Burnaby", CONN), ("Coquitlam Centre", "Lougheed", CONN), ("Brentwood", "Lougheed", CONN),
    ("Coquitlam Centre", "Maple Ridge", HWY), ("Surrey Central", "Hwy1 Port Mann", ART),
    ("Surrey Central", "Hwy1 Surrey", ART), ("Surrey Central", "Guildford", ART),
    ("Guildford", "Hwy1 Surrey", ART), ("Surrey Central", "New Westminster", ART),
    ("Surrey Central", "White Rock", HWY), ("Surrey Central", "Langley", ART),
    ("Langley", "Hwy1 Langley", ART), ("Langley", "White Rock", ART), ("Maple Ridge", "Langley", ART),
    ("Maple Ridge", "Hwy1 Langley", ART),
]

ROAD_FACTOR = {HWY: 1.08, ART: 1.25, CONN: 1.15}
SPEED_KMH = {HWY: 90.0, ART: 45.0, CONN: 65.0}
LOCAL_ROAD_FACTOR = 1.30
LOCAL_SPEED_KMH = 40.0
