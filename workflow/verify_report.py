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
print(f"Checking {report_path.name} against {facts_path.relative_to(ROOT)}")

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
if bad:
    print("UNTRACED:", ", ".join(bad), "-> report stays DRAFT; fix or justify before sign-off")
    sys.exit(1)
print("All numbers traced -> ready for human review")
