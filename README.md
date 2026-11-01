# ANL559 ECA · CityCycle weekly operations report automation

ANL559 Generative AI for Work Automation in Analytics, End-of-Course Assessment, July 2026.
This is a private working repository and the audit trail for Question 1.

## Run it

```bash
pip install pandas matplotlib openpyxl
python workflow/weekly_report.py                          # whole quarter
python workflow/weekly_report.py --week-start 2026-03-23  # one reporting week
python workflow/verify_report.py out/report_draft.md      # number check on a drafted report
```

## Layout

| Path | What it is |
|---|---|
| `data/raw/` | CityCycle trips, stations, feedback (CSV) and the combined workbook, as provided. Never edited |
| `workflow/work_order.md` | The work order and approved definitions (peaks, severity, safety) |
| `workflow/weekly_report.py` | Steps 1–4: validate, compute, classify, write `facts.json` and the charts |
| `workflow/verify_report.py` | Step 5: every number in the draft must appear in `facts.json` |
| `out/` | Generated outputs: data-quality log, flows, opening stock, classified feedback, needs-review list, `facts.json`, charts |
| `ai_use_log/` | AI-use log (`.md` and `.docx`); full AI outputs go in `ai_use_log/outputs/` |
| `docs/` | Notes for Question 1a: explainer and suggested wording |
| `report/` | Report drafts (`.docx`) |

## Pipeline

1. **Validate**: data contract; a FAIL stops the run (`out/data_quality_log.csv`)
2. **Compute**: weekday peaks 07:00–09:00 and 17:30–19:30, busiest stations, safe opening range per station (tested on unseen weeks), usage and complaint trends
3. **Classify**: theme and sentiment from the comment text, severity from the stars; disagreements go to `out/needs_review.csv`
4. **Facts**: `out/facts.json`, the only numbers the language model may quote
5. **Check**: `verify_report.py`, then the analyst reviews and the operations manager signs off
