"""Shared-ride pricing. Pure functions + breakdown dataclasses; no I/O.

Money is computed in floats for readability but *allocated* in integer cents so shares always sum
exactly to the total. Payments use integer cents end-to-end.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from app.core.config import PricingConfig


def _r(x: float) -> float:
    return round(x + 1e-9, 2)


# --------------------------------------------------------------------------- breakdowns
@dataclass(frozen=True)
class TripCostInputs:
    distance_km: float
    duration_min: float
    pickups: int = 1  # number of passenger pickups on the route
    detour_min: float = 0.0
    demand_count: int = 0  # open passenger requests on this corridor
    supply_seats: int = 0  # open driver seats on this corridor
    min_driver_net: float = 0.0  # driver's minimum acceptable earnings (after fee and operating cost)


@dataclass(frozen=True)
class TripCost:
    base_fare: float
    distance_cost: float
    time_cost: float
    pickup_cost: float
    detour_cost: float
    demand_multiplier: float
    demand_adjustment: float
    min_earnings_top_up: float  # added when the formula would leave the driver below their minimum
    operating_cost: float
    total: float  # everything the passengers pay together (incl. platform fee)

    def lines(self) -> list[tuple[str, float]]:
        out = [
            ("Base fare", self.base_fare),
            ("Distance", self.distance_cost),
            ("Time", self.time_cost),
            ("Pickups", self.pickup_cost),
            ("Detour", self.detour_cost),
            ("Demand adjustment", self.demand_adjustment),
        ]
        if self.min_earnings_top_up:
            out.append(("Driver minimum top-up", self.min_earnings_top_up))
        return out


@dataclass(frozen=True)
class DriverPayout:
    gross: float
    platform_fee: float
    payout: float  # what the driver receives
    operating_cost: float
    net_earnings: float  # payout - operating cost


@dataclass(frozen=True)
class Savings:
    solo_cost: float
    shared_cost: float
    saved: float
    percent: float


@dataclass(frozen=True)
class PassengerShareInput:
    request_id: int
    distance_km: float
    time_min: float
    detour_contribution_min: float = 0.0
    party_size: int = 1


@dataclass(frozen=True)
class PassengerFare:
    request_id: int
    fare: float
    platform_fee: float
    distance_part: float
    time_part: float
    detour_part: float
    share_fraction: float


# --------------------------------------------------------------------------- functions
def estimate_market_benchmark(
    distance_km: float, duration_min: float, cfg: PricingConfig, surge: float | None = None
) -> float:
    """Configurable stand-in for a solo ride-hail price (NOT a claim about any real company's pricing).

    Swap in a licensed price source by implementing ``BenchmarkProvider`` and passing it to callers.
    """
    raw = cfg.benchmark_base + cfg.benchmark_per_km * distance_km + cfg.benchmark_per_min * duration_min
    raw = (raw + cfg.benchmark_booking_fee) * (cfg.benchmark_surge if surge is None else surge)
    return _r(max(cfg.benchmark_minimum, raw))


class BenchmarkProvider(Protocol):
    def solo_price(self, distance_km: float, duration_min: float) -> float: ...


def calculate_platform_fee(total: float, commission_rate: float) -> float:
    return _r(total * commission_rate)


def demand_multiplier(demand_count: int, supply_seats: int, cfg: PricingConfig) -> float:
    if demand_count <= 0 and supply_seats <= 0:
        return 1.0
    ratio = demand_count / max(1, supply_seats)
    raw = 1.0 + cfg.demand_sensitivity * (ratio - 1.0)
    return max(cfg.demand_multiplier_min, min(cfg.demand_multiplier_max, raw))


def estimate_trip_cost(inp: TripCostInputs, cfg: PricingConfig) -> TripCost:
    """Total Trip Cost = Base + Distance + Time + Pickup/Detour costs, scaled by demand, floored so the
    driver always clears their minimum earnings."""
    base = cfg.base_fare
    dist = cfg.per_km * inp.distance_km
    time = cfg.per_min * inp.duration_min
    pickups = cfg.per_extra_pickup * max(0, inp.pickups - 1)
    detour = cfg.per_detour_min * max(0.0, inp.detour_min)
    subtotal = base + dist + time + pickups + detour
    mult = demand_multiplier(inp.demand_count, inp.supply_seats, cfg)
    adjusted = subtotal * mult
    operating = cfg.fuel_cost_per_km * inp.distance_km
    required = (inp.min_driver_net + operating) / (1 - cfg.platform_commission_rate) if inp.min_driver_net else 0.0
    top_up = max(0.0, required - adjusted)
    return TripCost(
        base_fare=_r(base), distance_cost=_r(dist), time_cost=_r(time), pickup_cost=_r(pickups),
        detour_cost=_r(detour), demand_multiplier=round(mult, 3), demand_adjustment=_r(adjusted - subtotal),
        min_earnings_top_up=_r(top_up), operating_cost=_r(operating), total=_r(adjusted + top_up),
    )


def calculate_driver_payout(total: float, operating_cost: float, cfg: PricingConfig) -> DriverPayout:
    fee = calculate_platform_fee(total, cfg.platform_commission_rate)
    payout = _r(total - fee)
    return DriverPayout(_r(total), fee, payout, _r(operating_cost), _r(payout - operating_cost))


def calculate_savings(shared: float, solo: float) -> Savings:
    saved = _r(solo - shared)
    return Savings(_r(solo), _r(shared), saved, round(100.0 * saved / solo, 1) if solo > 0 else 0.0)


def calculate_passenger_share(
    total: float, passengers: Sequence[PassengerShareInput], cfg: PricingConfig
) -> list[PassengerFare]:
    """Split ``total`` proportionally to distance travelled, time in vehicle and detour caused.

    The detour weight falls back onto distance when nobody caused a detour. A minimum fare per
    passenger is enforced and the remainder re-split among the others.
    """
    if not passengers:
        return []
    wd, wt, wx = cfg.share_weight_distance, cfg.share_weight_time, cfg.share_weight_detour

    def parts(group: Sequence[PassengerShareInput]):
        s_d = sum(p.distance_km * p.party_size for p in group) or 1.0
        s_t = sum(p.time_min * p.party_size for p in group) or 1.0
        s_x = sum(p.detour_contribution_min * p.party_size for p in group)
        w_x = wx if s_x > 0 else 0.0
        norm = (wd + (wx - w_x)) + wt + w_x  # fold unused detour weight into distance
        rows = []
        for p in group:
            d = (wd + (wx - w_x)) / norm * p.distance_km * p.party_size / s_d
            t = wt / norm * p.time_min * p.party_size / s_t
            x = (w_x / norm * p.detour_contribution_min * p.party_size / s_x) if s_x > 0 else 0.0
            rows.append((p, d, t, x))
        return rows

    total_cents = round(total * 100)
    fixed: dict[int, int] = {}
    floor_cents = round(cfg.min_passenger_fare * 100)
    free = list(passengers)
    budget = total_cents
    for _ in range(len(passengers)):  # iterate: pin anyone under the floor, re-split the rest
        rows = parts(free)
        shares = {p.request_id: (d + t + x) for p, d, t, x in rows}
        under = [p for p in free if budget * shares[p.request_id] < floor_cents * p.party_size]
        if not under or len(under) == len(free):
            break
        for p in under:
            fixed[p.request_id] = floor_cents * p.party_size
            budget -= fixed[p.request_id]
            free.remove(p)
    rows = parts(free) if free else []
    cents: dict[int, int] = dict(fixed)
    frac: dict[int, tuple[float, float, float, float]] = {}
    for p, d, t, x in rows:
        cents[p.request_id] = int(budget * (d + t + x))
        frac[p.request_id] = (d, t, x, d + t + x)
    leftover = total_cents - sum(cents.values())  # hand the rounding remainder out, largest first
    order = sorted(cents, key=lambda k: -cents[k])
    for i in range(abs(leftover)):
        cents[order[i % len(order)]] += 1 if leftover > 0 else -1

    out: list[PassengerFare] = []
    for p in passengers:
        c = cents[p.request_id]
        d, t, x, f = frac.get(p.request_id, (1.0, 0.0, 0.0, 1.0))
        denom = (d + t + x) or 1.0
        fare = c / 100
        out.append(
            PassengerFare(
                p.request_id, _r(fare), calculate_platform_fee(fare, cfg.platform_commission_rate),
                _r(fare * d / denom), _r(fare * t / denom), _r(fare * x / denom),
                round(c / total_cents, 4) if total_cents else 0.0,
            )
        )
    return out


def fare_range(fare: float, cfg: PricingConfig) -> tuple[float, float]:
    return _r(fare * (1 - cfg.fare_range_pct)), _r(fare * (1 + cfg.fare_range_pct))


def cancellation_fee(fare: float, hours_to_departure: float, cfg) -> float:
    """Fee a passenger owes for cancelling after confirmation. ``cfg`` is a CancellationConfig."""
    if hours_to_departure >= cfg.free_hours_before:
        return 0.0
    if hours_to_departure >= cfg.partial_hours_before:
        return _r(fare * cfg.partial_fee_rate)
    return _r(fare * cfg.late_fee_rate)
