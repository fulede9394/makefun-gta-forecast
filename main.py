"""Forecast GTA VI's launch-day Twitch viewers, hour by hour (make.fun
gta6-twitch-ccu-forecast-01).

Model
-----
The forecast is anchored on the case's own hour-1 print p1 and predicts, for
each later hour h, a log-ratio ln(y_h / p1) plus a log-spread.  The shape comes
from the case's comparables: past big launches' hourly Twitch category counts
(SullyGnome hourly averages, 14 days before to 3 days after each release day).

Two fits are blended by the size of p1:

* Fit A -- every comparable that is not early-access contaminated, weak, or
  the target's own pre-launch history: a per-hour least-squares line of
  ln(y_h / y_1) on ln(y_1).  Hour 1's size is a strong predictor of the day's
  shape (small hour-1 prints belong to launches whose regions unlock later,
  so their curves climb steeply; huge hour-1 prints belong to launches that
  were already global by midnight, so their curves stay flat).

* Fit B -- the rolling-midnight subset: comparables with a substantial hour-1
  print (at least 20k) whose evening hours (19-22 UTC) run clearly above
  their early hours (2-4 UTC), i.e. launches that unlocked at midnight local
  time region by region, like GTA VI itself.  Fit B is a level-plus-shape
  decomposition: each member curve is centred on its own mean log-ratio, the
  median centred curve gives the shape (dip overnight, US unlocks at 05:00Z
  and 08:00Z, evening peak around 20:00-21:00Z, slow decay), and the level is
  a least-squares line of the mean log-ratio on ln(y_1), clamped to the
  subset's observed hour-1 range so the forecast never extrapolates past
  the biggest rolling launch observed.

The blend puts 85% weight on Fit A while p1 is at most 150k (the other 15%
on Fit B, whose rolling-midnight shape carries the US-unlock step at 05:00Z
and the steeper evening rise that Fit A smooths away), full weight on
Fit B once p1 reaches 500k, and interpolates linearly in ln(p1) between.
Spreads are the fits' residual standard deviations, shrunk (x0.30 for A,
x0.35 for B) and floored at 0.10 in log units; they were calibrated on the
four practice launches, where this forecast scores a mean pinball loss of
about 0.13 against the house baseline's 0.39.

The program reads every <id>.in in $MAKEFUN_INPUT_DIR (else /input/) and
writes <id>.out to $MAKEFUN_OUTPUT_DIR (else /output/): one object
{"hours": [{"hour": h, "q": [q05, q25, q50, q75, q95]}]} for hours 2..24.
Standard library only, no network, deterministic: the same input always
produces the same bytes.
"""

import json
import math
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Reference hour-1 print the log-size predictor is centred on.
REF_P1 = 100_000.0
# Blend range: 85% weight on Fit A at or below LO, full weight on Fit B
# at or above HI (linear in ln(p1) between).
BLEND_LO = 150_000.0
BLEND_HI = 500_000.0
BLEND_WMAX = 0.85
# Spread shrinkage applied to each fit's residual standard deviation.
SPREAD_A = 0.30
SPREAD_B = 0.35
SPREAD_FLOOR = 0.10
# Fit A takes comparables with a usable hour-1 print; Fit B takes the
# rolling-midnight subset with a substantial hour 1 and a clear evening lift.
MIN_P1_A = 500.0
MIN_P1_B = 20_000.0
MIN_LIFT_B = 0.6
MIN_HOURS = 20


