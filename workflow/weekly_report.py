"""CityCycle weekly operations report: the deterministic core of the automation (v2).

    python workflow/weekly_report.py                          # latest complete week (default)
    python workflow/weekly_report.py --week-start 2026-03-16  # any other reporting week

Outputs go to out/week_<Monday>/. The reporting week comes first; all earlier data gives the context
(peak-hour consistency, opening targets, trends).

Step 1 VALIDATE   data contract on the reporting week; a FAIL stops the run
Step 2 COMPUTE    peak hours detected from the data and checked for consistency; station flows per peak
Step 3 REBALANCE  opening target per station; overnight vs midday rebalancing simulated; nightly move plan
Step 4 CLASSIFY   approved taxonomy: sentiment from text, severity from stars, safety (brakes, gears) flagged
Step 5 FACTS      facts.json: the ONLY numbers the language model may quote; charts
The LLM then drafts the report from facts.json, and verify_report.py / independent_check.py check it.
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

# ---- approved definitions (work_order.md v2.0); changing one needs a new sign-off ----------------
PEAKS = {"Morning peak (08:00-10:00)": (8 * 60, 10 * 60),
         "Lunch peak (12:00-13:00)": (12 * 60, 13 * 60),
         "Evening peak (17:00-20:00)": (17 * 60, 20 * 60)}
PEAK_RULE = 1.5             # a 30-min weekday slot is "peak" if its demand >= 1.5 x the weekday average slot
MIDDAY_RUN = 11 * 60        # candidate midday rebalancing time: the quiet gap between morning and lunch peaks
TARGET_WEEKS = 4            # opening targets use the latest 4 complete weeks
TARGET_PCTL = 0.90          # enough bikes / free docks for 9 days in 10
SAFETY_THEMES = {"Brakes loose", "Gears slipping"}
HOLIDAYS = {"2026-02-16": "Chinese New Year"}

# Feedback taxonomy v1.1: drafted by the LLM, reviewed and approved by the analyst. text -> (theme, sentiment)
THEMES = {
    "the app keeps crashing when I unlock": ("App crash on unlock", "negative"),
    "payment failed in the app twice": ("App payment failure", "negative"),
    "app GPS shows wrong station": ("App GPS wrong station", "negative"),
    "love how easy the app is to use": ("Praise - app", "positive"),
    "no bikes available at my station in the morning": ("No bikes (morning)", "negative"),
    "hard to find a bike at peak hour": ("No bikes (peak hour)", "negative"),
    "docks were all full, couldn't return": ("Docks full, can't return", "negative"),
    "always bikes at Bishan, great": ("Praise - availability", "positive"),
    "brakes felt loose": ("Brakes loose", "negative"),
    "tyre was flat": ("Flat tyre", "negative"),
    "seat was wobbly": ("Wobbly seat", "negative"),
    "gears slipping": ("Gears slipping", "negative"),
    "bike was in great condition": ("Praise - bike", "positive"),
    "charged twice for one ride": ("Double charge", "negative"),
    "unexpected late fee": ("Unexpected late fee", "negative"),
    "super convenient for my commute": ("Praise - general", "positive"),
    "great value membership": ("Praise - general", "positive"),
    "clean and well-maintained bikes": ("Praise - bike", "positive"),
}
URA_REGION = {"Raffles Place": "Central", "Tanjong Pagar": "Central", "Marina Bay": "Central", "Bugis": "Central",
              "Orchard": "Central", "Somerset": "Central", "Tampines Hub": "East", "Jurong East": "West",
              "Bishan": "Central", "Woodlands": "North", "Pasir Ris": "East", "Sentosa": "Central",
              "one-north": "Central", "Buona Vista": "Central", "Paya Lebar": "Central", "Serangoon": "North-East",
              "Ang Mo Kio": "North-East", "Clarke Quay": "Central", "HarbourFront": "Central",
              "Changi Business Park": "East"}

INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BLUE, ORANGE, GREY, RED = "#2a78d6", "#eb6834", "#d9d8d3", "#d03b3b"
OUT = ROOT / "out"


def severity(r):
    return "high" if r <= 2 else ("medium" if r == 3 else "low")


def fmt_window(a, b):
    return f"{a // 60:02d}:{a % 60:02d}-{b // 60:02d}:{b % 60:02d}"


# ------------------------------------------------------------------ step 1
def validate(t, s, f):
    rows = []
    def add(level, check, n, note=""):
        rows.append({"level": level, "check": check, "count": int(n), "note": note})
    n = t.trip_id.duplicated().sum(); add("FAIL" if n else "ok", "trip_id unique", n)
    n = t.isna().sum().sum(); add("FAIL" if n else "ok", "no blank trip fields", n)
    n = (~t.start_station.isin(s.station) | ~t.end_station.isin(s.station)).sum()
    add("FAIL" if n else "ok", "stations exist in station table", n)
    calc = (t.end_time - t.start_time).dt.total_seconds() / 60
    n = ((calc - t.duration_min).abs() > 1).sum(); add("FAIL" if n else "ok", "duration = end - start", n)
    n = ((t.duration_min < 1) | (t.duration_min > 180)).sum(); add("WARN" if n else "ok", "duration 1-180 min", n)
    ts = t.sort_values(["bike_id", "start_time"])
    ov = ts[ts.groupby("bike_id").start_time.shift(-1) < ts.end_time]
    add("WARN" if len(ov) else "ok", "bike not on two trips at once", len(ov),
        ("examples: " + ", ".join(ov.trip_id.head(3))) if len(ov) else "")
    add("WARN", "round trips (start = end station)", (t.start_station == t.end_station).sum(),
        "valid, but they don't move bikes between stations")
    sd = t[t.start_station != t.end_station].groupby(["start_station", "end_station"]).distance_km.std()
    add("WARN", "distance consistent per station pair", (sd > 0.5).sum(),
        f"median std {sd.median():.2f} km for the same pair: distance is approximate, so not used for routing")
    br = s[s.station.map(URA_REGION) != s.region]
    add("WARN" if len(br) else "ok", "station region matches URA planning region", len(br),
        "; ".join(f"{r.station}: '{r.region}' vs URA '{URA_REGION[r.station]}'" for r in br.itertuples()))
    n = f.feedback_id.duplicated().sum(); add("FAIL" if n else "ok", "feedback_id unique", n)
    n = (~f.rating.between(1, 5)).sum(); add("FAIL" if n else "ok", "rating 1-5", n)
    n = (~f.comment_text.isin(THEMES)).sum()
    add("FAIL" if n else "ok", "every comment has an approved theme", n, "new comment types go to a human first")
    add("WARN", "feedback has no station field", len(f), "complaints can't be tied to a station")
    log = pd.DataFrame(rows); log.to_csv(OUT / "data_quality_log.csv", index=False)
    return log


# ------------------------------------------------------------------ step 2
def complete_weeks(t):
    wk = t.start_time.dt.to_period("W-SUN")
    days = t.groupby(wk).start_time.apply(lambda x: x.dt.normalize().nunique())
    return [p for p, d in days.items() if d == 7]


def detect_peaks(t):
    """Weekday demand per 30-minute slot; slots >= PEAK_RULE x average are peak; adjacent slots merge."""
    wd = t[t.start_time.dt.dayofweek < 5]
    n_days = wd.start_time.dt.normalize().nunique()
    slot = (wd.start_time.dt.hour * 60 + (wd.start_time.dt.minute // 30) * 30)
    prof = (slot.value_counts().sort_index() / n_days).reindex(range(6 * 60, 23 * 60, 30), fill_value=0)
    thr = prof.mean() * PEAK_RULE
    windows, start = [], None
    for m, v in prof.items():
        if v >= thr and start is None:
            start = m
        if v < thr and start is not None:
            windows.append((start, m)); start = None
    if start is not None:
        windows.append((start, prof.index[-1] + 30))
    we = t[t.start_time.dt.dayofweek >= 5]
    we_prof = ((we.start_time.dt.hour * 60 + (we.start_time.dt.minute // 30) * 30).value_counts().sort_index()
               / max(we.start_time.dt.normalize().nunique(), 1)).reindex(prof.index, fill_value=0)
    return prof, we_prof, thr, windows


def peak_consistency(t, weeks):
    """For each complete week: which hour was busiest in the morning and in the evening (weekdays)?"""
    wd = t[(t.start_time.dt.dayofweek < 5) & t.start_time.dt.to_period("W-SUN").isin(weeks)]
    h = wd.start_time.dt.hour; wk = wd.start_time.dt.to_period("W-SUN")
    am = wd[h < 12].groupby([wk[h < 12], h[h < 12]]).size().unstack(fill_value=0).idxmax(axis=1)
    pm = wd[h >= 15].groupby([wk[h >= 15], h[h >= 15]]).size().unstack(fill_value=0).idxmax(axis=1)
    mins = h * 60 + wd.start_time.dt.minute
    in_peaks = sum(mins.between(a, b - 1) for a, b in PEAKS.values()).astype(bool)
    share = in_peaks.groupby(wk).mean()
    df = pd.DataFrame({"busiest_morning_hour": am, "busiest_evening_hour": pm, "share_of_trips_in_peaks": share.round(3)})
    df.index = df.index.map(lambda p: str(p.start_time.date())); df.index.name = "week_starting"
    return df


def peak_flows(t, cap):
    wk_s, wk_e = t.start_time.dt.dayofweek < 5, t.end_time.dt.dayofweek < 5
    n_wd = t.loc[wk_s, "start_time"].dt.normalize().nunique() or 1
    ms = t.start_time.dt.hour * 60 + t.start_time.dt.minute
    me = t.end_time.dt.hour * 60 + t.end_time.dt.minute
    out = {}
    for name, (a, b) in PEAKS.items():
        dep = t[wk_s & ms.between(a, b - 1)].start_station.value_counts() / n_wd
        arr = t[wk_e & me.between(a, b - 1)].end_station.value_counts() / n_wd
        df = pd.DataFrame({"departures": dep, "arrivals": arr}).reindex(cap.index).fillna(0)
        df["net_leaving"] = df.departures - df.arrivals
        out[name] = df.round(2)
    return out


# ------------------------------------------------------------------ step 3
def events(t):
    ev = pd.concat([pd.DataFrame({"station": t.start_station, "ts": t.start_time, "d": -1}),
                    pd.DataFrame({"station": t.end_station, "ts": t.end_time, "d": 1})]).sort_values(["ts", "d"])
    ev["day"] = ev.ts.dt.normalize(); ev["mins"] = ev.ts.dt.hour * 60 + ev.ts.dt.minute
    return ev


def opening_targets(t, cap):
    """Safe opening range per station: enough bikes for a 9-in-10 day's largest loss AND enough free
    docks for a 9-in-10 day's largest gain. Target = middle of the range."""
    ev = events(t)
    run = ev.assign(run=ev.groupby(["station", "day"]).d.cumsum()).groupby(["station", "day"]).run
    loss, gain = (-run.min()).clip(lower=0), run.max().clip(lower=0)
    df = pd.DataFrame({"capacity": cap,
                       "open_min": loss.groupby("station").quantile(TARGET_PCTL).round(),
                       "open_max": cap - gain.groupby("station").quantile(TARGET_PCTL).round()})
    df["target"] = ((df.open_min + df.open_max) / 2).round().astype(int)
    return df


