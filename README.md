# ShareTaxi

> **Post where you're going. We find people going your way, match everyone with a driver, and split the ride so everyone pays less.**

ShareTaxi is a collaborative ride-matching platform (think BlaBlaCar's shared travel + a ride-hailing booking
experience + algorithmic passenger grouping + a reverse marketplace where passenger demand attracts drivers).
It is **not** "passenger requests → nearest driver accepts". Passengers are first **grouped by route**, the
pickup/drop-off sequence is optimised, the fare is priced and split fairly, and only then is a driver matched
— subject to the driver actually earning enough.

```
Passenger posts trip ─▶ find compatible riders (route overlap, time, detour) ─▶ build groups of ≥3
   ─▶ optimise stop order ─▶ price + fair split ─▶ find/rank drivers (seats, detour, earnings)
   ─▶ driver accepts ─▶ ride confirmed ─▶ pay (hold) ─▶ ride ─▶ capture ─▶ payout
```

| | |
|---|---|
| `backend/` | FastAPI · SQLAlchemy 2 · Alembic · Pydantic · Redis · JWT · WebSockets · Stripe (pluggable) |
| `mobile/`  | Expo SDK 58 · React Native · TypeScript · Expo Router · TanStack Query · Zustand |
| `docs/`    | [Architecture](docs/ARCHITECTURE.md), [matching algorithm](docs/MATCHING.md) |

## Quick start

### Option A — everything in Docker (Postgres + PostGIS, Redis, API, seed data)

```bash
cp .env.example .env
docker compose up --build
# API docs   http://localhost:8000/docs
# Admin UI   http://localhost:8000/admin-ui     (admin@sharetaxi.dev / password123)
```

### Option B — local, zero infrastructure (SQLite + in-memory cache)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed                      # demo data + prints how the engine grouped everyone
uvicorn app.main:app --reload           # http://localhost:8000/docs
pytest                                  # 100+ tests
```

### Mobile app

```bash
cd mobile
cp .env.example .env                    # EXPO_PUBLIC_API_URL (use your LAN IP on a physical device)
npm install
npx expo start                          # press i (iOS simulator) / a (Android) / scan the QR with a dev build
npm run typecheck
```

`react-native-maps` ships in Expo Go on iOS/Android. Maps show a placeholder on web.

### Demo accounts (all `password123`)

| Account | Role | Scenario (from the product brief, "tomorrow") |
|---|---|---|
| `alice@sharetaxi.dev` | passenger | Burnaby → Abbotsford, 10:00 |
| `bob@sharetaxi.dev`   | passenger | Coquitlam → Abbotsford, 9:50 |
| `carol@sharetaxi.dev` | passenger | Burnaby → Langley, 10:10 |
| `dave@sharetaxi.dev`  | driver    | Vancouver → Abbotsford, 9:30, 4 seats, min earnings $55 |
| `erin@sharetaxi.dev`  | driver    | verified, no trip posted yet |
| `admin@sharetaxi.dev` | admin     | web dashboard |

Sign in as **dave** → *My Trips* → the trip shows a recommended 3-passenger group (route map, added minutes,
earnings after fees and fuel) → *Accept group*. Then sign in as **alice** to see the confirmed ride, pay, chat,
and (as dave) start/complete it to watch capture → payout → ratings.

## What's implemented

Everything in the brief's Phase 1 and most of Phase 2/3, working end-to-end and covered by tests:

* **Auth** — email/password (bcrypt), 15-min JWT access tokens, **rotating refresh tokens with reuse detection**
  (replaying an old token revokes the whole family), Google sign-in endpoint, rate limiting.
* **Passenger** — post requests (flexible time, party size, luggage, accessibility, pickup/detour limits, ride
  type), instant search summary (potential matches, fare range, savings, departure window), group-forming view,
  discovery ("Explore": rides already forming, priced for *you*), join/leave, recurring commutes, cancellations with
  tiered fees.
* **Driver** — verification workflow (4 documents, admin review), vehicles, post trips (seats, detour, minimum
  earnings, auto-match), ranked passenger-group recommendations with route map and earnings breakdown,
  accept/reject, edit flexibility, dashboard, earnings/payouts, **demand marketplace** (clusters of waiting riders).
* **Matching engine** — see below and [docs/MATCHING.md](docs/MATCHING.md).
* **Pricing engine** — base + distance + time + pickups + detour, demand adjustment, driver minimum top-up,
  platform commission (admin-editable), proportional fair split, competitiveness cap, pluggable benchmark.
* **Payments** — authorise at confirmation → capture at completion → driver payout; Stripe PaymentIntents with
  manual capture and Connect transfers behind a gateway interface (offline fake gateway by default).
* **Chat** — per-ride group chat (REST + WebSocket push), quick replies, phone numbers masked.
* **Safety** — emergency contacts, SOS, public live-trip share link, report/block, trip history.
* **Ratings** — category ratings both ways, written reviews, aggregated profiles.
* **Notifications** — all 14 event types, stored + pushed (Expo push queue in Redis) + WebSocket.
* **Privacy** — other riders appear only as neighbourhoods and ~1 km-snapped coordinates until/unless needed.
* **Admin** — role-protected API + web dashboard at `/admin-ui` (users, driver verification, rides, matching,
  payments & refunds, safety reports/SOS, platform fee, analytics).
* **Ops** — structured JSON logs for match/payment/ride events, Sentry hook, Docker, Alembic, GitHub Actions CI.

## The matching algorithm (the heart of the product)

`backend/app/services/matching_service.py` — pure functions, no DB, fully unit-tested.

1. **Compatibility score (0–100)** between two requests, weights configurable:
   route overlap 40 · departure-time similarity 20 · origin proximity 15 · destination proximity 15 · detour 10.
   *Overlap* compares route polylines inside a corridor and is **directional** (opposite directions score 0).
   *Proximity* is forgiving when one pickup lies *on the other's route* — a Coquitlam rider is a good fit for a
   Burnaby→Abbotsford trip even though the origins are 10 km apart.
2. **Hard feasibility** — departure gap ≤ 30 min, intersecting flexibility windows, seats, and everyone's detour
   within their *own* limit and the platform limit (so we never stretch a route just to fill seats).
3. **Grouping** — greedy best-first clustering: seed with the best-connected request, grow by highest mean pair
   score, accept a candidate only if the *whole group* still passes (time, seats, detours). Aim: ≥3 riders.
4. **Stop sequencing** — nearest-neighbour with pickup-before-drop-off + capacity constraints, then a relocate
   improvement pass. The `StopPlan` shape is solver-agnostic so OR-Tools VRP can replace `optimize_stops`.
5. **Driver assignment** — `evaluate_assignment` checks seats, pickup times vs each rider's window, driver and
   rider detours, **driver net earnings ≥ minimum**, and fare competitiveness; then scores
   route fit · profitability · passenger savings · seat utilisation · completion probability
   (`Overall 91 = …`), and ranks.
6. Both directions share that core: *passenger posts → group → find driver*, *driver posts → enumerate and
   rank passenger combinations*.

On the brief's example the engine groups A+B+C (compat ≈ 81, detours ≤ 21 min), the driver nets ≈ $65–79 after fees
and fuel, and riders pay ≈ $23–35 against a $57–113 solo benchmark.

## Pricing & fairness

```
Total trip cost = base + distance + time + (extra pickups) + detour, × demand multiplier
                  (topped up if needed so the driver clears their minimum earnings)
