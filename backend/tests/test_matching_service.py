from datetime import datetime, timedelta

import pytest

from app.core.config import MatchingConfig, PricingConfig, ScoreWeights
from app.services import matching_service as ms
from app.services.route_service import geocode_address as g

CFG, PCFG = MatchingConfig(), PricingConfig()
T0 = datetime(2026, 10, 8, 10, 0)


def req(i, o, d, offset_min=0, **kw):
    return ms.build_request(i, i, g(o).point, g(d).point, T0 + timedelta(minutes=offset_min), max_detour_min=25, **kw)


@pytest.fixture(scope="module")
def trio():
    return req(1, "Burnaby", "Abbotsford", 0), req(2, "Coquitlam", "Abbotsford", -10), req(3, "Burnaby", "Langley", 10)


def test_time_compatibility_curve():
    t = lambda m: T0 + timedelta(minutes=m)
    f = lambda a, b, w=30: ms.calculate_time_compatibility(t(a), t(a - w), t(a + w), t(b), t(b - w), t(b + w), 30)
    assert f(0, 0) == 1.0
    assert f(0, 15) == pytest.approx(0.5)
    assert f(0, 30) == 0.0
    assert f(0, 90) == 0.0  # disjoint windows


def test_time_compat_zero_when_windows_disjoint_even_if_prefs_close():
    t = lambda m: T0 + timedelta(minutes=m)
    assert ms.calculate_time_compatibility(t(0), t(0), t(5), t(10), t(8), t(15), 30) == 0.0


def test_origin_and_destination_similarity(trio):
    a, b, c = trio
    assert ms.calculate_origin_similarity(a, c, CFG) == pytest.approx(1.0)
    assert ms.calculate_destination_similarity(a, b, CFG) == pytest.approx(1.0)
    assert 0 < ms.calculate_origin_similarity(a, b, CFG) < 1


def test_brief_example_pairs_are_all_compatible(trio):
    a, b, c = trio
    for x, y in ((a, b), (a, c), (b, c)):
        s = ms.calculate_match_score(x, y, CFG)
        assert s.feasible, (x.id, y.id, s)
        assert 55 <= s.total <= 100
        assert set(s.components) == {"route_overlap", "time", "origin", "destination", "detour"}


def test_score_symmetry(trio):
    a, b, _ = trio
    assert ms.calculate_match_score(a, b, CFG).total == pytest.approx(ms.calculate_match_score(b, a, CFG).total, abs=0.5)


def test_opposite_direction_rejected():
    s = ms.calculate_match_score(req(1, "Burnaby", "Abbotsford"), req(2, "Abbotsford", "Burnaby"), CFG)
    assert not s.feasible and "route_overlap" in s.reasons


def test_departure_gap_rejected():
    s = ms.calculate_match_score(req(1, "Burnaby", "Abbotsford"), req(2, "Burnaby", "Abbotsford", 45), CFG)
    assert not s.feasible and "departure_gap" in s.reasons


def test_capacity_rejected():
    s = ms.calculate_match_score(req(1, "Burnaby", "Abbotsford", passenger_count=3), req(2, "Burnaby", "Abbotsford", passenger_count=2), CFG)
    assert not s.feasible and "capacity" in s.reasons


def test_weights_are_configurable(trio):
    a, b, _ = trio
    base = ms.calculate_match_score(a, b, CFG).total
    time_only = MatchingConfig(weights=ScoreWeights(route_overlap=0, time=1, origin=0, destination=0, detour=0))
    s = ms.calculate_match_score(a, b, time_only)
    assert s.total == pytest.approx(s.components["time"], abs=0.01) and s.total != base


def test_threshold_is_configurable(trio):
    a, b, _ = trio
    strict = MatchingConfig(score_threshold=99)
    assert not ms.calculate_match_score(a, b, strict).feasible


def test_find_passenger_matches_sorted_and_excludes_self(trio):
    a, b, c = trio
    far = req(9, "UBC", "YVR Airport", 0)
    res = ms.find_passenger_matches(a, [a, b, c, far], CFG)
    assert [r.id for r, _ in res] and a.id not in [r.id for r, _ in res] and far.id not in [r.id for r, _ in res]
    assert [s.total for _, s in res] == sorted((s.total for _, s in res), reverse=True)


def test_same_user_not_matched_with_self():
    a = req(1, "Burnaby", "Abbotsford")
    twin = ms.RideRequestData(**{**a.__dict__, "id": 2})
    assert ms.find_passenger_matches(a, [twin], CFG) == []


def test_creates_one_group_of_three_from_brief(trio):
    groups = ms.create_passenger_groups(list(trio), CFG)
    assert len(groups) == 1 and groups[0].seats == 3 and groups[0].meets_minimum(CFG)
    g_ = groups[0]
    assert g_.window_start <= g_.suggested_departure <= g_.window_end
    for m in g_.members:
        assert g_.plan.metrics[m.id].detour_min <= CFG.max_passenger_detour_min


def test_unrelated_requests_stay_alone(trio):
    outlier = req(9, "UBC", "YVR Airport", 0)
    groups = ms.create_passenger_groups(list(trio) + [outlier], CFG)
    assert sorted(g_.seats for g_ in groups) == [1, 3]
    assert all(9 not in gr.request_ids for gr in groups if gr.seats == 3)


