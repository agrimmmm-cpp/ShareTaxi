import pytest

from app.services import route_service as rs
from app.utils import polyline
from app.utils.geo import Point, haversine_km, nearest_on_polyline, resample

VAN, BBY, ABB, LNG, COQ = (rs.geocode_address(n).point for n in ("Vancouver", "Burnaby", "Abbotsford", "Langley", "Coquitlam"))


def test_geocode_gazetteer_and_aliases():
    assert rs.geocode_address("SFU Burnaby, BC").name == "SFU Burnaby"
    assert rs.geocode_address("downtown").name == "Downtown Vancouver"
    assert rs.geocode_address("Abbotsford, BC").point == rs.geocode_address("abbotsford").point


def test_geocode_unknown_raises():
    with pytest.raises(rs.GeocodeError):
        rs.geocode_address("zzzz nowhere")


def test_route_is_realistic_and_cached():
    r = rs.calculate_route(VAN, ABB)
    assert 60 < r.distance_km < 90 and 45 < r.duration_min < 75
    assert rs.calculate_route(VAN, ABB) is rs.calculate_route(VAN, ABB)
    assert rs.calculate_route_distance(VAN, ABB) == r.distance_km
    assert rs.calculate_route_duration(VAN, ABB) == r.duration_min


def test_route_through_waypoint_is_longer():
    direct = rs.calculate_route(BBY, ABB)
    via = rs.calculate_route(BBY, ABB, via=[COQ])
    assert via.distance_km >= direct.distance_km


def test_polyline_roundtrip():
    pts = [Point(49.2827, -123.1207), Point(49.05, -122.30), Point(49.1, -122.5)]
    out = polyline.decode(polyline.encode(pts))
    assert all(haversine_km(a, b) < 0.002 for a, b in zip(pts, out))


def test_overlap_same_direction_high():
    a, b = rs.calculate_route(BBY, ABB), rs.calculate_route(COQ, ABB)
    assert rs.calculate_route_overlap(a.points, b.points).ratio > 0.8


def test_overlap_subroute_counts():
    long_, short = rs.calculate_route(BBY, ABB), rs.calculate_route(BBY, LNG)
    assert rs.calculate_route_overlap(long_.points, short.points).ratio > 0.7


def test_overlap_opposite_direction_is_zero():
    fwd, back = rs.calculate_route(BBY, ABB), rs.calculate_route(ABB, BBY)
    assert rs.calculate_route_overlap(fwd.points, back.points).ratio == 0


def test_overlap_unrelated_routes_low():
    east = rs.calculate_route(BBY, ABB)
    west = rs.calculate_route(rs.geocode_address("UBC").point, rs.geocode_address("YVR").point)
    assert rs.calculate_route_overlap(east.points, west.points).ratio < 0.2


def test_nearest_on_polyline_and_resample():
    line = [Point(49.0, -123.0), Point(49.0, -122.0)]
    d, along = nearest_on_polyline(Point(49.05, -122.5), line)
    assert 5 < d < 6 and 35 < along < 40
    pts = resample(line, 10)
    assert len(pts) > 5 and pts[0] == line[0] and pts[-1] == line[-1]


def stops(*spec):
    return [rs.Stop(f"{k}{i}", i, kind, p) for k, kind, i, p in spec]


def test_optimize_respects_pickup_before_dropoff():
    ss = stops(("p", "pickup", 1, BBY), ("d", "dropoff", 1, ABB), ("p", "pickup", 2, COQ), ("d", "dropoff", 2, LNG))
    plan = rs.optimize_stops(VAN, ss, None)
    seen = set()
    for rid, kind in plan.sequence():
        if kind == "pickup":
            seen.add(rid)
        else:
            assert rid in seen


def test_optimize_never_exceeds_capacity():
    ss = [rs.Stop(f"p{i}", i, "pickup", BBY, 2) for i in (1, 2)] + [rs.Stop(f"d{i}", i, "dropoff", ABB, 2) for i in (1, 2)]
    plan = rs.optimize_stops(VAN, ss, None, capacity=2)
    onboard = 0
    for s in plan.stops:
        onboard += s.party_size if s.kind == "pickup" else -s.party_size
        assert onboard <= 2


def test_optimize_is_at_least_as_good_as_reverse_order():
    ss = stops(("p", "pickup", 1, COQ), ("p", "pickup", 2, BBY), ("d", "dropoff", 1, ABB), ("d", "dropoff", 2, LNG))
    plan = rs.optimize_stops(VAN, ss, ABB)
    naive = rs.evaluate_sequence(VAN, [ss[0], ss[1], ss[2], ss[3]], ABB)
    assert plan.total_min <= naive[1] + 1e-6


def test_estimate_detour_nonnegative_and_pickup_on_route_is_small():
    on_route = rs.estimate_detour(VAN, ABB, stops(("p", "pickup", 1, BBY), ("d", "dropoff", 1, ABB)))
    off_route = rs.estimate_detour(VAN, ABB, stops(("p", "pickup", 1, rs.geocode_address("Maple Ridge").point), ("d", "dropoff", 1, ABB)))
    assert 0 <= on_route.added_min < off_route.added_min


def test_route_efficiency_score_bounds():
    plan = rs.optimize_stops(VAN, stops(("p", "pickup", 1, BBY), ("d", "dropoff", 1, ABB)), ABB)
    direct = rs.calculate_route_duration(VAN, ABB)
    assert 0 < rs.route_efficiency(plan, direct) <= 100


def test_approximate_area_is_neighbourhood_label():
    assert rs.approximate_area(Point(49.2790, -122.9250)) == "SFU Burnaby"
