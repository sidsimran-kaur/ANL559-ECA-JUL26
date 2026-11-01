"""Evidence check: recompute the worked-example week's key figures with a different method
(plain csv module, no pandas) and compare them with facts.json.

    python workflow/independent_check.py 2026-03-23
"""
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ws = datetime.fromisoformat(sys.argv[1]); we = ws + timedelta(days=7)
facts = json.loads((ROOT / "out" / f"week_{sys.argv[1]}" / "facts.json").read_text())
P = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

trips = [r for r in csv.DictReader(open(ROOT / "data/raw/CityCycle_trips.csv")) if ws <= P(r["start_time"]) < we]
fb = [r for r in csv.DictReader(open(ROOT / "data/raw/CityCycle_feedback.csv"))
      if ws <= datetime.fromisoformat(r["date"]) < we]
weekdays = {P(r["start_time"]).date() for r in trips if P(r["start_time"]).weekday() < 5}

def am_net(station):
    dep = sum(1 for r in trips if r["start_station"] == station and P(r["start_time"]).weekday() < 5
              and 7 <= P(r["start_time"]).hour < 9)
    arr = sum(1 for r in trips if r["end_station"] == station and P(r["end_time"]).weekday() < 5
              and 7 <= P(r["end_time"]).hour < 9)
    return round((dep - arr) / len(weekdays), 1)

neg_words = ("crash", "failed", "wrong", "no bikes", "hard to find", "full", "loose", "flat", "wobbly",
             "slipping", "twice", "late fee")
checks = [
    ("Trips in week", len(trips), facts["trips"]["total"]),
    ("Trips per day", round(len(trips) / 7, 1), facts["trips"]["per_day"]),
    ("Changi Business Park starts", Counter(r["start_station"] for r in trips)["Changi Business Park"],
     facts["busiest_start_stations"]["Changi Business Park"]),
    ("Tanjong Pagar morning net loss", am_net("Tanjong Pagar"), facts["morning_peak_draining"]["Tanjong Pagar"]),
    ("Raffles Place morning net loss", am_net("Raffles Place"), facts["morning_peak_draining"]["Raffles Place"]),
    ("Comments in week", len(fb), facts["feedback"]["total"]),
    ("Negative comments (keyword rule)", sum(any(w in r["comment_text"] for w in neg_words) for r in fb),
     facts["feedback"]["negative"]),
    ("Average rating", round(sum(int(r["rating"]) for r in fb) / len(fb), 2), facts["feedback"]["avg_rating"]),
]
ok = True
print(f"{'Figure':36s}{'Independent':>12s}{'facts.json':>12s}  Result")
for name, mine, theirs in checks:
    match = abs(float(mine) - float(theirs)) < 1e-9
    ok &= match
    print(f"{name:36s}{mine:>12}{theirs:>12}  {'MATCH' if match else 'DIFFERENT'}")
sys.exit(0 if ok else 1)
