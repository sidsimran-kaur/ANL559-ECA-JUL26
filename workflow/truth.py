"""Independent source of truth for report numbers.

Recomputes every figure the write-up and weekly report quote, directly from the raw CSVs, using the
plain csv module and none of the pipeline's code (no pandas, no import of weekly_report.py). Two
independent implementations agreeing is the evidence; if they disagree, one of them is wrong.

    python workflow/truth.py 2026-03-23        # prints every value
"""
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

NEGATIVE = {"the app keeps crashing when I unlock", "payment failed in the app twice", "app GPS shows wrong station",
            "no bikes available at my station in the morning", "hard to find a bike at peak hour",
            "docks were all full, couldn't return", "brakes felt loose", "tyre was flat", "seat was wobbly",
            "gears slipping", "charged twice for one ride", "unexpected late fee"}
MORNING = "no bikes available at my station in the morning"
GPS = "app GPS shows wrong station"
BRAKES, GEARS = "brakes felt loose", "gears slipping"
TRUE_REGION = {"Raffles Place": "Central", "Tanjong Pagar": "Central", "Marina Bay": "Central", "Bugis": "Central",
               "Orchard": "Central", "Somerset": "Central", "Tampines Hub": "East", "Jurong East": "West",
               "Bishan": "Central", "Woodlands": "North", "Pasir Ris": "East", "Sentosa": "Central",
               "one-north": "Central", "Buona Vista": "Central", "Paya Lebar": "Central", "Serangoon": "North-East",
               "Ang Mo Kio": "North-East", "Clarke Quay": "Central", "HarbourFront": "Central",
               "Changi Business Park": "East"}
PEAKS = [(8 * 60, 10 * 60), (12 * 60, 13 * 60), (17 * 60, 20 * 60)]


THEME_OF = {"the app keeps crashing when I unlock": "App crash on unlock", "payment failed in the app twice": "App payment failure",
            "app GPS shows wrong station": "App GPS wrong station", "no bikes available at my station in the morning": "No bikes (morning)",
            "hard to find a bike at peak hour": "No bikes (peak hour)", "docks were all full, couldn't return": "Docks full, can't return",
            "brakes felt loose": "Brakes loose", "tyre was flat": "Flat tyre", "seat was wobbly": "Wobbly seat",
            "gears slipping": "Gears slipping", "charged twice for one ride": "Double charge", "unexpected late fee": "Unexpected late fee"}


def mann_whitney_p(a, b):
    """Two-sided Mann-Whitney U, normal approximation with tie and continuity correction (written from the formula)."""
    import math
    allv = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, i = {}, 0
    vals = [v for v, _ in allv]
    rank_of = {}
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        rank_of[vals[i]] = (i + j) / 2 + 1
        i = j + 1
    n1, n2, N = len(a), len(b), len(a) + len(b)
    u1 = sum(rank_of[v] for v in a) - n1 * (n1 + 1) / 2
    ties = sum(c ** 3 - c for c in Counter(vals).values())
    sigma = math.sqrt(n1 * n2 / 12 * ((N + 1) - ties / (N * (N - 1))))
    z = (abs(u1 - n1 * n2 / 2) - 0.5) / sigma
    return math.erfc(z / math.sqrt(2))


def load():
    trips = list(csv.DictReader(open(ROOT / "data/raw/CityCycle_trips.csv", encoding="utf-8")))
    for r in trips:
        r["st"], r["et"] = P(r["start_time"]), P(r["end_time"])
    stations = list(csv.DictReader(open(ROOT / "data/raw/CityCycle_stations.csv", encoding="utf-8")))
    fb = list(csv.DictReader(open(ROOT / "data/raw/CityCycle_feedback.csv", encoding="utf-8")))
    for r in fb:
        r["d"] = datetime.fromisoformat(r["date"]); r["rating"] = int(r["rating"])
    return trips, stations, fb


def monday(d):
    return (d - timedelta(days=d.weekday())).date()


def complete_weeks(trips):
    days = defaultdict(set)
    for r in trips:
        days[monday(r["st"])].add(r["st"].date())
    return sorted(w for w, d in days.items() if len(d) == 7)


def disagree(r):
    neg = r["comment_text"] in NEGATIVE
    return (neg and r["rating"] >= 4) or ((not neg) and r["rating"] <= 2)