def simulate(t, cap, start, midday=None):
    """Replay every trip in time order. Each day each station starts at `start` (the overnight reset);
    if `midday` is set it is also reset to `start` at that minute. Counts riders who find no bike /
    no free dock, and bikes moved (one move = one pick-up and one drop-off)."""
    ev = events(t)
    no_bike = no_dock = moved = 0
    ends, curve, close = [], [], []
    for (st, day), g in ev.groupby(["station", "day"]):
        c, b, reset = cap[st], int(start[st]), False
        curve.append((st, day, 6 * 60, b))
        for m, d in zip(g.mins, g.d):
            if midday is not None and not reset and m >= midday:
                moved += abs(int(start[st]) - b); b = int(start[st]); reset = True
            if d < 0:
                if b == 0: no_bike += 1
                else: b -= 1
            elif b == c: no_dock += 1
            else: b += 1
            curve.append((st, day, m, b))
        moved += abs(int(start[st]) - b)
        ends.append((st, day, b))
        lo_hi = [x[3] for x in curve if x[0] == st and x[1] == day]
        if min(lo_hi) == 0 or max(lo_hi) == c:
            close.append(st)
    days = ev.day.nunique() or 1
    return ({"riders_no_bike": no_bike, "riders_no_dock": no_dock, "bikes_moved_per_day": round(moved / 2 / days, 1),
             "close_call_station_days": len(close), "close_call_stations": sorted(set(close))},
            pd.DataFrame(ends, columns=["station", "day", "end"]),
            pd.DataFrame(curve, columns=["station", "day", "mins", "bikes"]))