def test_every_request_in_exactly_one_group(trio):
    pool = list(trio) + [req(4, "Burnaby", "Abbotsford", 5), req(5, "UBC", "YVR Airport")]
    ids = [i for gr in ms.create_passenger_groups(pool, CFG) for i in gr.request_ids]
    assert sorted(ids) == sorted(r.id for r in pool)


def test_group_never_exceeds_seats():
    pool = [req(i, "Burnaby", "Abbotsford", i) for i in range(1, 8)]
    assert all(gr.seats <= CFG.max_group_size for gr in ms.create_passenger_groups(pool, CFG))


def test_tight_detour_limit_prevents_unreasonable_groups(trio):
    strict = MatchingConfig(max_passenger_detour_min=3)
    groups = ms.create_passenger_groups(list(trio), strict)
    assert max(gr.seats for gr in groups) < 3


def test_driver_match_for_brief_group_is_profitable_and_cheaper(trio):
    group = ms.create_passenger_groups(list(trio), CFG)[0]
    trip = ms.build_trip(1, 99, g("Vancouver").point, g("Abbotsford").point, T0 - timedelta(minutes=30), 4, 30, 55)
    [m] = ms.find_driver_for_group(group, [trip], CFG, PCFG)
    assert m.payout.net_earnings >= 55
    assert m.seats_used == 3 and m.scores["seat_utilization"] == 75.0
    assert m.driver_detour_min <= 30
    for rid in m.request_ids:
        assert m.savings[rid].percent >= 30  # materially cheaper than the solo benchmark
    assert sum(f.fare for f in m.fares) == pytest.approx(m.cost.total, abs=0.02)
    assert 0 <= m.overall <= 100


def test_driver_minimum_earnings_blocks_unviable_match(trio):
    group = ms.create_passenger_groups(list(trio), CFG)[0]
    greedy = ms.build_trip(1, 99, g("Vancouver").point, g("Abbotsford").point, T0 - timedelta(minutes=30), 4, 30, 5000)
    assert ms.find_driver_for_group(group, [greedy], CFG, PCFG) == []


def test_driver_too_few_seats_rejected(trio):
    group = ms.create_passenger_groups(list(trio), CFG)[0]
    small = ms.build_trip(1, 99, g("Vancouver").point, g("Abbotsford").point, T0 - timedelta(minutes=30), 2, 30, 0)
    assert ms.find_driver_for_group(group, [small], CFG, PCFG) == []


def test_driver_detour_limit_enforced(trio):
    group = ms.create_passenger_groups(list(trio), CFG)[0]
    rigid = ms.build_trip(1, 99, g("Vancouver").point, g("Abbotsford").point, T0 - timedelta(minutes=30), 4, 2, 0)
    assert ms.find_driver_for_group(group, [rigid], CFG, PCFG) == []


def test_driver_leaving_too_late_misses_pickup_window(trio):
    group = ms.create_passenger_groups(list(trio), CFG)[0]
    late = ms.build_trip(1, 99, g("Vancouver").point, g("Abbotsford").point, T0 + timedelta(hours=2), 4, 30, 0)
    assert ms.find_driver_for_group(group, [late], CFG, PCFG) == []


def test_driver_wrong_direction_rejected(trio):
    group = ms.create_passenger_groups(list(trio), CFG)[0]
    wrong = ms.build_trip(1, 99, g("Abbotsford").point, g("Vancouver").point, T0 - timedelta(minutes=30), 4, 30, 0)
    assert ms.find_driver_for_group(group, [wrong], CFG, PCFG) == []


def test_rank_driver_matches_orders_by_overall(trio):
    group = ms.create_passenger_groups(list(trio), CFG)[0]
    t1 = ms.build_trip(1, 90, g("Vancouver").point, g("Abbotsford").point, T0 - timedelta(minutes=30), 4, 30, 0)
    t2 = ms.build_trip(2, 91, g("Vancouver").point, g("Abbotsford").point, T0 - timedelta(minutes=30), 7, 30, 0)
    ranked = ms.find_driver_for_group(group, [t1, t2], CFG, PCFG)
    assert [m.overall for m in ranked] == sorted((m.overall for m in ranked), reverse=True)
    assert ranked[0].trip_id == 1  # better seat utilisation (3/4 vs 3/7)


def test_recommend_groups_for_driver_prefers_fuller_cars(trio):
    trip = ms.build_trip(1, 99, g("Vancouver").point, g("Abbotsford").point, T0 - timedelta(minutes=30), 4, 30, 55)
    recs = ms.recommend_groups_for_driver(trip, list(trio), CFG, PCFG)
    assert recs and set(recs[0].request_ids) == {1, 2, 3}
    assert all(r.payout.net_earnings >= 55 for r in recs)
    assert [r.overall for r in recs] == sorted((r.overall for r in recs), reverse=True)


def test_recommend_skips_requests_going_elsewhere(trio):
    trip = ms.build_trip(1, 99, g("Vancouver").point, g("Abbotsford").point, T0 - timedelta(minutes=30), 4, 30, 0)
    recs = ms.recommend_groups_for_driver(trip, list(trio) + [req(9, "UBC", "YVR Airport")], CFG, PCFG)
    assert all(9 not in r.request_ids for r in recs)


def test_price_group_without_driver(trio):
    group = ms.create_passenger_groups(list(trio), CFG)[0]
    cost, fares, bench, savings = ms.price_group_without_driver(group, PCFG)
    assert round(sum(f.fare for f in fares), 2) == cost.total
    assert all(s.saved > 0 for s in savings.values())
