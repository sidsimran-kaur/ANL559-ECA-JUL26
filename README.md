# ANL559 ECA · CityCycle weekly operations report and rebalancing plan

ANL559 Generative AI for Work Automation in Analytics, End-of-Course Assessment, July 2026.
This is a private working repository and the audit trail for Question 1.

## Run it

```bash
pip install pandas matplotlib openpyxl
python workflow/weekly_report.py                              # latest complete week (default)
python workflow/weekly_report.py --week-start 2026-03-16      # any other week
python workflow/verify_report.py out/week_2026-03-23/weekly_report_draft.md
python workflow/independent_check.py 2026-03-23
cd workflow && python backtest_weeks.py                       # rebalancing timing on every testable week
```

## Pipeline (v2)

1. **Validate**: data contract on the reporting week; a FAIL stops the run
2. **Compute**: peak hours detected from the data (weekday 30-min slots ≥ 1.5× average) and checked for week-to-week consistency; station flows in each peak
3. **Rebalance**: the team resets every station overnight, so days are independent. Opening target per station from the latest 4 weeks; the week is replayed to compare overnight-only with overnight + 11:00 rebalancing; nightly move list and transfer pairs; watch list for near-misses
4. **Classify**: theme and sentiment from text, severity from stars; brakes and gears are **safety** issues, escalated the same day
5. **Facts**: `facts.json`, the only numbers the language model may quote; six charts
6. **Check**: `verify_report.py` (every number traced), `independent_check.py` (key figures recomputed differently), then human review and sign-off

## Layout

| Path | What it is |
|---|---|
| `data/raw/` | CityCycle data as provided. Never edited |
| `workflow/work_order.md` | Work order v2.0 and approved definitions |
| `workflow/*.py` | Pipeline, checks, backtest |
| `out/week_<Monday>/` | One folder per reporting week: facts, plan, safety list, review list, charts, draft report, check results |
| `out/backtest_rebalancing_by_week.csv` | Overnight vs midday rebalancing on 8 weeks of unseen data |
| `report/` | Write-up drafts (`ANL559_ECA_1a_1b_v3.docx` is current) and builder |
| `ai_use_log/` | AI-use log v2 (`.docx`, `.md`); full AI outputs go in `outputs/` |
| `docs/` | Earlier explainer (v1, superseded by v2 pipeline) |