def balanced_round(x):
    """Round average moves to whole bikes so deliveries equal collections (bikes are conserved)."""
    r = x.round()
    gap = int(r.sum())                       # >0: too many deliveries; <0: too many collections
    err = (r - x).sort_values(ascending=(gap < 0))
    for st in err.index[:abs(gap)]:
        r[st] -= 1 if gap > 0 else -1
    return r.astype(int)


def transfers(move):
    """Pair stations with spare bikes to stations that need them, largest first (fewest truck stops).
    Routing by distance needs road data the dataset doesn't have, so the route is left to the ops team."""
    give = (-move[move < 0]).sort_values(ascending=False).to_dict()
    need = move[move > 0].sort_values(ascending=False).to_dict()
    plan = []
    for dst in list(need):
        while need[dst] > 0 and give:
            src = max(give, key=give.get); n = min(give[src], need[dst])
            plan.append({"from": src, "to": dst, "bikes": int(n)})
            give[src] -= n; need[dst] -= n
            if give[src] == 0: del give[src]
    return pd.DataFrame(plan)


def rebalancing(t_week, history, cap):
    """Backtest: targets set from the 4 weeks BEFORE the reporting week, replayed on it, under four rules.
    Plan for next week: targets from the latest 4 complete weeks (incl. this one); nightly moves = what
    this week's trips leave out of place, so the latest week drives the plan."""
    prior = complete_weeks(history)[-TARGET_WEEKS:]
    targets_bt = opening_targets(history[history.start_time.dt.to_period("W-SUN").isin(prior)], cap)
    both = pd.concat([history, t_week])
    recent = complete_weeks(both)[-TARGET_WEEKS:]
    targets_next = opening_targets(both[both.start_time.dt.to_period("W-SUN").isin(recent)], cap)

    tests = {}
    for name, start, mid in [("open full, overnight only", cap, None),
                             ("open half full, overnight only", (cap / 2).round(), None),
                             ("open at target, overnight only", targets_bt.target, None),
                             ("open at target, overnight + 11:00 run", targets_bt.target, MIDDAY_RUN)]:
        tests[name] = simulate(t_week, cap, start, mid)[0]
    a, b = tests["open at target, overnight only"], tests["open at target, overnight + 11:00 run"]
    midday_needed = (b["riders_no_bike"] + b["riders_no_dock"]) < (a["riders_no_bike"] + a["riders_no_dock"])

    _, ends, curve = simulate(t_week, cap, targets_next.target)
    ends["weekday"] = pd.to_datetime(ends.day).dt.dayofweek < 5
    ends["move"] = ends.station.map(targets_next.target) - ends.end      # + deliver, - collect
    plan = targets_next[["capacity", "open_min", "open_max", "target"]].copy()
    plan["weekday_night_move"] = balanced_round(ends[ends.weekday].groupby("station").move.mean().reindex(plan.index).fillna(0))
    plan["weekend_night_move"] = balanced_round(ends[~ends.weekday].groupby("station").move.mean().reindex(plan.index).fillna(0))
    plan = plan.sort_values("weekday_night_move", ascending=False)
    return plan, transfers(plan.weekday_night_move), tests, midday_needed, curve


