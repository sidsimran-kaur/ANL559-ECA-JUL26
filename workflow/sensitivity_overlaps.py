"""Sensitivity check: does dropping one trip from every overlapping-bike pair change any result?

    cd workflow && python sensitivity_overlaps.py
"""
from pathlib import Path
import pandas as pd
import weekly_report as w

ROOT = Path(__file__).resolve().parents[1]
t = pd.read_csv(ROOT / "data/raw/CityCycle_trips.csv", parse_dates=["start_time", "end_time"])
cap = pd.read_csv(ROOT / "data/raw/CityCycle_stations.csv").set_index("station").capacity
ts = t.sort_values(["bike_id", "start_time"]).reset_index(drop=True)
first = ts.index[ts.groupby("bike_id").start_time.shift(-1) < ts.end_time]
second_ids = set(ts.loc[first + 1, "trip_id"])
week = w.complete_weeks(t)[-1]
rows = []
for label, d in [("keep all trips", t), ("drop second trip of each pair", t[~t.trip_id.isin(second_ids)])]:
    hist = d[d.start_time < week.start_time]
    prior = w.complete_weeks(hist)[-w.TARGET_WEEKS:]
    targets = w.opening_targets(hist[hist.start_time.dt.to_period("W-SUN").isin(prior)], cap).target
    this = d[d.start_time.dt.to_period("W-SUN") == week]
    sim = w.simulate(this, cap, targets)[0]
    rows.append({"version": label, "trips": len(d), "trips_in_latest_week": len(this),
                 "peaks": ", ".join(w.fmt_window(a, b) for a, b in w.detect_peaks(d)[3]),
                 "targets_sum": int(targets.sum()), "riders_turned_away": sim["riders_no_bike"] + sim["riders_no_dock"],
                 "bikes_moved_per_day": sim["bikes_moved_per_day"]})
df = pd.DataFrame(rows)
df.to_csv(ROOT / "out" / "sensitivity_overlapping_trips.csv", index=False)
print(df.to_string(index=False))
print("\nSame result either way:", df.drop(columns=["version", "trips"]).nunique().le(1).all())
