# Architecture

```
┌────────────────────┐   REST + WebSocket   ┌──────────────────────────────────────────────┐
│ Expo / React Native│◀────────────────────▶│ FastAPI                                      │
│  TanStack Query    │                      │  routers  → thin HTTP + auth + validation    │
│  Zustand           │                      │  schemas  → Pydantic in/out                  │
└────────────────────┘                      │  services → business logic (below)           │
┌────────────────────┐                      │  repositories → queries                      │
│ Admin web (static) │─────REST────────────▶│  models   → SQLAlchemy 2                     │
└────────────────────┘                      └──────┬───────────────┬──────────────┬────────┘
                                                   │               │              │
                                         PostgreSQL/PostGIS      Redis        Stripe / Expo push / OSRM
                                         (system of record)  (cache, queues,   (behind interfaces)
                                                              rate limits, GEO)
```

## Layering (clean architecture)

| Layer | Path | Rule |
|---|---|---|
| Routers | `app/routers` | HTTP only: parse, authorise, call a service, serialise. No business rules. |
| Services | `app/services` | All business logic. **Pure engines** (`matching_service`, `pricing_service`, most of `route_service`) take plain dataclasses and have no I/O. **Orchestrators** (`matching_orchestrator`, `ride_service`, `payment_service`) glue engines to the DB. |
| Repositories | `app/repositories` | Query objects; services never write ad-hoc SQL. |
| Models / Schemas | `app/models`, `app/schemas` | SQLAlchemy tables / Pydantic contracts. API never returns ORM objects directly. |
| Core | `app/core` | config, security, cache (Redis + in-memory), logging, rate limit, deps, WebSocket manager. |

## Real-time matching flow

`POST /ride-requests` → save → `matching_orchestrator.rematch()`:

1. expire stale requests; load the active pool (`searching…driver_found`)
2. `create_passenger_groups` (scores every feasible pair, clusters)
3. reuse existing `RideGroup` rows by **maximum member overlap** so ids stay stable as groups grow
4. for groups with ≥ `min_group_size` seats: `find_driver_for_group` over open driver trips →
   persist the top 3 as `Match(status=proposed)` with full plan JSON (stops, ETAs, per-rider fares, cost lines)
5. transition request states through `state_machine.transition` (illegal jumps raise)
6. notify exactly the people whose situation changed

`POST /driver/trips` runs `rematch()` and `recommend_for_trip()` (enumerate/rank rider combinations for that
driver, persisted as `source="driver_combo"` matches). Accepting a match (`ride_service.confirm_match`) re-validates
everything (pool status, seats, trip open) inside one transaction, creates the `Ride`, `RidePassenger`s,
`RideStop`s and `Payment` rows, voids competing proposals, notifies, then re-runs `rematch()` for the remaining pool.
Driver cancellation puts riders back to `searching` and the same `rematch()` finds them a new driver.

## Data model

`users · profiles · drivers · vehicles · driver_documents · passenger_requests · driver_trip_posts · ride_groups ·
ride_group_members · matches · rides · ride_passengers · ride_stops · payments · driver_payouts · ratings · messages ·
notifications · reports · emergency_contacts · saved_locations · recurring_requests · user_blocks · refresh_tokens ·
platform_settings` (25 tables, Alembic migration `0001`). Money lives in `Float` on planning rows
(`matches`, `rides`) and in **integer cents** on `payments`/`driver_payouts`.

## State machines (`services/state_machine.py`)

* Ride: `confirmed → driver_arriving → active → completed`, `cancelled` from the first two.
* Request: `searching → group_found → driver_search → driver_found → confirmed → driver_arriving → active → completed`
  (+ `cancelled`/`expired`; `confirmed → searching` when a driver cancels).
* Trip: `open → confirmed → active → completed` (+ `cancelled`).

## Redis (never the system of record)

route cache (24 h) · GEO index of request origins · rate-limit windows · push-notification queue · (hooks for ride
state and WebSocket fan-out). Absent `REDIS_URL`, an in-memory implementation of the same interface is used.

## Security

bcrypt hashes · 15-min JWTs · rotating refresh tokens (hashed at rest, reuse ⇒ family revoked) · per-IP rate limits
(stricter on auth) · role dependencies (`require_driver`, `require_admin`) · ownership checks return 404 (no
existence leaks) · SQLAlchemy parameterised queries · Pydantic validation everywhere · other riders' exact locations
never serialised · chat masks phone numbers · no card data stored · JSON structured logs with event names.

## Extending

| Want | Do |
|---|---|
| Real roads / ETAs | `ROUTING_PROVIDER=osrm` or implement `RoutingProvider` |
| Better sequencing | replace `route_service.optimize_stops` with an OR-Tools VRP (same `StopPlan` output) |
| ML / demand forecasting | add a scorer next to `calculate_match_score`; weights already live in config |
| Dynamic pricing | feed forecasts into `TripCostInputs.demand_count/supply_seats` |
| Competitor benchmarks | implement `pricing_service.BenchmarkProvider` (licensed data only) |
| ID / licence checks | implement `verification_service.VerificationProvider` |
| Celery / RQ | call `rematch`, `drain_push_queue` from tasks; they are already isolated |
| Scale-out | shard `rematch` by geohash + time bucket; Redis pub/sub for WebSockets; PostGIS for candidate queries |
| Observability | Sentry via `SENTRY_DSN`; all events go through `log_event` (hook OpenTelemetry/Prometheus there) |
