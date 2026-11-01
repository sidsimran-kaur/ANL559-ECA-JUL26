"""Robustness check: replay every complete week that has 4 earlier complete weeks, with opening targets
set ONLY from those 4 earlier weeks, under overnight-only and overnight + midday rebalancing.

    python workflow/backtest_weeks.py
"""
from pathlib import Path
import pandas as pd
import weekly_report as w

ROOT = Path(__file__).resolve().parents[1]
t = pd.read_csv(ROOT / "data/raw/CityCycle_trips.csv", parse_dates=["start_time", "end_time"])
cap = pd.read_csv(ROOT / "data/raw/CityCycle_stations.csv").set_index("station").capacity
weeks = w.complete_weeks(t)
rows = []
for i, wk in enumerate(weeks):
    if i < w.TARGET_WEEKS:
        continue
    prior = weeks[i - w.TARGET_WEEKS:i]
    targets = w.opening_targets(t[t.start_time.dt.to_period("W-SUN").isin(prior)], cap).target
    this = t[t.start_time.dt.to_period("W-SUN") == wk]
    a = w.simulate(this, cap, targets)[0]; b = w.simulate(this, cap, targets, w.MIDDAY_RUN)[0]
    rows.append({"week_starting": str(wk.start_time.date()),
                 "overnight_riders_turned_away": a["riders_no_bike"] + a["riders_no_dock"],
                 "overnight_close_calls": a["close_call_station_days"], "overnight_bikes_per_day": a["bikes_moved_per_day"],
                 "midday_riders_turned_away": b["riders_no_bike"] + b["riders_no_dock"],
                 "midday_close_calls": b["close_call_station_days"], "midday_bikes_per_day": b["bikes_moved_per_day"]})
df = pd.DataFrame(rows)
df.to_csv(ROOT / "out" / "backtest_rebalancing_by_week.csv", index=False)
print(df.to_string(index=False))
print("\nTotals:", df.drop(columns="week_starting").sum().to_dict())