# ------------------------------------------------------------------ trends
def trends(t_all, f_all, upto):
    t = t_all[t_all.start_time < upto]; f = f_all[f_all.date < upto]
    tw = t[t.start_time.dt.to_period("W-SUN").isin(complete_weeks(t))]
    weekly = pd.crosstab(tw.start_time.dt.to_period("W-SUN"), tw.user_type)
    weekly["total"] = weekly.sum(axis=1)
    weekly.index = weekly.index.map(lambda p: str(p.start_time.date())); weekly.index.name = "week_starting"
    m = t.start_time.dt.to_period("M"); days = t.groupby(m).start_time.apply(lambda x: x.dt.normalize().nunique())
    mem = t.user_type == "Member"
    monthly = pd.DataFrame({"trips_per_day": t.groupby(m).size() / days,
                            "member_per_day": t[mem].groupby(m[mem]).size() / days,
                            "casual_per_day": t[~mem].groupby(m[~mem]).size() / days}).round(1)
    monthly.index = monthly.index.astype(str)
    neg = f[f.comment_text.map(lambda c: THEMES[c][1]) == "negative"]
    comp = pd.crosstab(neg.date.dt.to_period("M").astype(str), neg.category)
    return weekly, monthly, comp


# ------------------------------------------------------------------ main
def main(week_start=None):
    global OUT
    t_all = pd.read_csv(RAW / "CityCycle_trips.csv", parse_dates=["start_time", "end_time"])
    s = pd.read_csv(RAW / "CityCycle_stations.csv")
    f_all = pd.read_csv(RAW / "CityCycle_feedback.csv", parse_dates=["date"])
    cap = s.set_index("station").capacity
    if week_start is None:                                         # default: the latest complete week
        week_start = str(complete_weeks(t_all)[-1].start_time.date())
    ws = pd.Timestamp(week_start); we = ws + pd.Timedelta(days=7)
    OUT = ROOT / "out" / f"week_{week_start}"; OUT.mkdir(parents=True, exist_ok=True)
    t = t_all[(t_all.start_time >= ws) & (t_all.start_time < we)]
    f = f_all[(f_all.date >= ws) & (f_all.date < we)]
    history = t_all[t_all.start_time < ws]
    if t.empty:
        print(f"No trips in the week starting {week_start}"); sys.exit(1)

    control = {"trips_rows": len(t), "stations_rows": len(s), "feedback_rows": len(f),
               "total_ride_minutes": int(t.duration_min.sum()), "total_km": round(float(t.distance_km.sum()), 2)}
    log = validate(t, s, f)
    if (log.level == "FAIL").any():
        print("DATA CONTRACT FAILED - no report produced. See data_quality_log.csv"); sys.exit(1)

    # step 2 - peaks (all data up to the week's end) and this week's flows
    t_upto = t_all[t_all.start_time < we]
    prof, we_prof, thr, windows = detect_peaks(t_upto)
    detected = [fmt_window(a, b) for a, b in windows]
    approved = [fmt_window(a, b) for a, b in PEAKS.values()]
    consistency = peak_consistency(t_upto, complete_weeks(t_upto)); consistency.to_csv(OUT / "peak_consistency.csv")
    flows = peak_flows(t, cap); pd.concat(flows, axis=1).to_csv(OUT / "station_peak_flows.csv")

    # step 3 - rebalancing
    plan, pairs, tests, midday_needed, curve = rebalancing(t, history, cap)
    plan.to_csv(OUT / "rebalancing_plan.csv"); pairs.to_csv(OUT / "rebalancing_transfers.csv", index=False)
    pd.DataFrame(tests).T.rename_axis("rule").to_csv(OUT / "rebalancing_timing_test.csv")

    # step 4 - feedback (week) and themes to date
    def classify(d):
        d = d.assign(theme=d.comment_text.map(lambda c: THEMES[c][0]),
                     sentiment=d.comment_text.map(lambda c: THEMES[c][1]), severity=d.rating.map(severity))
        d["safety"] = d.theme.isin(SAFETY_THEMES)
        d["needs_review"] = ((d.sentiment == "negative") & (d.rating >= 4)) | ((d.sentiment == "positive") & (d.rating <= 2))
        return d
    f = classify(f); f_upto = classify(f_all[f_all.date < we])
    f.to_csv(OUT / "feedback_classified.csv", index=False)
    f[f.needs_review].to_csv(OUT / "needs_review.csv", index=False)
    f[f.safety].to_csv(OUT / "safety_escalations.csv", index=False)
    neg, neg_q = f[f.sentiment == "negative"], f_upto[f_upto.sentiment == "negative"]
    themes_q = (neg_q.groupby("theme").agg(n=("feedback_id", "size"), avg_rating=("rating", "mean"),
                                           high_severity=("severity", lambda x: int((x == "high").sum())))
                .sort_values("n", ascending=False).round(2))
    themes_q.to_csv(OUT / "feedback_themes_to_date.csv")

    weekly, monthly, comp = trends(t_all, f_all, we)
    weekly.to_csv(OUT / "trend_weekly_trips.csv"); monthly.to_csv(OUT / "trend_monthly.csv")
    comp.to_csv(OUT / "trend_complaints_by_month.csv")
    tot = weekly.total

    # step 5 - facts
    morning = flows[list(PEAKS)[0]].net_leaving
    evening = flows[list(PEAKS)[2]].net_leaving
    facts = {
        "week": {"from": str(ws.date()), "to": str((we - pd.Timedelta(days=1)).date())},
        "control_totals": control,
        "data_quality_warnings": log[log.level == "WARN"][["check", "count"]].to_dict("records"),
        "trips": {"total": len(t), "per_day": round(len(t) / 7, 1),
                  "member_share_pct": round((t.user_type == "Member").mean() * 100, 1),
                  "avg_minutes_member": round(t[t.user_type == "Member"].duration_min.mean(), 1),
                  "avg_minutes_casual": round(t[t.user_type == "Casual"].duration_min.mean(), 1),
                  "prior_4wk_avg": round(float(tot.iloc[-5:-1].mean()), 1),
                  "vs_prior_4wk_avg_pct": round(float(tot.iloc[-1] / tot.iloc[-5:-1].mean() * 100 - 100), 1),
                  "complete_week_range": [int(tot.min()), int(tot.max())]},
        "busiest_start_stations": t.start_station.value_counts().head(5).to_dict(),
        "peaks": {"approved": approved, "detected_this_run": detected, "match": detected == approved,
                  "rule_threshold_trips_per_slot": round(float(thr), 2),
                  "weeks_checked": len(consistency),
                  "weeks_busiest_morning_hour_08": int((consistency.busiest_morning_hour == 8).sum()),
                  "weeks_busiest_evening_hour_18": int((consistency.busiest_evening_hour == 18).sum()),
                  "share_of_weekday_trips_in_peaks_pct": round(float(consistency.share_of_trips_in_peaks.mean() * 100), 1),
                  "weekend_busiest_slot": fmt_window(int(we_prof.idxmax()), int(we_prof.idxmax()) + 30)},
        "morning_peak_losing_bikes": morning[morning > 0.5].sort_values(ascending=False).to_dict(),
        "evening_peak_net_range": [round(float(evening.min()), 1), round(float(evening.max()), 1)],
        "rebalancing": {
            "timing_test_this_week": tests,
            "recommended_timing": "overnight + midday" if midday_needed else "overnight (end of day)",
            "midday_run_needed": bool(midday_needed),
            "weekday_deliver": plan[plan.weekday_night_move > 0].weekday_night_move.to_dict(),
            "weekday_collect": (-plan[plan.weekday_night_move < 0].weekday_night_move).to_dict(),
            "weekday_bikes_to_move_per_night": int(plan.weekday_night_move.clip(lower=0).sum()),
            "weekend_bikes_to_move_per_night": int(plan.weekend_night_move.clip(lower=0).sum()),
            "targets_next_week": plan.target.to_dict(),
            "all_targets_feasible": bool(plan.open_min.le(plan.open_max).all()),
            "transfers": pairs.to_dict("records"),
            "watch_list": tests["open at target, overnight only"]["close_call_stations"],
            "watch_rule": "a station that hits empty or full on 2+ days in a week gets a higher/lower target; midday run only if riders are turned away",
        },
        "feedback_week": {"total": len(f), "negative": len(neg), "positive": int((f.sentiment == "positive").sum()),
                          "avg_rating": round(float(f.rating.mean()), 2) if len(f) else None,
                          "top_issues": neg.theme.value_counts().head(5).to_dict(),
                          "safety_escalations": int(f.safety.sum()),
                          "rating_text_disagree": int(f.needs_review.sum())},
        "feedback_to_date": {"total": len(f_upto), "negative": len(neg_q), "positive": int((f_upto.sentiment == "positive").sum()),
                             "safety_mentions": int(neg_q.safety.sum()),
                             "brakes": int((neg_q.theme == "Brakes loose").sum()),
                             "gears": int((neg_q.theme == "Gears slipping").sum()),
                             "rating_text_disagree": int(f_upto.needs_review.sum()),
                             "top_issues": themes_q.head(5).reset_index()[["theme", "n", "avg_rating"]].to_dict("records")},
        "trend": {"monthly": monthly.to_dict("index"), "complaints_by_month": comp.to_dict("index")},
    }
    (OUT / "facts.json").write_text(json.dumps(facts, indent=2, default=str))
    charts(prof, we_prof, thr, flows, plan, curve, themes_q, weekly)
    print(json.dumps(facts, indent=2, default=str))