def quantile(xs, q):                      # linear interpolation, same definition as the spec in work_order.md
    xs = sorted(xs); pos = (len(xs) - 1) * q; lo = int(pos); hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def station_days(trips):
    """station -> day -> list of (minute, +1/-1) in time order; departures before arrivals at the same minute."""
    ev = defaultdict(lambda: defaultdict(list))
    for r in trips:
        ev[r["start_station"]][r["st"].date()].append((r["st"], -1))
        ev[r["end_station"]][r["et"].date()].append((r["et"], 1))
    for st in ev:
        for d in ev[st]:
            ev[st][d].sort()
    return ev


def targets(trips, cap):
    ev = station_days(trips); out = {}
    for st, c in cap.items():
        loss, gain = [], []
        for d, es in ev[st].items():
            run = lo = hi = 0
            for _, x in es:
                run += x; lo = min(lo, run); hi = max(hi, run)
            loss.append(-lo); gain.append(hi)
        mn = round(quantile(loss, 0.9)); mx = c - round(quantile(gain, 0.9))
        out[st] = round((mn + mx) / 2)
    return out


def replay(trips, cap, start, midday=None, close=None):
    ev = station_days(trips); turned = moved = 0; days = set(); ends = defaultdict(list)
    for st in cap:
        for d, es in ev[st].items():
            days.add(d); b = start[st]; reset = False; lo, hi = b, b
            for t, x in es:
                if midday is not None and not reset and t.hour * 60 + t.minute >= midday:
                    moved += abs(start[st] - b); b = start[st]; reset = True
                if x < 0:
                    if b == 0: turned += 1
                    else: b -= 1
                elif b == cap[st]: turned += 1
                else: b += 1
                lo, hi = min(lo, b), max(hi, b)
            if close is not None and (lo == 0 or hi == cap[st]):
                close[st] += 1
            moved += abs(start[st] - b); ends[st].append((d, b))
    return turned, round(moved / 2 / len(days), 1), ends


