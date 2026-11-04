"""Evidence check: recompute key figures for a reporting week with a different method
(plain csv module, no pandas) and compare them with that week's facts.json.

    python workflow/independent_check.py 2026-03-23
"""
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
week = sys.argv[1]
ws = datetime.fromisoformat(week); we = ws + timedelta(days=7)
facts = json.loads((ROOT / "out" / f"week_{week}" / "facts.json").read_text())
P = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

all_trips = list(csv.DictReader(open(ROOT / "data/raw/CityCycle_trips.csv")))
trips = [r for r in all_trips if ws <= P(r["start_time"]) < we]
all_fb = list(csv.DictReader(open(ROOT / "data/raw/CityCycle_feedback.csv")))
fb = [r for r in all_fb if ws <= datetime.fromisoformat(r["date"]) < we]
fb_to_date = [r for r in all_fb if datetime.fromisoformat(r["date"]) < we]
weekdays = {P(r["start_time"]).date() for r in trips if P(r["start_time"]).weekday() < 5}


def morning_net(station):                       # approved morning peak 08:00-10:00, weekdays
    dep = sum(1 for r in trips if r["start_station"] == station and P(r["start_time"]).weekday() < 5
              and 8 <= P(r["start_time"]).hour < 10)
    arr = sum(1 for r in trips if r["end_station"] == station and P(r["end_time"]).weekday() < 5
              and 8 <= P(r["end_time"]).hour < 10)
    return round((dep - arr) / len(weekdays), 2)


# busiest weekday morning hour across all data up to the week's end
upto = [r for r in all_trips if P(r["start_time"]) < we and P(r["start_time"]).weekday() < 5]
busiest_am = Counter(P(r["start_time"]).hour for r in upto if P(r["start_time"]).hour < 12).most_common(1)[0][0]
busiest_pm = Counter(P(r["start_time"]).hour for r in upto if P(r["start_time"]).hour >= 15).most_common(1)[0][0]

sys.path.insert(0, str(Path(__file__).parent))
from truth import mann_whitney_p, THEME_OF  # noqa: E402  (csv-only implementation, not the pipeline's scipy)


def flagged(rows):
    out = {}
    for text, theme in THEME_OF.items():
        mine = [int(r["rating"]) for r in rows if r["comment_text"] == text]
        rest = [int(r["rating"]) for r in rows if r["comment_text"] != text]
        if mine and round(mann_whitney_p(mine, rest), 4) < 0.01:
            out[theme] = "watch closely" if sum(mine) / len(mine) < sum(rest) / len(rest) else "ratings unaffected"
    return out


now_f = flagged([r for r in all_fb if datetime.fromisoformat(r["date"]) < we])
prev_f = flagged([r for r in all_fb if datetime.fromisoformat(r["date"]) < ws])
changes = sorted(f"{t}: {prev_f.get(t, 'not flagged')} -> {now_f.get(t, 'not flagged')}"
                 for t in set(now_f) | set(prev_f) if now_f.get(t) != prev_f.get(t))

neg_words = ("crash", "failed", "wrong", "no bikes", "hard to find", "full", "loose", "flat", "wobbly",
             "slipping", "twice", "late fee")
reb = facts["rebalancing"]
checks = [
    ("Trips in week", len(trips), facts["trips"]["total"]),
    ("Trips per day", round(len(trips) / 7, 1), facts["trips"]["per_day"]),
    ("Changi Business Park starts", Counter(r["start_station"] for r in trips)["Changi Business Park"],
     facts["busiest_start_stations"].get("Changi Business Park", 0)),
    ("Tanjong Pagar morning net loss", morning_net("Tanjong Pagar"), facts["morning_peak_losing_bikes"]["Tanjong Pagar"]),
    ("Raffles Place morning net loss", morning_net("Raffles Place"), facts["morning_peak_losing_bikes"]["Raffles Place"]),
    ("Busiest weekday morning hour", busiest_am, 8),
    ("Busiest weekday evening hour", busiest_pm, 18),
    ("Comments in week", len(fb), facts["feedback_week"]["total"]),
    ("Negative comments in week", sum(any(w in r["comment_text"] for w in neg_words) for r in fb),
     facts["feedback_week"]["negative"]),
    ("Safety comments to date (brakes + gears)",
     sum(r["comment_text"] in ("brakes felt loose", "gears slipping") for r in fb_to_date),
     facts["feedback_to_week_end"]["safety_mentions"]),
    ("Rating-pattern changes vs last week (count)", len(changes), len(facts["feedback_week"]["rating_pattern_changes_vs_last_week"])),
    ("Rating-pattern changes identical (1 = yes)", int(changes == facts["feedback_week"]["rating_pattern_changes_vs_last_week"]), 1),
    ("Plan balances: delivered = collected", sum(reb["weekday_deliver"].values()), sum(reb["weekday_collect"].values())),
]
ok = True
print(f"{'Figure':42s}{'Independent':>12s}{'Pipeline':>10s}  Result")
for name, mine, theirs in checks:
    match = abs(float(mine) - float(theirs)) < 1e-9
    ok &= match
    print(f"{name:42s}{mine:>12}{theirs:>10}  {'MATCH' if match else 'DIFFERENT'}")
sys.exit(0 if ok else 1)
