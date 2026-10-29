# Matching & pricing — worked example

Inputs (tomorrow): **A** Burnaby→Abbotsford 10:00 · **B** Coquitlam→Abbotsford 9:50 · **C** Burnaby→Langley 10:10,
each ±30 min, detour limit 25 min. Driver: Vancouver→Abbotsford 9:30, 4 seats, ≤30 min detour, min earnings $55.

| Pair | Overlap | Time | Origin | Dest | Detour | **Score** |
|---|---|---|---|---|---|---|
| A–B | 97 | 67 | 61 | 100 | 58 | **82** |
| A–C | 100 | 67 | 100 | 89 | 59 | **88** |
| B–C | 94 | 33 | 61 | 89 | 58 | **73** |

All three are feasible (≥ threshold 55, within detours) → one group of 3. Optimised sequence
`A↑ C↑ B↑ C↓ B↓ A↓` (C is dropped at Langley on the way). Driver match: score route-fit 85 · profitability 100 ·
savings 97 · seats 75 · completion 95 → **overall ≈ 91**.

Fares are split by distance, time aboard and detour caused — B pays slightly more than A for a similar trip because
picking B up costs everyone a detour. Run `python -m app.seed` to see the live numbers.

## Why directional corridor overlap?

Comparing only origin/destination misses most good groupings. We resample each route to ~1.5 km, mark samples that lie
within `corridor_km` of the other route *and* progress in the same direction along it, and report the shared length
over the shorter route. Burnaby→Langley is a 90 % sub-route of Burnaby→Abbotsford; Abbotsford→Burnaby is 0 %.

## Tuning

| Env var | Effect |
|---|---|
| `MATCHING__WEIGHTS__*` | importance of overlap / time / origin / destination / detour |
| `MATCHING__SCORE_THRESHOLD` | minimum compatibility to be considered |
| `MATCHING__MAX_PASSENGER_DETOUR_MIN`, `MAX_DRIVER_DETOUR_MIN`, `MAX_DEPARTURE_GAP_MIN` | reasonableness limits |
| `MATCHING__MIN_GROUP_SIZE` / `MAX_GROUP_SIZE` | when a driver search starts / seats per car |
| `PRICING__*` | rates, commission, fairness weights, competitiveness cap, benchmark formula |
