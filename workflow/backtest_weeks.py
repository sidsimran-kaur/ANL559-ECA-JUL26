"""Baseline ladder for the rebalancing rule, on every complete week that has 4 earlier complete weeks.
Each week's opening targets are set ONLY from the 4 weeks before it, then the week is replayed.

    cd workflow && python backtest_weeks.py

Rungs (simplest first), scored by riders turned away (no bike or no free dock) and bikes moved per day:
  0 do nothing       no trucks at all: stations start half full on the first test day, stock carries over
  1 open full        every station reset to full each night
  2 open half        every station reset to half full each night (a rule a manager could apply without data)
  3 single signal    reset to the average daily loss only (one signal, ignores free docks)
  4 targets          our rule: middle of the safe range, overnight only
  5 targets + midday our rule plus an 11:00 reset
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import weekly_report as w

ROOT = Path(__file__).resolve().parents[1]
t = pd.read_csv(ROOT / "data/raw/CityCycle_trips.csv", parse_dates=["start_time", "end_time"])
cap = pd.read_csv(ROOT / "data/raw/CityCycle_stations.csv").set_index("station").capacity
weeks = w.complete_weeks(t)
test_weeks = weeks[w.TARGET_WEEKS:]


def do_nothing(trips, start):
    ev = w.events(trips); stock = {k: int(v) for k, v in start.items()}; turned = 0
    for st, d in zip(ev.station, ev.d):
        if d < 0:
            if stock[st] == 0: turned += 1
            else: stock[st] -= 1
        elif stock[st] == cap[st]: turned += 1
        else: stock[st] += 1
    return turned


def avg_loss(prior):
    ev = w.events(prior)
    run = ev.assign(run=ev.groupby(["station", "day"]).d.cumsum()).groupby(["station", "day"]).run
    return (-run.min()).clip(lower=0).groupby("station").mean().round().reindex(cap.index).fillna(0)


RUNGS = ["1 open full", "2 open half", "3 single signal", "4 targets (our rule)", "5 targets + midday"]
rows = []
for i, wk in enumerate(weeks):
    if i < w.TARGET_WEEKS:
        continue
    prior = t[t.start_time.dt.to_period("W-SUN").isin(weeks[i - w.TARGET_WEEKS:i])]
    this = t[t.start_time.dt.to_period("W-SUN") == wk]
    tg = w.opening_targets(prior, cap).target
    row = {"week_starting": str(wk.start_time.date())}
    for name, start, mid in zip(RUNGS, [cap, (cap / 2).round(), avg_loss(prior), tg, tg],
                                [None, None, None, None, w.MIDDAY_RUN]):
        r = w.simulate(this, cap, start, mid)[0]
        row[name] = r["riders_no_bike"] + r["riders_no_dock"]
        row[name + " | bikes/day"] = r["bikes_moved_per_day"]
    rows.append(row)
df = pd.DataFrame(rows)
df.to_csv(ROOT / "out" / "backtest_rebalancing_by_week.csv", index=False)

span = t[t.start_time.dt.to_period("W-SUN").isin(test_weeks)]
ladder = pd.DataFrame({
    "rule": ["0 do nothing"] + RUNGS,
    "riders_turned_away": [do_nothing(span, (cap / 2).round())] + [int(df[r].sum()) for r in RUNGS],
    "bikes_moved_per_day": [0.0] + [round(df[r + " | bikes/day"].mean(), 1) for r in RUNGS],
})
ladder.to_csv(ROOT / "out" / "baseline_ladder.csv", index=False)
print(df.to_string(index=False)); print(); print(ladder.to_string(index=False))

# chart
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
lab = ["Do nothing (no trucks)", "Open every station full", "Open every station half full",
       "Single signal: average loss only", "Station targets, overnight (our rule)", "Station targets + midday run"]
d = ladder.assign(label=lab).iloc[::-1]
fig, ax = plt.subplots(figsize=(8.5, 3.8)); ax.set_facecolor(SURF); fig.patch.set_facecolor(SURF)
cols = ["#2a78d6" if "our rule" in l else ("#9fc2ec" if "midday" in l else "#c9c8c3") for l in d.label]
ax.barh(d.label, d.riders_turned_away, color=cols, height=0.65)
for y, (n, b) in enumerate(zip(d.riders_turned_away, d.bikes_moved_per_day)):
    ax.text(n + 20, y, f"{n:,} riders   ({b:.1f} bikes moved a day)", va="center", fontsize=8, color=INK2)
for sp in ["top", "right", "left"]:
    ax.spines[sp].set_visible(False)
ax.spines["bottom"].set_color(GRID); ax.tick_params(colors=INK2, length=0, labelsize=8.5); ax.xaxis.grid(True, color=GRID, lw=0.8)
ax.set_axisbelow(True); ax.set_xlim(0, ladder.riders_turned_away.max() * 1.45)
ax.set_xlabel(f"Riders turned away (no bike or no free dock), {len(test_weeks)} weeks not used to set the targets", color=INK2, fontsize=8.5)
ax.set_title("Nightly rebalancing is what matters; targets edge out a half-full rule", loc="left", color=INK, fontsize=11.5, fontweight="bold")
fig.tight_layout(); fig.savefig(ROOT / "out" / "chart_baseline_ladder.png", dpi=200); plt.close(fig)
