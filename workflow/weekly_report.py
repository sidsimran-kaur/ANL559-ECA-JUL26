"""CityCycle weekly operations report: the deterministic core of the automation.

    python workflow/weekly_report.py                         # whole quarter
    python workflow/weekly_report.py --week-start 2026-03-23 # one reporting week

Step 1 VALIDATE  data contract on the inputs; a FAIL stops the run
Step 2 COMPUTE   station flows (two peaks), opening stock needed, demand, feedback
Step 3 CLASSIFY  apply the approved taxonomy (sentiment from text, severity from stars)
Step 4 FACTS     write out/facts.json, the ONLY numbers the language model may quote
Step 5 CHARTS    four PNGs for the report
The report text is drafted by the LLM from facts.json and then checked by verify_report.py.
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
RAW, OUT = ROOT / "data" / "raw", ROOT / "out"
OUT.mkdir(exist_ok=True)

# ---- approved definitions (work_order.md); changing one needs a new sign-off ----
PEAKS = {"Morning peak (07:00-09:00)": (7 * 60, 9 * 60), "Evening peak (17:30-19:30)": (17 * 60 + 30, 19 * 60 + 30)}
OPENING_STOCK_PCTL = 0.90
SAFETY_THEMES = {"Brakes loose"}

# Feedback taxonomy v1: drafted by the LLM, reviewed and approved by the analyst.
# comment text -> (theme, sentiment)
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
# URA Master Plan region of each station's planning area: used only to check the region field
URA_REGION = {"Raffles Place": "Central", "Tanjong Pagar": "Central", "Marina Bay": "Central", "Bugis": "Central",
              "Orchard": "Central", "Somerset": "Central", "Tampines Hub": "East", "Jurong East": "West",
              "Bishan": "Central", "Woodlands": "North", "Pasir Ris": "East", "Sentosa": "Central",
              "one-north": "Central", "Buona Vista": "Central", "Paya Lebar": "Central", "Serangoon": "North-East",
              "Ang Mo Kio": "North-East", "Clarke Quay": "Central", "HarbourFront": "Central",
              "Changi Business Park": "East"}

INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#d9d8d3"


def severity(r):
    return "high" if r <= 2 else ("medium" if r == 3 else "low")


# ------------------------------------------------------------------ step 1
def validate(t, s, f):
    rows = []
    def add(level, check, n, note=""):
        rows.append({"level": level, "check": check, "count": int(n), "note": note})
    dup = t.trip_id.duplicated().sum(); add("FAIL" if dup else "ok", "trip_id unique", dup)
    nul = t.isna().sum().sum(); add("FAIL" if nul else "ok", "no blank trip fields", nul)
    bad = (~t.start_station.isin(s.station) | ~t.end_station.isin(s.station)).sum()
    add("FAIL" if bad else "ok", "stations exist in station table", bad)
    calc = (t.end_time - t.start_time).dt.total_seconds() / 60
    mis = ((calc - t.duration_min).abs() > 1).sum(); add("FAIL" if mis else "ok", "duration = end - start", mis)
    rng = ((t.duration_min < 1) | (t.duration_min > 180)).sum(); add("WARN" if rng else "ok", "duration 1-180 min", rng)
    ts = t.sort_values(["bike_id", "start_time"])
    ov = ts[ts.groupby("bike_id").start_time.shift(-1) < ts.end_time]
    add("WARN" if len(ov) else "ok", "bike not on two trips at once", len(ov),
        "same bike_id on two overlapping trips: ID or logging error. Examples: " + ", ".join(ov.trip_id.head(3)))
    add("WARN", "round trips (start = end station)", (t.start_station == t.end_station).sum(),
        "valid, but they don't move bikes between stations")
    sd = t[t.start_station != t.end_station].groupby(["start_station", "end_station"]).distance_km.std()
    add("WARN", "distance consistent per station pair", (sd > 0.5).sum(),
        f"median std {sd.median():.2f} km for the same pair: distance is approximate")
    br = s[s.station.map(URA_REGION) != s.region]
    add("WARN" if len(br) else "ok", "station region matches URA planning region", len(br),
        "; ".join(f"{r.station}: '{r.region}' vs URA '{URA_REGION[r.station]}'" for r in br.itertuples()))
    fd = f.feedback_id.duplicated().sum(); add("FAIL" if fd else "ok", "feedback_id unique", fd)
    fr = (~f.rating.between(1, 5)).sum(); add("FAIL" if fr else "ok", "rating 1-5", fr)
    un = (~f.comment_text.isin(THEMES)).sum()
    add("FAIL" if un else "ok", "every comment has an approved theme", un, "new comment types go to a human first")
    add("WARN", "feedback has no station field", len(f), "complaints can't be tied to a station")
    log = pd.DataFrame(rows); log.to_csv(OUT / "data_quality_log.csv", index=False)
    return log


# ------------------------------------------------------------------ step 2
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


def opening_stock(t, cap):
    """Largest running loss of bikes per station per day -> the stock it needed at opening."""
    ev = pd.concat([pd.DataFrame({"station": t.start_station, "ts": t.start_time, "d": -1}),
                    pd.DataFrame({"station": t.end_station, "ts": t.end_time, "d": 1})]).sort_values(["ts", "d"])
    ev["day"] = ev.ts.dt.normalize()
    ev["run"] = ev.groupby(["station", "day"]).d.cumsum()
    need = (-ev.groupby(["station", "day"]).run.min()).clip(lower=0)
    g = need.groupby("station")
    df = pd.DataFrame({"avg_day": g.mean().round(1), "p90_day": g.quantile(OPENING_STOCK_PCTL).round(0),
                       "worst_day": g.max(), "capacity": cap})
    half = (cap / 2).round()
    df["days_empty_if_half_full"] = need.groupby("station").apply(lambda x: int((x > half[x.name]).sum()))
    df["p90_pct_capacity"] = (df.p90_day / df.capacity * 100).round(0)
    return df.sort_values("p90_pct_capacity", ascending=False)


def main(week_start=None):
    t = pd.read_csv(RAW / "CityCycle_trips.csv", parse_dates=["start_time", "end_time"])
    s = pd.read_csv(RAW / "CityCycle_stations.csv")
    f = pd.read_csv(RAW / "CityCycle_feedback.csv", parse_dates=["date"])
    control = {"trips_rows": len(t), "stations_rows": len(s), "feedback_rows": len(f),
               "total_ride_minutes": int(t.duration_min.sum()), "total_km": round(float(t.distance_km.sum()), 2)}

    log = validate(t, s, f)
    if (log.level == "FAIL").any():
        print("DATA CONTRACT FAILED - no report produced. See out/data_quality_log.csv"); sys.exit(1)

    if week_start:
        ws = pd.Timestamp(week_start); we = ws + pd.Timedelta(days=7)
        t = t[(t.start_time >= ws) & (t.start_time < we)]; f = f[(f.date >= ws) & (f.date < we)]
    cap = s.set_index("station").capacity
    days = t.start_time.dt.normalize().nunique()

    flows = peak_flows(t, cap)
    pd.concat(flows, axis=1).to_csv(OUT / "station_peak_flows.csv")
    stock = opening_stock(t, cap); stock.to_csv(OUT / "opening_stock_needed.csv")
    hourly = pd.crosstab(t.start_time.dt.hour, t.user_type)

    # step 3 - classify feedback: sentiment from text, severity from stars, disagreement -> review
    f = f.assign(theme=f.comment_text.map(lambda c: THEMES[c][0]),
                 sentiment=f.comment_text.map(lambda c: THEMES[c][1]),
                 severity=f.rating.map(severity))
    f["needs_review"] = ((f.sentiment == "negative") & (f.rating >= 4)) | ((f.sentiment == "positive") & (f.rating <= 2))
    f.to_csv(OUT / "feedback_classified.csv", index=False)
    f[f.needs_review | f.theme.isin(SAFETY_THEMES)].to_csv(OUT / "needs_review.csv", index=False)
    neg = f[f.sentiment == "negative"]
    themes = (neg.groupby("theme").agg(n=("feedback_id", "size"), avg_rating=("rating", "mean"),
                                       high_severity=("severity", lambda x: int((x == "high").sum())))
              .sort_values("n", ascending=False).round(2))
    themes.to_csv(OUT / "feedback_themes.csv")

    am, pm = flows[list(PEAKS)[0]], flows[list(PEAKS)[1]]
    facts = {
        "window": {"from": str(t.start_time.min().date()), "to": str(t.start_time.max().date()), "days": int(days)},
        "control_totals": control,
        "data_quality_warnings": log[log.level == "WARN"][["check", "count"]].to_dict("records"),
        "trips": {"total": len(t), "per_day": round(len(t) / days, 1),
                  "member_share_pct": round((t.user_type == "Member").mean() * 100, 1),
                  "avg_minutes_member": round(t[t.user_type == "Member"].duration_min.mean(), 1),
                  "avg_minutes_casual": round(t[t.user_type == "Casual"].duration_min.mean(), 1),
                  "member_peak_hours": [int(h) for h in hourly["Member"].nlargest(2).index],
                  "casual_peak_hour": int(hourly["Casual"].idxmax())},
        "busiest_start_stations": t.start_station.value_counts().head(5).to_dict(),
        "morning_peak_draining": am[am.net_leaving > 0].net_leaving.sort_values(ascending=False).to_dict(),
        "evening_peak_net_leaving_range": [float(pm.net_leaving.min()), float(pm.net_leaving.max())],
        "opening_stock_needed_top": stock.head(6)[["p90_day", "worst_day", "capacity", "p90_pct_capacity",
                                                   "days_empty_if_half_full"]].to_dict("index"),
        "feedback": {"total": len(f), "negative": len(neg), "positive": int((f.sentiment == "positive").sum()),
                     "avg_rating": round(f.rating.mean(), 2),
                     "top_issues": themes.head(6).reset_index()[["theme", "n", "avg_rating", "high_severity"]].to_dict("records"),
                     "safety_mentions": int(f.theme.isin(SAFETY_THEMES).sum()),
                     "rating_text_disagree": int(f.needs_review.sum())},
    }
    (OUT / "facts.json").write_text(json.dumps(facts, indent=2, default=str))
    charts(flows, hourly, themes, stock)
    print(json.dumps(facts, indent=2, default=str))


# ------------------------------------------------------------------ step 5
def style(ax):
    ax.set_facecolor(SURF)
    for sp in ["top", "right", "left"]:
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(GRID); ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.set_axisbelow(True)


def title(fig_or_ax, text, sub=None):
    fig_or_ax.suptitle(text, x=0.02, ha="left", color=INK, fontsize=12, fontweight="bold")


def charts(flows, hourly, themes, stock):
    plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": SURF})

    # Chart 1 - morning vs evening peak, small multiples on one shared axis
    names = list(PEAKS)
    order = flows[names[0]].net_leaving.sort_values().index
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 6), sharey=True, sharex=True)
    for ax, n in zip(axes, names):
        style(ax); d = flows[n].net_leaving.reindex(order)
        ax.barh(d.index, d.values, color=[ORANGE if v > 0 else BLUE for v in d.values], height=0.7)
        ax.axvline(0, color=INK2, lw=1); ax.xaxis.grid(True, color=GRID, lw=0.8)
        ax.set_title(n, loc="left", fontsize=10, color=INK)
        for y, v in enumerate(d.values):
            if abs(v) >= 0.3:
                ax.text(v + (0.06 if v > 0 else -0.06), y, f"{v:+.1f}", va="center", ha="left" if v > 0 else "right", fontsize=7.5, color=INK2)
    axes[0].set_xlim(-1.4, 2.6)
    fig.supxlabel("Net bikes leaving per weekday (departures minus arrivals)", color=INK2, fontsize=9)
    title(fig, "Six stations drain every morning, and the evening peak doesn't put the bikes back")
    fig.text(0.02, 0.905, "Orange = station loses bikes   Blue = station gains bikes", ha="left", fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.9)); fig.savefig(OUT / "chart1_peak_imbalance.png", dpi=200); plt.close(fig)

    # Chart 2 - hourly demand by rider type
    fig, ax = plt.subplots(figsize=(8, 4)); style(ax)
    for col, c in [("Member", BLUE), ("Casual", ORANGE)]:
        ax.plot(hourly.index, hourly[col], color=c, lw=2, marker="o", ms=4, label=col)
    for a, b in PEAKS.values():
        ax.axvspan(a / 60, b / 60, color=GREY, alpha=0.35, lw=0)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_xticks(range(6, 23, 2)); ax.set_xticklabels([f"{h:02d}:00" for h in range(6, 23, 2)])
    ax.set_ylabel("Trips started", color=INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.set_title("Members ride at the two commute peaks (shaded); casual riders at midday", loc="left", color=INK, fontsize=12, fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "chart2_hourly_demand.png", dpi=200); plt.close(fig)

    # Chart 3 - complaint themes, split by severity (from stars)
    th = themes.sort_values("n")
    fig, ax = plt.subplots(figsize=(8, 5)); style(ax)
    ax.barh(th.index, th.high_severity, color=ORANGE, height=0.7, label="1-2 stars (high severity)")
    ax.barh(th.index, th.n - th.high_severity, left=th.high_severity, color=GREY, height=0.7, label="3-5 stars")
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    for y, (n, r) in enumerate(zip(th.n, th.avg_rating)):
        ax.text(n + 0.4, y, f"{n}  (avg {r:.1f} stars)", va="center", fontsize=8, color=INK2)
    ax.set_xlabel("Negative comments (sentiment read from the text)", color=INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.set_title("App faults and morning availability lead the complaints", loc="left", color=INK, fontsize=12, fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "chart3_complaint_themes.png", dpi=200); plt.close(fig)

    # Chart 4 - availability vs usage: opening stock needed vs docks
    st = stock.sort_values("p90_pct_capacity")
    fig, ax = plt.subplots(figsize=(8.5, 6)); style(ax)
    ax.barh(st.index, st.capacity, color=GREY, height=0.75, label="Docks (capacity)")
    ax.barh(st.index, st.p90_day, color=BLUE, height=0.45, label="Bikes needed at opening (9 days in 10)")
    ax.scatter(st.worst_day, st.index, color=ORANGE, s=28, zorder=3, label="Worst day")
    for y, (c, n) in enumerate(zip(st.capacity, st.days_empty_if_half_full)):
        if n:
            ax.text(c + 0.4, y, f"empty on {n} day{'s' if n > 1 else ''} if opened half-full", va="center", fontsize=7.5, color=INK2)
    ax.xaxis.grid(True, color=GRID, lw=0.8); ax.set_xlim(0, 40)
    ax.set_xlabel("Bikes", color=INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(0, 1.07), ncol=3)
    ax.set_title("Raffles Place and Tanjong Pagar need almost half their docks filled", loc="left", color=INK, fontsize=12, fontweight="bold", pad=26)
    fig.tight_layout(); fig.savefig(OUT / "chart4_restock_need.png", dpi=200); plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--week-start")
    main(ap.parse_args().week_start)
