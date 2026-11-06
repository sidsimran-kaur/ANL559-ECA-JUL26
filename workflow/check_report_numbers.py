"""Counter-check every number in the reports before anything is submitted or sent.

    python workflow/check_report_numbers.py
    python workflow/check_report_numbers.py report/ANL559_ECA_1a_1b_v5.docx

Three checks, all must pass (exit code 0):
  A. WRITE-UP CLAIMS   every registered number in report_claims.json is recomputed from the raw CSVs
                       by truth.py (independent code: csv module, no pandas, no pipeline imports)
                       and must match, rounded as written.
  B. COVERAGE          every number in 1a/1b must belong to a registered claim or definition, so a new
                       or edited figure can't slip through unchecked.
  C. WEEKLY REPORT     the drafted weekly report must trace 100% to its facts.json (verify_report.py),
                       and the key figures must match the independent recalculation (independent_check.py).
Results are written to report/check_result.txt.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import docx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import truth  # noqa: E402

WORDS = {"no": 0, "none": 0, "zero": 0, "once": 1, "one": 1, "two": 2, "twice": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
LABELS = [r"\b(?:Figure|Table|Appendix|row|rows|step|Step)\s+[\dA-Z]+(?:\s*[–-]\s*\d+)?", r"Opus\s+\d+(?:\.\d+)?",
          rf"\d{{1,2}}(?:\s*[–-]\s*\d{{1,2}})?\s+(?:{MONTHS})(?:\s+\d{{4}})?", r"\b\d{1,2}:\d{2}(?:\s*[–-]\s*\d{1,2}:\d{2})?",
          r"\b(?:19|20)\d{2}\b"]


def norm(s):
    return s.replace(" ", " ").replace("‑", "-").replace("’", "'").replace("“", '"').replace("”", '"')


def writeup_text(path):
    """Body text in document order, including tables (cells joined with ' | ')."""
    d = docx.Document(path); parts = []
    for el in d.element.body.iterchildren():
        tag = el.tag.split("}")[1]
        if tag == "p":
            parts.append("".join(t.text or "" for t in el.iter() if t.tag.endswith("}t")))
        elif tag == "tbl":
            for tr in el.iter():
                if tr.tag.endswith("}tr"):
                    cells = []
                    for tc in tr:
                        if tc.tag.endswith("}tc"):
                            cells.append(" ".join("".join(t.text or "" for t in p.iter() if t.tag.endswith("}t"))
                                                  for p in tc if p.tag.endswith("}p")))
                    parts.append(" | ".join(cells))
    text = norm("\n".join(parts))
    return text[text.index("1a. Design"):text.index("Appendix A:")]


def to_number(raw):
    return float(raw.replace(",", "").replace("%", ""))


def equal(written, true, absolute=False):
    if isinstance(true, list):                              # e.g. peak windows: membership
        return written in true
    if isinstance(true, str):
        return written == true
    w = WORDS[written.lower()] if written.lower() in WORDS else to_number(written)
    t = abs(true) if absolute else true
    decimals = len(written.split(".")[1]) if "." in written and written.lower() not in WORDS else 0
    return round(t, decimals) == w


def main():
    claims_file = json.loads((ROOT / "report" / "report_claims.json").read_text(encoding="utf-8"))
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted((ROOT / "report").glob("ANL559_ECA_1a*_v*.docx"),
                                                               key=lambda p: int(re.search(r"_v(\d+)", p.stem).group(1)))[-1]
    week = claims_file["week"]
    T = truth.compute(week)
    text = writeup_text(path)
    lines, fails = [f"Checking {path.name} (claims: report_claims.json, week {week})", ""], 0

    # ---- A. claims
    lines.append("A. Write-up numbers vs independent recalculation")
    covered = []
    for c in claims_file["claims"]:
        phrase = norm(c["phrase"])
        pos = text.find(phrase)
        if pos < 0:
            fails += 1; lines.append(f"  FAIL  phrase not found (sentence edited? update report_claims.json): \"{phrase}\""); continue
        covered.append((pos, pos + len(phrase)))
        for kind in ("values", "words"):
            for written, keys in c.get(kind, {}).items():
                for key in keys if isinstance(keys, list) else [keys]:
                    ok = equal(written, T[key], c.get("abs", False))
                    fails += not ok
                    lines.append(f"  {'ok  ' if ok else 'FAIL'}  {written:>12}  vs {key} = {T[key]}   \"{phrase[:60]}\"")
    for d in claims_file["definitions"]:
        pos = text.find(norm(d))
        if pos >= 0:
            covered.append((pos, pos + len(norm(d))))

    # ---- B. coverage
    lines += ["", "B. Every number in 1a/1b is registered"]
    masked = text
    for pat in LABELS:
        masked = re.sub(pat, lambda m: " " * len(m.group(0)), masked)
    unregistered = []
    for m in re.finditer(r"(?<![\w.,])\d[\d,]*(?:\.\d+)?%?(?![A-Za-z])", masked):
        if not any(a <= m.start() < b for a, b in covered):
            ctx = text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
            unregistered.append(f"  FAIL  unregistered number {m.group(0)!r}: ...{ctx}...")
    fails += len(unregistered)
    lines += unregistered or ["  ok    all numbers belong to a registered claim, a definition or a label"]

    # ---- C. weekly report
    lines += ["", f"C. Weekly report for week {week}"]
    draft = ROOT / "out" / f"week_{week}" / "weekly_report_draft.md"
    for name, cmd in [("verify_report.py", [sys.executable, str(ROOT / "workflow" / "verify_report.py"), str(draft)]),
                      ("independent_check.py", [sys.executable, str(ROOT / "workflow" / "independent_check.py"), week])]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        last = [l for l in r.stdout.strip().splitlines() if l.strip()][-1] if r.stdout.strip() else r.stderr.strip()[-200:]
        fails += r.returncode != 0
        lines.append(f"  {'ok  ' if r.returncode == 0 else 'FAIL'}  {name}: {last}")

    lines += ["", f"RESULT: {'PASS - all numbers check out' if fails == 0 else f'FAIL - {fails} problem(s); fix before submitting'}"]
    out = "\n".join(lines)
    (ROOT / "report" / "check_result.txt").write_text(out + "\n", encoding="utf-8")
    print(out)
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