Platform fee    = commission × total      Driver payout = total − fee     Net = payout − fuel/wear
Passenger fare  = total × weighted share of {distance ridden 60%, time aboard 25%, detour caused 15%}
```

Shares sum **exactly** to the total (allocation is done in cents), have a per-passenger floor, and come with a
transparent breakdown. The "solo ride (est.)" price is a **configurable formula** (`PRICING__BENCHMARK_*`) — it is
not a quote from any company. Implement `BenchmarkProvider` to plug in a licensed price source later.

## Configuration

Everything tunable is an environment variable (nested with `__`), see `.env.example`:
`MATCHING__WEIGHTS__ROUTE_OVERLAP`, `MATCHING__MAX_PASSENGER_DETOUR_MIN`, `MATCHING__MAX_DEPARTURE_GAP_MIN`,
`PRICING__PLATFORM_COMMISSION_RATE` (also editable from the admin dashboard), `ROUTING_PROVIDER=offline|osrm`,
`PAYMENT_PROVIDER=fake|stripe`, `REDIS_URL`, …

## Payments (Stripe)

```
PAYMENT_PROVIDER=stripe  STRIPE_SECRET_KEY=sk_test_…
```
`/payments/create` makes a PaymentIntent (`capture_method=manual`) and returns its `client_secret`; the app
confirms it with Stripe's PaymentSheet (cards, Apple Pay, Google Pay — add `@stripe/stripe-react-native` and a
development build); `/payments/confirm` verifies it is `requires_capture`. Completion captures it and creates a
Connect transfer to the driver's `stripe_account_id`. No card data touches this server.

## Maps & routing

Out of the box a built-in **offline road network** (Metro Vancouver / Fraser Valley highway skeleton + Dijkstra)
makes the demo deterministic with no API keys. Set `ROUTING_PROVIDER=osrm` for real roads, or implement the
`RoutingProvider` protocol for Google/Mapbox/HERE. Geocoding uses a built-in gazetteer, optionally falling back to
Nominatim (`GEOCODER=nominatim`). Postgres runs on a PostGIS image; the MVP uses indexed lat/lng columns plus a
Redis GEO index (swap in PostGIS `ST_DWithin` when pools get large).

## Honest limitations (MVP)

* **Figma**: I couldn't open the shared Figma file from this environment (it needs a signed-in session), so the UI
  follows the written design direction. All colours/radii/spacing live in `mobile/src/theme.ts` for a quick re-skin.
* Matching re-groups the *whole* open pool on every change — fine to thousands of requests per region; shard by
  time bucket + geohash before that (see ARCHITECTURE → scaling).
* Background work (push delivery, matching) runs in-process via FastAPI background tasks; the entry points are
  isolated so Celery/RQ can take over. WebSocket rooms are in-process (use Redis pub/sub for multi-instance).
* A trip hosts one confirmed ride (one passenger group); driver trips don't yet serve multiple groups.
* Third-party verification, Apple sign-in, SMS and live driver GPS are provider seams, not integrations.
* Dev builds can't run Stripe's native sheet in Expo Go; use a development build.
* The offline road model is a coarse approximation; use OSRM/Google for production accuracy.

## Testing

```bash
cd backend && pytest -q          # unit + API tests (pricing, routing, matching, state machine, auth, permissions, full ride lifecycle)
cd mobile  && npm run typecheck
```