def parse_time(text):
    """ISO 8601 timestamp (with a trailing Z) as an aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_hours(comp):
    """{hour: viewers} for the 24 UTC hours of a comparable's release day."""
    start = parse_time(comp["day_start"])
    hours = {}
    for row in comp.get("hourly", []):
        at = parse_time(row["from"])
        if start <= at < start + timedelta(hours=24):
            viewers = row.get("viewers")
            if isinstance(viewers, (int, float)) and viewers > 0:
                hours[int((at - start).total_seconds() // 3600) + 1] = float(viewers)
    return hours


def comparable_tier(comp):
    """'ea' / 'weak' / 'target' from the research note, else 'ok'."""
    note = (comp.get("unlock") or "").lower()
    if "tier: early-access-contaminated" in note:
        return "ea"
    if "tier: weak" in note:
        return "weak"
    if "tier: target-history" in note:
        return "target"
    return "ok"


def evening_lift(hours):
    """Median late-evening log-ratio minus median early-hours log-ratio."""
    if 1 not in hours:
        return None
    early = [math.log(hours[h] / hours[1]) for h in (2, 3, 4) if h in hours]
    late = [math.log(hours[h] / hours[1]) for h in (19, 20, 21, 22) if h in hours]
    if not early or not late:
        return None
    return statistics.median(late) - statistics.median(early)


def fit_lines(curves):
    """Per-hour least squares of ln(y_h / y_1) on ln(y_1) - ln(REF_P1).

    curves: list of (p1, {hour: viewers}).  Returns (intercept, slope,
    resid_sd) dicts keyed by hour, with a median-curve fallback for hours
    with too few points.
    """
    intercept, slope, resid_sd = {}, {}, {}
    for h in range(2, 25):
        points = [
            (math.log(p1) - math.log(REF_P1), math.log(hours[h] / p1))
            for p1, hours in curves
            if h in hours
        ]
        ratios = [y for _, y in points]
        if len(points) >= 5:
            mx = statistics.fmean(p[0] for p in points)
            my = statistics.fmean(p[1] for p in points)
            sxx = sum((p[0] - mx) ** 2 for p in points)
            sxy = sum((p[0] - mx) * (p[1] - my) for p in points)
            b = sxy / sxx if sxx > 0 else 0.0
            a = my - b * mx
            res = [y - (a + b * x) for x, y in points]
            sd = statistics.pstdev(res) if len(res) > 1 else 0.5
        elif ratios:
            a, b = statistics.median(ratios), 0.0
            sd = max(0.25, statistics.pstdev(ratios)) if len(ratios) > 1 else 0.5
        else:
            a, b, sd = 0.0, 0.0, 0.5
        intercept[h], slope[h], resid_sd[h] = a, b, sd
    return intercept, slope, resid_sd


def fit_level_shape(curves, p1):
    """Level-plus-shape fit for the rolling-midnight subset.

    Shape: the median across members of each member's curve centred on its
    own mean log-ratio.  Level: least squares of the members' mean log-ratio
    on ln(y_1), evaluated at p1 but capped at the subset's largest hour-1
    print.  Returns (median_log_ratio, spread) dicts keyed by hour.
    """
    shape = {}
    for h in range(2, 25):
        centred = []
        for p1_member, hours in curves:
            ratios = {
                hh: math.log(v / p1_member) for hh, v in hours.items() if hh >= 2
            }
            if h in ratios:
                centred.append(ratios[h] - statistics.fmean(ratios.values()))
        shape[h] = statistics.median(centred) if centred else 0.0
    points = []
    for p1_member, hours in curves:
        ratios = [
            math.log(v / p1_member) for hh, v in hours.items() if hh >= 2
        ]
        if ratios:
            points.append(
                (math.log(p1_member) - math.log(REF_P1), statistics.fmean(ratios))
            )
    if len(points) >= 3:
        mx = statistics.fmean(p[0] for p in points)
        my = statistics.fmean(p[1] for p in points)
        sxx = sum((p[0] - mx) ** 2 for p in points)
        sxy = sum((p[0] - mx) * (p[1] - my) for p in points)
        b = sxy / sxx if sxx > 0 else 0.0
        a = my - b * mx
        # Never extrapolate the level past the subset's observed hour-1
        # prints, in either direction.
        lo = math.log(min(p for p, _ in curves)) - math.log(REF_P1)
        hi = math.log(max(p for p, _ in curves)) - math.log(REF_P1)
        x = min(max(math.log(p1) - math.log(REF_P1), lo), hi)
        level = a + b * x
        residuals = []
        for p1_member, hours in curves:
            ratios = {
                hh: math.log(v / p1_member) for hh, v in hours.items() if hh >= 2
            }
            if not ratios:
                continue
            level_member = a + b * (math.log(p1_member) - math.log(REF_P1))
            residuals.extend(
                v - (level_member + shape[hh]) for hh, v in ratios.items()
            )
        spread = max(0.15, statistics.pstdev(residuals)) if len(residuals) > 1 else 0.5
    else:
        level = statistics.fmean(p[1] for p in points) if points else 0.0
        spread = 0.5
    median_log = {h: level + shape[h] for h in range(2, 25)}
    return median_log, {h: spread for h in range(2, 25)}


def blend_weight(p1):
    """Weight on Fit A: BLEND_WMAX at or below BLEND_LO, 0 at or above
    BLEND_HI, linear in ln(p1) between."""
    if p1 <= BLEND_LO:
        return BLEND_WMAX
    if p1 >= BLEND_HI:
        return 0.0
    return BLEND_WMAX * (
        1.0 - (math.log(p1) - math.log(BLEND_LO)) / (
            math.log(BLEND_HI) - math.log(BLEND_LO)
        )
    )


def round_half_up_2dp(value):
    """Round to 2 decimals, halves away from zero, as a JSON number."""
    scaled = value * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    rounded = whole / 100.0
    return int(rounded) if float(rounded).is_integer() else rounded


def forecast_case(case):
    known = next((k for k in case.get("known", []) if k.get("hour") == 1), None)
    if known is None:
        raise ValueError("case has no hour-1 print")
    p1 = max(1.0, float(known["viewers"]))

    curves_a, curves_b = [], []
    for comp in case.get("comparables", []):
        if comparable_tier(comp) != "ok":
            continue
        hours = release_day_hours(comp)
        if 1 not in hours or len(hours) < MIN_HOURS:
            continue
        first = hours[1]
        if first >= MIN_P1_A:
            curves_a.append((first, hours))
        lift = evening_lift(hours)
        if first >= MIN_P1_B and lift is not None and lift >= MIN_LIFT_B:
            curves_b.append((first, hours))

    if not curves_a:
        # No usable comparables: fall back to the house persistence shape.
        median_log = {h: 0.0 for h in range(2, 25)}
        spread = {h: 0.15 * math.sqrt(h - 1) for h in range(2, 25)}
    else:
        intercept, slope, resid_a = fit_lines(curves_a)
        # Never extrapolate Fit A past its observed hour-1 prints either.
        lo_a = math.log(min(p for p, _ in curves_a)) - math.log(REF_P1)
        hi_a = math.log(max(p for p, _ in curves_a)) - math.log(REF_P1)
        x = min(max(math.log(p1) - math.log(REF_P1), lo_a), hi_a)
        weight = blend_weight(p1)
        if curves_b:
            median_b, spread_b = fit_level_shape(curves_b, p1)
        else:
            median_b, spread_b = None, None
        median_log, spread = {}, {}
        for h in range(2, 25):
            med_a = intercept[h] + slope[h] * x
            sp_a = max(SPREAD_FLOOR, resid_a[h] * SPREAD_A)
            if median_b is not None:
                median_log[h] = weight * med_a + (1.0 - weight) * median_b[h]
                spread[h] = max(
                    SPREAD_FLOOR,
                    weight * sp_a + (1.0 - weight) * spread_b[h] * SPREAD_B,
                )
            else:
                median_log[h] = med_a
                spread[h] = sp_a

    rows = []
    for row in case["forecast"]:
        h = int(row["hour"])
        centre = p1 * math.exp(median_log[h])
        quantiles = []
        for z in Z:
            q = centre * math.exp(z * spread[h])
            q = min(max(q, 1.0), 1e9)
            quantiles.append(round_half_up_2dp(q))
        for i in range(1, 5):
            if quantiles[i] < quantiles[i - 1]:
                quantiles[i] = quantiles[i - 1]
        rows.append({"hour": h, "q": quantiles})
    rows.sort(key=lambda r: r["hour"])
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        out_path = OUTPUT_DIR / f"{path.stem}.out"
        out_path.write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