# ------------------------------------------------------------------ charts
def style(ax):
    ax.set_facecolor(SURF)
    for sp in ["top", "right", "left"]:
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(GRID); ax.tick_params(colors=INK2, labelsize=9, length=0); ax.set_axisbelow(True)


def charts(prof, we_prof, thr, flows, plan, curve, themes_q, weekly):
    plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": SURF})

    # 1 - peak hours
    fig, ax = plt.subplots(figsize=(8.5, 4)); style(ax)
    x = prof.index / 60
    ax.plot(x, prof.values, color=BLUE, lw=2, marker="o", ms=3, label="Weekday")
    ax.plot(x, we_prof.values, color=ORANGE, lw=1.5, ls="--", label="Weekend")
    for a, b in PEAKS.values():
        ax.axvspan(a / 60, b / 60, color=GREY, alpha=0.45, lw=0)
    ax.axhline(thr, color=INK2, lw=0.8, ls=":")
    ax.text(22.9, thr + 0.12, f"peak rule: {PEAK_RULE}x average", ha="right", fontsize=8, color=INK2)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_xticks(range(6, 24, 2)); ax.set_xticklabels([f"{h:02d}:00" for h in range(6, 24, 2)])
    ax.set_ylabel("Trips started per 30 min (avg day)", color=INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.set_title("Weekday peaks: 08:00-10:00, 12:00-13:00 and 17:00-20:00", loc="left", color=INK, fontsize=12, fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "chart1_peak_hours.png", dpi=200); plt.close(fig)

    # 2 - station flows in each peak this week
    names = list(PEAKS); order = flows[names[0]].net_leaving.sort_values().index
    fig, axes = plt.subplots(1, 3, figsize=(10, 6), sharey=True, sharex=True)
    for ax, n in zip(axes, names):
        style(ax); d = flows[n].net_leaving.reindex(order)
        ax.barh(d.index, d.values, color=[ORANGE if v > 0 else BLUE for v in d.values], height=0.7)
        ax.axvline(0, color=INK2, lw=1); ax.xaxis.grid(True, color=GRID, lw=0.8)
        ax.set_title(n, loc="left", fontsize=9.5, color=INK)
        for y, v in enumerate(d.values):
            if abs(v) >= 1:
                ax.text(v + (0.08 if v > 0 else -0.08), y, f"{v:+.1f}", va="center", ha="left" if v > 0 else "right", fontsize=7, color=INK2)
    fig.supxlabel("Net bikes leaving per weekday (departures minus arrivals)", color=INK2, fontsize=9)
    fig.suptitle("This week: business-district stations empty in the morning and don't refill later",
                 x=0.02, ha="left", color=INK, fontsize=11.5, fontweight="bold")
    fig.text(0.02, 0.905, "Orange = station loses bikes   Blue = station gains bikes", ha="left", fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.9)); fig.savefig(OUT / "chart2_peak_flows.png", dpi=200); plt.close(fig)

    # 3 - nightly rebalancing plan (weekday)
    p = plan.weekday_night_move.sort_values()
    fig, ax = plt.subplots(figsize=(8.5, 6)); style(ax)
    ax.barh(p.index, p.values, color=[BLUE if v > 0 else ORANGE for v in p.values], height=0.7)
    ax.axvline(0, color=INK2, lw=1); ax.xaxis.grid(True, color=GRID, lw=0.8)
    for y, (st, v) in enumerate(p.items()):
        if v:
            ax.text(v + (0.15 if v > 0 else -0.15), y, f"{'deliver' if v > 0 else 'collect'} {abs(v)} (target {plan.target[st]})",
                    va="center", ha="left" if v > 0 else "right", fontsize=7.5, color=INK2)
    ax.set_xlim(p.min() - 5, p.max() + 6)
    ax.set_xlabel("Bikes to move each weekday night to bring every station back to its opening target", color=INK2, fontsize=9)
    ax.set_title(f"Overnight plan: {int(p.clip(lower=0).sum())} bikes from residential to business-district stations",
                 loc="left", color=INK, fontsize=11.5, fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "chart3_rebalancing_plan.png", dpi=200); plt.close(fig)

    # 4 - bikes on hand through an average weekday at the four stations needing most deliveries
    wd = curve[pd.to_datetime(curve.day).dt.dayofweek < 5].copy()
    wd["slot"] = (wd.mins // 30) * 30
    slots = list(range(6 * 60, 23 * 60, 30))
    tight = plan.index[:4]
    fig, ax = plt.subplots(figsize=(8.5, 4.8)); style(ax)
    for st, c in zip(tight, [BLUE, ORANGE, "#1baf7a", "#6250d6"]):
        per = (wd[wd.station == st].groupby(["day", "slot"]).bikes.min().unstack()
               .reindex(columns=slots).ffill(axis=1).bfill(axis=1))
        ax.plot([s_ / 60 for s_ in slots], per.mean().values, color=c, lw=2,
                label=f"{st} (target {plan.target[st]}, {plan.capacity[st]} docks)")
        ax.fill_between([s_ / 60 for s_ in slots], per.min().values, per.mean().values, color=c, alpha=0.12, lw=0)
    for a, b in PEAKS.values():
        ax.axvspan(a / 60, b / 60, color=GREY, alpha=0.35, lw=0)
    ax.axhline(0, color=RED, lw=1); ax.text(6.1, 0.3, "empty", color=RED, fontsize=8)
    ax.axvline(MIDDAY_RUN / 60, color=INK2, lw=0.8, ls="--")
    ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_ylim(-1, None)
    ax.text(MIDDAY_RUN / 60 + 0.1, ax.get_ylim()[1] * 0.93, "possible midday run", fontsize=8, color=INK2)
    ax.set_xticks(range(6, 24, 2)); ax.set_xticklabels([f"{h:02d}:00" for h in range(6, 24, 2)])
    ax.set_ylabel("Bikes on hand (line = avg, shade = lowest day)", color=INK2, fontsize=8.5)
    ax.legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    ax.set_title("Opened at target, no rider is turned away; Raffles Place runs close to empty",
                 loc="left", color=INK, fontsize=11, fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "chart4_stock_through_day.png", dpi=200); plt.close(fig)

    # 5 - complaints to date, safety highlighted
    th = themes_q.sort_values("n")
    fig, ax = plt.subplots(figsize=(8, 5)); style(ax)
    ax.barh(th.index, th.n, color=[RED if i in SAFETY_THEMES else BLUE for i in th.index], height=0.7)
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    for y, (name, n, r) in enumerate(zip(th.index, th.n, th.avg_rating)):
        safe = name in SAFETY_THEMES
        ax.text(n + 0.4, y, f"{n}  (avg {r:.1f} stars){'  SAFETY' if safe else ''}", va="center", fontsize=8,
                color=RED if safe else INK2, fontweight="bold" if safe else "normal")
    ax.set_xlabel("Negative comments to date (sentiment read from the text)", color=INK2, fontsize=9)
    ax.set_title("Complaint themes: brakes and gears go straight to maintenance", loc="left", color=INK, fontsize=12, fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "chart5_complaints_safety.png", dpi=200); plt.close(fig)

    # 6 - weekly usage trend (complete weeks)
    fig, ax = plt.subplots(figsize=(8, 3.8)); style(ax)
    xs = [d[5:] for d in weekly.index]
    for col, c in [("Member", BLUE), ("Casual", ORANGE)]:
        ax.plot(xs, weekly[col], color=c, lw=2, marker="o", ms=4, label=col)
    for i, d in enumerate(weekly.index):
        if d in HOLIDAYS:
            ax.annotate(HOLIDAYS[d], (i, weekly.Member.iloc[i]), xytext=(0, -26), textcoords="offset points", ha="center",
                        fontsize=8, color=INK2, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_ylim(0, None)
    ax.set_ylabel("Trips per week", color=INK2, fontsize=9)
    ax.set_xlabel("Week starting (month-day), complete weeks only", color=INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.set_title("Usage is steady week to week, with casual riding edging up", loc="left", color=INK, fontsize=12, fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "chart6_weekly_trend.png", dpi=200); plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--week-start")
    main(ap.parse_args().week_start)
