"""Efficiency estimate for Question 1c, computed from the stated assumptions (efficiency_assumptions.json).

    python workflow/efficiency_model.py

Writes out/efficiency/efficiency_estimate.json and chart_time_per_week.png.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
A = json.loads((ROOT / "workflow" / "efficiency_assumptions.json").read_text())
OUT = ROOT / "out" / "efficiency"; OUT.mkdir(parents=True, exist_ok=True)

manual, auto = sum(A["manual"].values()), sum(A["automated"].values())
saved = manual - auto
weeks, rate = A["working_weeks_per_year"], A["analyst_cost_per_hour_sgd"]
lo, hi = A["sensitivity_manual_hours"]
est = {
    "manual_minutes": manual, "manual_hours": round(manual / 60, 1),
    "automated_minutes": auto, "automated_hours": round(auto / 60, 2),
    "saved_minutes": saved, "saved_hours": round(saved / 60, 1), "saved_pct": round(saved / manual * 100),
    "saved_hours_per_year": round(saved / 60 * weeks), "saved_value_sgd_per_year": round(saved / 60 * weeks * rate, -2),
    "sensitivity_saved_hours": [round(lo - auto / 60, 1), round(hi - auto / 60, 1)],
    "assumptions": A,
}
(OUT / "efficiency_estimate.json").write_text(json.dumps(est, indent=2))

INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SHORT = ["Export", "Pivots & shortages", "Read", "Charts", "Commentary", "Rebalancing plan"]
fig, ax = plt.subplots(figsize=(8.5, 3.2)); ax.set_facecolor(SURF); fig.patch.set_facecolor(SURF)
left = 0
for i, m in enumerate(A["manual"].values()):
    ax.barh(1, m, left=left, color="#eb6834" if i % 2 == 0 else "#f29a74", height=0.55, edgecolor=SURF, linewidth=1.5)
    ax.text(left + m / 2, 1, SHORT[i] if i < len(SHORT) else "", ha="center", va="center", fontsize=7.5, color="white")
    left += m
ax.text(left + 4, 1, f"{manual} min ({manual / 60:.1f} h)", va="center", fontsize=9, color=INK2)
ax.barh(0, auto, color="#2a78d6", height=0.55)
ax.text(auto + 4, 0, f"{auto} min: review checks, read draft, approve plan, sign off, upkeep", va="center", fontsize=8.5, color=INK2)
ax.set_yticks([0, 1]); ax.set_yticklabels(["Automated", "Manual"])
for sp in ["top", "right", "left"]:
    ax.spines[sp].set_visible(False)
ax.spines["bottom"].set_color(GRID); ax.tick_params(colors=INK2, length=0); ax.xaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
ax.set_xlim(0, manual * 1.22); ax.set_xlabel("Minutes of staff time per week (assumptions in efficiency_assumptions.json)", color=INK2, fontsize=9)
ax.set_title(f"Staff time per week falls from {manual / 60:.1f} hours to {auto} minutes", loc="left", color=INK, fontsize=12, fontweight="bold")
fig.tight_layout(); fig.savefig(OUT / "chart_time_per_week.png", dpi=200); plt.close(fig)
print(json.dumps({k: v for k, v in est.items() if k != "assumptions"}, indent=1))
