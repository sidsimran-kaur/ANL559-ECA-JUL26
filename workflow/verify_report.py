"""Step 5 CHECK: every number in the drafted report must be traceable to out/facts.json.

    python workflow/verify_report.py out/report_draft.md

Prints each number in the text, PASS if it matches a value in facts.json (allowing for rounding),
UNTRACED if not. Exits with code 1 if anything is untraced, and the report stays DRAFT.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
report_path = Path(sys.argv[1]).resolve()
# use the facts.json next to the report if there is one (weekly runs), else the quarter's
facts_path = report_path.parent / "facts.json" if (report_path.parent / "facts.json").exists() else ROOT / "out" / "facts.json"
facts = json.loads(facts_path.read_text())
print(f"Checking {report_path.name} against {facts_path}")

# Numbers that come from approved definitions in work_order.md, not from the data
DEFINITION_NUMBERS = {7, 9, 17, 19, 30, 90, 1, 2, 3, 4, 5}


def flatten(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from flatten(v)
    elif isinstance(x, list):
        for v in x:
            yield from flatten(v)
    elif isinstance(x, (int, float)) and not isinstance(x, bool):
        yield float(x)


values = set(flatten(facts))
# derived forms a writer may legitimately use: rounded, percentage of a share
allowed = set()
for v in values:
    allowed |= {round(v, 2), round(v, 1), round(v), round(abs(v), 2), round(abs(v), 1), round(abs(v))}


def traced(num):
    return any(abs(num - a) < 1e-9 for a in allowed)


text = report_path.read_text(encoding="utf-8")
# charts: the work order requires at least four, and each must exist next to the report
MIN_CHARTS = 4
charts = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
missing_charts = [c for c in charts if not (report_path.parent / c).exists()]
text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)          # image lines carry no numbers to trace
# ignore dates (2026-03-23, 23–29 March 2026) and clock times (07:00) - labels, not findings
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
clean = re.sub(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}", " ", text)
clean = re.sub(rf"\d{{1,2}}(?:[–-]\d{{1,2}})?\s+(?:{MONTHS})\s+\d{{4}}", " ", clean)   # written dates, e.g. 23–29 March 2026
nums = [n for n in re.findall(r"(?<![\w.])-?\d[\d,]*\.?\d*", clean)]
bad = []
for raw in nums:
    n = float(raw.replace(",", "").rstrip("."))
    if traced(n):
        status = "PASS"
    elif n in DEFINITION_NUMBERS:
        status = "PASS (definition)"
    else:
        status = "UNTRACED"; bad.append(raw)
    print(f"{status:18s} {raw}")
print(f"\n{len(nums) - len(bad)}/{len(nums)} numbers traced to facts.json")

# ---- Part 2: every number written next to a station name must belong to THAT station in facts.json

def station_pairs(obj, out):
    """Collect (station, value) pairs from every dict in facts.json keyed by station name."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.setdefault(k, set()).add(round(float(v), 2))
            station_pairs(v, out)
    elif isinstance(obj, list):
        for v in obj:
            station_pairs(v, out)


pairs = {}
station_pairs(facts, pairs)
stations = [s for s in pairs if s[:1].isupper() or s == "one-north"]
transfers = {(t["from"], t["to"], t["bikes"]) for t in facts.get("rebalancing", {}).get("transfers", [])}
name_re = "|".join(re.escape(s) for s in sorted(stations, key=len, reverse=True))
pair_bad, n_pairs = [], 0
# "A → B 3" transfers
for a, b, n in re.findall(rf"({name_re})\s*→\s*({name_re})\s+(\d+)", text):
    n_pairs += 1
    if (a, b, int(n)) not in transfers:
        pair_bad.append(f"{a} → {b} {n} (not in the transfer plan)")
text_no_arrows = re.sub(rf"({name_re})\s*→\s*({name_re})\s+\d+", " ", text)
# "A, B and C 1 each" groups
for group, n in re.findall(rf"((?:(?:{name_re})(?:,\s*|\s+and\s+))+(?:{name_re}))\s+(\d+(?:\.\d+)?)\s+each", text_no_arrows):
    for st in re.findall(name_re, group):
        n_pairs += 1
        if round(float(n), 2) not in pairs.get(st, set()):
            pair_bad.append(f"{st} {n} (from a list; facts has {sorted(pairs.get(st, []))})")
text_no_groups = re.sub(rf"((?:(?:{name_re})(?:,\s*|\s+and\s+))+(?:{name_re}))\s+\d+(?:\.\d+)?\s+each", " ", text_no_arrows)
# "Station 4" / "Station 2.8"
for st, n in re.findall(rf"({name_re})\s+(\d+(?:\.\d+)?)(?![\d:])", text_no_groups):
    n_pairs += 1
    if round(float(n), 2) not in pairs.get(st, set()):
        pair_bad.append(f"{st} {n} (facts has {sorted(pairs.get(st, []))})")
print(f"{n_pairs - len(pair_bad)}/{n_pairs} station-number pairs match facts.json")
for b in pair_bad:
    print("MISMATCH          ", b)

print(f"{len(charts) - len(missing_charts)} charts embedded (minimum {MIN_CHARTS})")
chart_bad = len(charts) - len(missing_charts) < MIN_CHARTS or bool(missing_charts)
for c in missing_charts:
    print("MISSING CHART     ", c)
if chart_bad:
    print(f"TOO FEW CHARTS -> the work order requires at least {MIN_CHARTS}; report stays DRAFT")
    sys.exit(1)

if bad or pair_bad:
    if bad:
        print("UNTRACED:", ", ".join(bad), "-> report stays DRAFT; fix or justify before sign-off")
    if pair_bad:
        print("MISMATCHED PAIRS -> a number is attached to the wrong station; report stays DRAFT")
    sys.exit(1)
print("All numbers traced -> ready for human review")
