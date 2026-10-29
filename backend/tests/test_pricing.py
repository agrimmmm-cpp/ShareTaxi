import pytest

from app.core.config import CancellationConfig, PricingConfig
from app.services import pricing_service as p

CFG = PricingConfig()


def test_trip_cost_is_sum_of_parts_times_demand():
    c = p.estimate_trip_cost(p.TripCostInputs(70, 60, pickups=3, detour_min=10), CFG)
    expected = CFG.base_fare + 70 * CFG.per_km + 60 * CFG.per_min + 2 * CFG.per_extra_pickup + 10 * CFG.per_detour_min
    assert c.total == pytest.approx(expected, abs=0.02)
    assert c.demand_multiplier == 1.0 and c.demand_adjustment == 0


def test_demand_multiplier_bounded():
    hi = p.estimate_trip_cost(p.TripCostInputs(50, 40, demand_count=100, supply_seats=1), CFG)
    lo = p.estimate_trip_cost(p.TripCostInputs(50, 40, demand_count=0, supply_seats=100), CFG)
    assert hi.demand_multiplier == CFG.demand_multiplier_max
    assert lo.demand_multiplier == CFG.demand_multiplier_min
    assert hi.total > lo.total


def test_min_driver_earnings_top_up_guarantees_net():
    c = p.estimate_trip_cost(p.TripCostInputs(40, 35, pickups=2, min_driver_net=80), CFG)
    payout = p.calculate_driver_payout(c.total, c.operating_cost, CFG)
    assert c.min_earnings_top_up > 0
    assert payout.net_earnings >= 80 - 0.05


def test_no_top_up_when_formula_already_pays_enough():
    c = p.estimate_trip_cost(p.TripCostInputs(70, 60, pickups=3, min_driver_net=10), CFG)
    assert c.min_earnings_top_up == 0


def test_platform_fee_and_payout_add_up():
    pay = p.calculate_driver_payout(90.0, 15.0, PricingConfig(platform_commission_rate=0.1333))
    assert pay.platform_fee + pay.payout == pytest.approx(90.0, abs=0.01)
    assert pay.net_earnings == pytest.approx(pay.payout - 15.0, abs=0.01)


def test_platform_fee_configurable():
    assert p.calculate_platform_fee(100, 0.2) == 20.0
    assert p.calculate_platform_fee(100, 0.0) == 0.0


def test_benchmark_is_configurable_and_monotonic():
    short = p.estimate_market_benchmark(10, 15, CFG)
    long = p.estimate_market_benchmark(70, 60, CFG)
    assert long > short >= CFG.benchmark_minimum
    assert p.estimate_market_benchmark(70, 60, CFG, surge=2.0) > long


def test_savings():
    s = p.calculate_savings(31, 90)
    assert (s.saved, s.percent) == (59.0, 65.6)
    assert p.calculate_savings(10, 0).percent == 0.0


def test_shares_sum_exactly_to_total():
    shares = p.calculate_passenger_share(
        97.41, [p.PassengerShareInput(1, 70, 60), p.PassengerShareInput(2, 50, 45), p.PassengerShareInput(3, 30, 28)], CFG)
    assert round(sum(s.fare for s in shares), 2) == 97.41


def test_longer_trips_pay_more():
    a, b, c = p.calculate_passenger_share(
        100, [p.PassengerShareInput(1, 70, 60), p.PassengerShareInput(2, 50, 45), p.PassengerShareInput(3, 30, 28)], CFG)
    assert a.fare > b.fare > c.fare
    assert a.distance_part + a.time_part + a.detour_part == pytest.approx(a.fare, abs=0.02)


def test_detour_causers_pay_more():
    base = p.calculate_passenger_share(90, [p.PassengerShareInput(1, 50, 45), p.PassengerShareInput(2, 50, 45)], CFG)
    assert base[0].fare == base[1].fare
    skew = p.calculate_passenger_share(90, [p.PassengerShareInput(1, 50, 45, 0), p.PassengerShareInput(2, 50, 45, 12)], CFG)
    assert skew[1].fare > skew[0].fare
    assert skew[1].detour_part > 0 == skew[0].detour_part


def test_minimum_fare_floor_respected_and_total_preserved():
    shares = p.calculate_passenger_share(30, [p.PassengerShareInput(1, 100, 80), p.PassengerShareInput(2, 1, 2)], CFG)
    assert shares[1].fare >= CFG.min_passenger_fare
    assert round(sum(s.fare for s in shares), 2) == 30.0


def test_party_size_scales_share():
    solo, pair = p.calculate_passenger_share(90, [p.PassengerShareInput(1, 50, 45, party_size=1), p.PassengerShareInput(2, 50, 45, party_size=2)], CFG)
    assert pair.fare == pytest.approx(2 * solo.fare, abs=0.03)


def test_empty_passengers():
    assert p.calculate_passenger_share(50, [], CFG) == []


def test_cancellation_fee_tiers():
    c = CancellationConfig()
    assert p.cancellation_fee(30, 48, c) == 0
    assert p.cancellation_fee(30, 10, c) == pytest.approx(6.0)
    assert p.cancellation_fee(30, 1, c) == pytest.approx(15.0)


def test_fare_range_brackets_estimate():
    lo, hi = p.fare_range(30, CFG)
    assert lo < 30 < hi
