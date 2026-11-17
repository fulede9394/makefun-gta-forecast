# GTA VI Launch-Day Twitch Forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/fulede9394/makefun-gta-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/fulede9394/makefun-gta-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Entry for the [make.fun bounty gta6-twitch-ccu-forecast-01](https://make.fun/bounty/gta6-twitch-ccu-forecast-01): forecast how many
people watch Grand Theft Auto VI live on Twitch in each hour of its release day
(2026-11-19 UTC), after the first hour. The program reads one case file per run
and writes five quantiles (5/25/50/75/95%) for each of hours 2–24.

> make.fun referral: https://make.fun/r/5kkq1ant

## How it works

`main.py` (Python 3.13, standard library only, no network) anchors on the
case's own hour-1 print and predicts log-ratios `ln(viewers_h / viewers_1)`
from the case's comparables — past big launches' hourly Twitch category counts
(SullyGnome hourly averages).

Two fits are blended by the size of the hour-1 print:

- **Fit A** — every usable comparable (excluding early-access-contaminated,
  weak, and the target's own pre-launch history): a per-hour least-squares
  line of the log-ratio on `ln(hour-1 print)`. Hour 1's size is a strong
  predictor of the day's shape — small hour-1 prints belong to launches whose
  regions unlock later, so their curves climb steeply; huge hour-1 prints
  belong to launches that were already global by midnight, so their curves
  stay flat.
- **Fit B** — the rolling-midnight subset (substantial hour 1, evening hours
  clearly above early hours): a level-plus-shape decomposition. The median
  centred curve gives the shape (overnight dip, US unlocks at 05:00Z and
  08:00Z, evening peak around 20:00–21:00Z, slow decay); the level is a
  least-squares line on `ln(hour-1 print)`, capped at the subset's largest
  hour-1 print so the forecast never extrapolates past the biggest rolling
  launch observed.

The blend puts 85% weight on Fit A while the hour-1 print is at most 150k,
full weight on Fit B once it reaches 500k, and interpolates linearly in
`ln(p1)` between. Both fits clamp the size predictor to their observed
hour-1 range, so no forecast extrapolates past the comparables. Spreads are
the fits' residual standard deviations, shrunk (×0.30 for A, ×0.35 for B) and
floored at 0.10 in log units.

## Validation (practice cases)

Scored locally against the four practice launches' release-day hourly counts
(Marvel's Wolverine, Red Dead Redemption 2, God of War Ragnarök, Marvel's
Spider-Man 2 — SullyGnome hourly averages, fetched from the source the kit's
`NOTICE.txt` documents):

| case | pinball loss | typical miss | 90% coverage | baseline loss |
|------|-------------|--------------|--------------|---------------|
| p00 Wolverine | 0.104 | 17% | 0.91 | 0.744 |
| p01 RDR2 | 0.119 | 22% | 0.87 | 0.287 |
| p02 God of War Ragnarök | 0.087 | 15% | 1.00 | 0.215 |
| p03 Spider-Man 2 | 0.191 | 33% | 0.74 | 0.303 |
| **mean** | **0.125** | **22%** | **0.88** | **0.387** |

The forecast beats the house baseline (flat at the hour-1 print, spread
widening as `0.15·sqrt(h−1)`) on every practice case. Two runs on the same
input are byte-identical; runtime is ~0.06 s per case.

## Run it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `*.in` in the input directory and writes `<id>.out` per case:
`{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, …]}`.

## Files

- `main.py` — the entry point (the whole model, single file).
- `LICENSE` — MIT.
- `.makefun/owner.json` — payout wallet for the entry.