def compute(week):
    trips, stations, fb = load()
    cap = {s["station"]: int(s["capacity"]) for s in stations}
    ws = datetime.fromisoformat(week); we = ws + timedelta(days=7)
    wk = [r for r in trips if ws <= r["st"] < we]
    wfb = [r for r in fb if ws <= r["d"] < we]
    T = {}

    # ---- whole file (quarter)
    T["data.trips"] = len(trips); T["data.stations"] = len(stations); T["data.comments"] = len(fb)
    neg = [r for r in fb if r["comment_text"] in NEGATIVE]
    T["data.negative"] = len(neg); T["data.positive"] = len(fb) - len(neg)
    c = Counter(r["comment_text"] for r in neg)
    T["data.morning_shortage"] = c[MORNING]; T["data.gps"] = c[GPS]
    T["data.brakes"] = c[BRAKES]; T["data.gears"] = c[GEARS]; T["data.safety"] = c[BRAKES] + c[GEARS]
    T["data.rating_text_disagree"] = sum(disagree(r) for r in fb)
    # privacy and bias evidence for 1d
    key_min = Counter((r["start_station"], r["start_time"][:16]) for r in trips)
    T["data.unique_start_minute_pct"] = round(sum(1 for r in trips if key_min[(r["start_station"], r["start_time"][:16])] == 1) / len(trips) * 100, 1)
    pat_days = defaultdict(set)
    for r in trips:
        pat_days[(r["start_station"], r["end_station"], r["st"].hour * 60 + (r["st"].minute // 30) * 30, r["user_type"])].add(r["st"].date())
    T["data.recurring_patterns_5plus_days"] = sum(len(v) >= 5 for v in pat_days.values())
    T["data.feedback_per_trip_pct"] = round(len(fb) / len(trips) * 100, 1)
    T["data.casual_share_feedback_pct"] = round(sum(r["user_type"] == "Casual" for r in fb) / len(fb) * 100)
    T["data.casual_share_trips_pct"] = round(sum(r["user_type"] == "Casual" for r in trips) / len(trips) * 100)
    T["data.avg_rating"] = round(statistics.mean(r["rating"] for r in fb), 2)
    watch, hidden = [], []
    for text, theme in THEME_OF.items():
        mine = [r["rating"] for r in fb if r["comment_text"] == text]
        rest = [r["rating"] for r in fb if r["comment_text"] != text]
        key = "impact." + theme
        T[key + ".n"] = len(mine)
        T[key + ".avg"] = round(statistics.mean(mine), 2)
        T[key + ".diff"] = round(statistics.mean(mine) - statistics.mean(rest), 2)
        T[key + ".p"] = round(mann_whitney_p(mine, rest), 4)
        T[key + ".pct_1_2"] = round(sum(x <= 2 for x in mine) / len(mine) * 100)
        if T[key + ".p"] < 0.01:
            (watch if T[key + ".diff"] < 0 else hidden).append(theme)
    T["data.rating_watch_list"] = sorted(watch); T["data.rating_hidden_list"] = sorted(hidden)
    T["data.rating_watch_count"] = len(watch)
    T["data.watch_app_or_billing"] = sum(t in ("App crash on unlock", "App payment failure", "Double charge", "Unexpected late fee") for t in watch)
    T["data.hidden_complaints_total"] = sum(T["impact." + t + ".n"] for t in hidden)
    for text, theme in THEME_OF.items():
        mine = [r["rating"] for r in fb if r["comment_text"] == text]
        rest = [r["rating"] for r in fb if r["comment_text"] != text]
        T["impact." + theme + ".lift"] = round((statistics.mean(rest) - statistics.mean(mine)) * len(mine) / len(fb), 3)
    by_bike = defaultdict(list)
    for r in trips:
        by_bike[r["bike_id"]].append(r)
    pairs = []
    for rs in by_bike.values():
        rs.sort(key=lambda r: r["st"])
        pairs += [(a, b) for a, b in zip(rs, rs[1:]) if b["st"] < a["et"]]
    T["data.overlap_pairs"] = len(pairs)
    T["data.overlap_pairs_different_start"] = sum(a["start_station"] != b["start_station"] for a, b in pairs)
    T["data.region_mismatch"] = sum(TRUE_REGION[s["station"]] != s["region"] for s in stations)
    pair_km = defaultdict(list)
    for r in trips:
        if r["start_station"] != r["end_station"]:
            pair_km[(r["start_station"], r["end_station"])].append(float(r["distance_km"]))
    T["data.distance_std_km"] = round(statistics.median(statistics.stdev(v) for v in pair_km.values() if len(v) > 1), 1)
    month = defaultdict(int); mdays = defaultdict(set)
    for r in trips:
        month[r["st"].month] += 1; mdays[r["st"].month].add(r["st"].date())
    T["data.jan_trips_per_day"] = round(month[1] / len(mdays[1]), 1)
    T["data.mar_trips_per_day"] = round(month[3] / len(mdays[3]), 1)
    # peaks: weekday 30-min slots >= 1.5 x average
    wd = [r for r in trips if r["st"].weekday() < 5]
    nd = len({r["st"].date() for r in wd})
    slots = Counter(r["st"].hour * 60 + (r["st"].minute // 30) * 30 for r in wd)
    grid = list(range(6 * 60, 23 * 60, 30)); avg = sum(slots[g] for g in grid) / nd / len(grid)
    peak = [g for g in grid if slots[g] / nd >= 1.5 * avg]
    wins, s0 = [], None
    for g in grid + [None]:
        if g in peak and s0 is None: s0 = g
        if (g not in peak) and s0 is not None:
            wins.append(f"{s0 // 60:02d}:{s0 % 60:02d}–{prev // 60 + (prev % 60 + 30) // 60:02d}:{(prev % 60 + 30) % 60:02d}"); s0 = None
        prev = g
    T["data.peak_windows"] = wins
    cw = complete_weeks(trips); T["data.complete_weeks"] = len(cw)
    am = pm = 0; shares = []
    for w in cw:
        rs = [r for r in wd if monday(r["st"]) == w]
        h_am = Counter(r["st"].hour for r in rs if r["st"].hour < 12).most_common(1)[0][0]
        h_pm = Counter(r["st"].hour for r in rs if r["st"].hour >= 15).most_common(1)[0][0]
        am += h_am == 8; pm += h_pm == 18
        shares.append(sum(any(a <= r["st"].hour * 60 + r["st"].minute < b for a, b in PEAKS) for r in rs) / len(rs))
    T["data.weeks_busiest_08"] = am; T["data.weeks_busiest_18"] = pm
    T["data.busiest_morning_hour"] = f"{Counter(r['st'].hour for r in wd if r['st'].hour < 12).most_common(1)[0][0]:02d}:00"
    T["data.busiest_evening_hour"] = f"{Counter(r['st'].hour for r in wd if r['st'].hour >= 15).most_common(1)[0][0]:02d}:00"
    T["data.share_in_peaks_pct"] = round(sum(shares) / len(shares) * 100, 1)

    # ---- reporting week
    T["week.trips"] = len(wk); T["week.trips_per_day"] = round(len(wk) / 7, 1)
    T["week.comments"] = len(wfb)
    T["week.negative"] = sum(r["comment_text"] in NEGATIVE for r in wfb)
    T["week.rating_text_disagree"] = sum(disagree(r) for r in wfb)
    T["week.safety"] = sum(r["comment_text"] in (BRAKES, GEARS) for r in wfb)
    T["to_week_end.negative"] = sum(r["comment_text"] in NEGATIVE for r in fb if r["d"] < we)
    T["to_week_end.safety"] = sum(r["comment_text"] in (BRAKES, GEARS) for r in fb if r["d"] < we)
    wdays = {r["st"].date() for r in wk if r["st"].weekday() < 5}
    def morning(st):
        dep = sum(1 for r in wk if r["start_station"] == st and r["st"].weekday() < 5 and 8 <= r["st"].hour < 10)
        arr = sum(1 for r in wk if r["end_station"] == st and r["et"].weekday() < 5 and 8 <= r["et"].hour < 10)
        return round((dep - arr) / len(wdays), 1)
    T["week.morning_loss_tanjong_pagar"] = morning("Tanjong Pagar"); T["week.morning_loss_raffles_place"] = morning("Raffles Place")
    T["week.round_trips"] = sum(r["start_station"] == r["end_station"] for r in wk)
    T["week.warnings"] = (1 if T["week.round_trips"] else 0) + 1 + (1 if T["data.region_mismatch"] else 0) + (1 if wfb else 0) \
        + (1 if any(b["st"] < a["et"] for rs in [[r for r in wk if r["bike_id"] == bid] for bid in {r["bike_id"] for r in wk}]
                    for a, b in zip(sorted(rs, key=lambda r: r["st"]), sorted(rs, key=lambda r: r["st"])[1:])) else 0)
    weekly = Counter(monday(r["st"]) for r in trips if monday(r["st"]) in cw and monday(r["st"]) <= ws.date())
    tot = [weekly[w] for w in cw if w <= ws.date()]
    T["week.vs_prior_4wk_pct"] = round(tot[-1] / (sum(tot[-5:-1]) / 4) * 100 - 100, 1)
    T["week.range_min"] = min(tot); T["week.range_max"] = max(tot)

    # ---- rebalancing (independent replay)
    prior_weeks = [w for w in cw if w < ws.date()][-4:]
    tg_bt = targets([r for r in trips if monday(r["st"]) in prior_weeks], cap)
    close = Counter()
    T["reb.overnight_turned_away"], T["reb.overnight_bikes_per_day"], _ = replay(wk, cap, tg_bt, close=close)
    T["reb.raffles_close_call_days"] = close["Raffles Place"]
    T["reb.close_call_station_days"] = sum(close.values())
    T["reb.midday_turned_away"], T["reb.midday_bikes_per_day"], _ = replay(wk, cap, tg_bt, 11 * 60)
    T["reb.full_turned_away"] = replay(wk, cap, cap)[0]
    recent = [w for w in cw if w <= ws.date()][-4:]
    tg_next = targets([r for r in trips if monday(r["st"]) in recent], cap)
    _, _, ends = replay(wk, cap, tg_next)
    mean_move = {st: statistics.mean(tg_next[st] - b for d, b in ends[st] if d.weekday() < 5) for st in cap}
    rnd = {st: round(v) for st, v in mean_move.items()}
    gap = sum(rnd.values())
    err = {st: round(rnd[st] - mean_move[st], 6) for st in cap}
    if gap > 0:
        order = sorted(cap, key=lambda st: (-err[st], 0 if mean_move[st] <= 0 else 1, st))
    else:
        order = sorted(cap, key=lambda st: (err[st], 0 if mean_move[st] >= 0 else 1, st))
    for st in order[:abs(gap)]:
        rnd[st] += -1 if gap > 0 else 1
    T["reb.weekday_bikes_per_night"] = sum(v for v in rnd.values() if v > 0)
    T["reb.weekday_collected"] = -sum(v for v in rnd.values() if v < 0)
    bt_ok = 0
    for i, w in enumerate(cw):
        if i < 4: continue
        tg = targets([r for r in trips if monday(r["st"]) in cw[i - 4:i]], cap)
        bt_ok += replay([r for r in trips if monday(r["st"]) == w], cap, tg)[0] == 0
    T["reb.backtest_weeks_zero_turned_away"] = bt_ok
    T["reb.backtest_weeks"] = len(cw) - 4

    # ---- baseline ladder over the same unseen weeks (independent implementation)
    half = {st: round(c / 2) for st, c in cap.items()}
    full_n = half_n = single_n = 0
    for i, w_ in enumerate(cw):
        if i < 4: continue
        prior = [r for r in trips if monday(r["st"]) in cw[i - 4:i]]
        this = [r for r in trips if monday(r["st"]) == w_]
        full_n += replay(this, cap, dict(cap))[0]
        half_n += replay(this, cap, half)[0]
        ev = station_days(prior); avg = {}
        for st in cap:
            losses = []
            for d, es in ev[st].items():
                run = lo = 0
                for _, x in es:
                    run += x; lo = min(lo, run)
                losses.append(-lo)
            avg[st] = round(statistics.mean(losses)) if losses else 0
        single_n += replay(this, cap, avg)[0]
    span = [r for r in trips if monday(r["st"]) in cw[4:]]
    evs = sorted([(r["st"], -1, r["start_station"]) for r in span] + [(r["et"], 1, r["end_station"]) for r in span])
    stock = dict(half); nothing = 0
    for _, x, st in evs:
        if x < 0:
            if stock[st] == 0: nothing += 1
            else: stock[st] -= 1
        elif stock[st] == cap[st]: nothing += 1
        else: stock[st] += 1
    T["bl.do_nothing"], T["bl.open_full"], T["bl.open_half"], T["bl.single_signal"] = nothing, full_n, half_n, single_n
    tgt_n, tgt_moves, mid_moves = 0, [], []
    for i, w_ in enumerate(cw):
        if i < 4: continue
        tg = targets([r for r in trips if monday(r["st"]) in cw[i - 4:i]], cap)
        this = [r for r in trips if monday(r["st"]) == w_]
        n, mv, _ = replay(this, cap, tg); tgt_n += n; tgt_moves.append(mv)
        mid_moves.append(replay(this, cap, tg, 11 * 60)[1])
    T["bl.targets_turned_away"] = tgt_n
    T["bl.bikes_targets"] = round(statistics.mean(tgt_moves), 1); T["bl.bikes_midday"] = round(statistics.mean(mid_moves), 1)

    T["reb.midday_extra_moves"] = round(T["reb.midday_bikes_per_day"] - T["reb.overnight_bikes_per_day"])

    # ---- efficiency estimate: recomputed from the stated assumptions (not from efficiency_model.py)
    A = json.loads((ROOT / "workflow" / "efficiency_assumptions.json").read_text())
    man, aut = A["manual"], A["automated"]
    m_tot, a_tot = sum(man.values()), sum(aut.values())
    T["eff.manual_minutes"] = m_tot; T["eff.manual_hours"] = round(m_tot / 60, 1)
    T["eff.automated_minutes"] = a_tot
    T["eff.saved_hours"] = round((m_tot - a_tot) / 60, 1); T["eff.saved_pct"] = round((m_tot - a_tot) / m_tot * 100)
    T["eff.weeks"] = A["working_weeks_per_year"]; T["eff.rate"] = A["analyst_cost_per_hour_sgd"]
    T["eff.saved_hours_year"] = round((m_tot - a_tot) / 60 * A["working_weeks_per_year"])
    T["eff.saved_value_year"] = round((m_tot - a_tot) / 60 * A["working_weeks_per_year"] * A["analyst_cost_per_hour_sgd"], -2)
    T["eff.sens_low_hours"] = A["sensitivity_manual_hours"][0]
    T["eff.sens_low_saved"] = round(A["sensitivity_manual_hours"][0] - a_tot / 60, 1)
    mv, av = list(man.values()), list(aut.values())
    T["eff.m.prepare"], T["eff.m.analyse"], T["eff.m.charts"], T["eff.m.write"], T["eff.m.rebalance"] = mv[0], mv[1] + mv[2], mv[3], mv[4], mv[5]
    T["eff.a.prepare"], T["eff.a.write"], T["eff.a.rebalance"], T["eff.a.signoff"] = av[1], av[2], av[3], av[0] + av[4] + av[5]
    T["zero"] = 0

    # ---- process evidence (read from the check outputs)
    wkdir = ROOT / "out" / f"week_{week}"
    v = (wkdir / "verify_result.txt").read_text()
    import re
    T["proc.numbers_traced"] = int(re.search(r"(\d+)/\d+ numbers traced", v).group(1))
    T["proc.planted_value"] = int((wkdir / "planted_error_test.txt").read_text().split("UNTRACED:")[1].split()[0])
    T["proc.planted_true"] = Counter(r["start_station"] for r in wk)["Changi Business Park"]
    ic = (wkdir / "independent_check.txt").read_text().splitlines()[1:]
    T["proc.independent_checks"] = sum(1 for l in ic if l.strip())
    T["proc.independent_matched"] = sum(1 for l in ic if l.rstrip().endswith("MATCH"))
    return T


if __name__ == "__main__":
    print(json.dumps(compute(sys.argv[1] if len(sys.argv) > 1 else "2026-03-23"), indent=1, default=str))
