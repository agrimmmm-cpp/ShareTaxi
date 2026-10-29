"""Central configuration. Everything tunable lives here and can be overridden by environment variables.

Nested values use ``__`` as delimiter, e.g. ``MATCHING__WEIGHTS__ROUTE_OVERLAP=0.5``.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoreWeights(BaseModel):
    """Weights of the 0-100 compatibility score. They are normalised, so they need not sum to 1."""

    route_overlap: float = 0.40
    time: float = 0.20
    origin: float = 0.15
    destination: float = 0.15
    detour: float = 0.10


class DriverRankWeights(BaseModel):
    route_compatibility: float = 0.30
    profitability: float = 0.25
    passenger_savings: float = 0.20
    seat_utilization: float = 0.15
    completion_probability: float = 0.10


class MatchingConfig(BaseModel):
    weights: ScoreWeights = ScoreWeights()
    driver_rank_weights: DriverRankWeights = DriverRankWeights()
    score_threshold: float = 55.0  # minimum 0-100 compatibility to be considered
    max_passenger_detour_min: float = 25.0  # intercity trips tolerate more than urban ones
    max_driver_detour_min: float = 30.0
    max_departure_gap_min: float = 30.0
    max_driver_wait_min: float = 15.0  # driver may wait this long for an early pickup
    origin_radius_km: float = 15.0
    destination_radius_km: float = 20.0
    corridor_km: float = 5.0  # half-width of the "same route" corridor
    min_route_overlap: float = 0.45  # ratio (0-1) below which two trips are not "on the same route"
    min_group_size: int = 3  # passengers needed before we go looking for a driver
    max_group_size: int = 4  # seats in a typical car
    max_combo_candidates: int = 8  # candidates considered when enumerating driver combinations
    target_driver_hourly: float = 35.0  # net $/h that earns a 100 profitability score
    target_savings_ratio: float = 0.6  # savings ratio that earns a 100 savings score


class PricingConfig(BaseModel):
    base_fare: float = 5.00
    per_km: float = 0.75
    per_min: float = 0.20
    per_extra_pickup: float = 2.00
    per_detour_min: float = 0.60
    fuel_cost_per_km: float = 0.22  # driver operating cost (fuel + wear)
    platform_commission_rate: float = 0.13
    min_passenger_fare: float = 8.00
    demand_sensitivity: float = 0.10
    demand_multiplier_min: float = 0.90
    demand_multiplier_max: float = 1.25
    max_fraction_of_benchmark: float = 0.70  # shared fare must be <= 70% of the solo benchmark
    fare_range_pct: float = 0.08
    # fairness weights for splitting the fare
    share_weight_distance: float = 0.60
    share_weight_time: float = 0.25
    share_weight_detour: float = 0.15
    # configurable stand-in for a ride-hail price (replace with a licensed data source later)
    benchmark_base: float = 3.50
    benchmark_per_km: float = 1.60
    benchmark_per_min: float = 0.45
    benchmark_booking_fee: float = 3.00
    benchmark_minimum: float = 9.00
    benchmark_surge: float = 1.0


class CancellationConfig(BaseModel):
    free_hours_before: float = 24.0
    partial_hours_before: float = 2.0
    partial_fee_rate: float = 0.20
    late_fee_rate: float = 0.50


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")

    app_name: str = "ShareTaxi"
    environment: str = "development"
    database_url: str = "sqlite:///./sharetaxi.db"
    redis_url: str | None = None  # None -> in-memory fallback (dev/tests)

    jwt_secret: str = "dev-secret-change-me-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    google_client_id: str | None = None
    apple_client_id: str | None = None

    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 20

    routing_provider: str = "offline"  # offline | osrm
    osrm_url: str = "https://router.project-osrm.org"
    geocoder: str = "gazetteer"  # gazetteer | nominatim (gazetteer first, nominatim as fallback)

    payment_provider: str = "fake"  # fake | stripe
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    expo_push_url: str = "https://exp.host/--/api/v2/push/send"
    push_enabled: bool = False
    cors_origins: list[str] = ["*"]
    sentry_dsn: str | None = None

    matching: MatchingConfig = MatchingConfig()
    pricing: PricingConfig = PricingConfig()
    cancellation: CancellationConfig = CancellationConfig()


@lru_cache
def get_settings() -> Settings:
    return Settings()
