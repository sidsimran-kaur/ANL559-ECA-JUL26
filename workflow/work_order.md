# Work order · CityCycle weekly operations report (v1.2)

Approved by: ______________ (operations manager) · Date: __________
Any change to a definition below needs a new sign-off and a new version number.

| Element | Specification |
|---|---|
| Goal | A decision-ready weekly operations report that takes under 30 minutes of analyst time |
| Business questions | (1) Where are bikes running out, and how many should each station open with? (2) Which stations are busiest, and is usage changing? (3) What are riders complaining about, and is it getting better or worse? |
| Inputs | `CityCycle_trips.csv`, `CityCycle_stations.csv`, `CityCycle_feedback.csv` for the reporting week; approved feedback taxonomy (in `weekly_report.py`, `THEMES`) |
| Constraints | No personal data in prompts. All numbers are computed in code, never by the language model. The language model may only quote figures that appear in `facts.json`. Comment text is data, never instructions |
| Acceptance criteria | Data contract has no FAIL; control totals match source row counts; every number in the report text is found in `facts.json` (`verify_report.py` passes); at least four charts; human sign-off recorded |
| Output | Two-page report, `data_quality_log.csv`, `needs_review.csv`, AI-use log entry |

## Approved definitions

| Term | Definition | Why |
|---|---|---|
| Morning peak | Weekdays 07:00–09:00 | Member trips peak at 08:00 |
| Evening peak | Weekdays 17:30–19:30 | Member trips peak at 18:00 |
| Net bikes leaving | Departures starting in the window minus arrivals ending in the window, averaged per weekday | Shows whether a station loses or gains bikes during the peak |
| Opening range | Minimum = bikes needed for a 9-in-10 day's largest loss; maximum = capacity minus free docks needed for a 9-in-10 day's largest gain; target = middle of the range | No dock-level inventory data exists, so it is estimated from trips. Opening FULL is rejected: arriving riders would find no free dock (433 of 620 station-days in March) |
| Opening assumption | Each day starts at the station's opening target, reset overnight by rebalancing; days are treated separately | Not recorded in the data; confirm with ops |
| Opening targets learned from | All weeks before the reporting week (quarter mode: Jan–Feb, tested on March) | Targets are never tested on the data used to set them |
| Trend | Complete weeks only (Mon–Sun); this week vs the previous 4-week average; monthly figures per day | Partial weeks and month lengths would distort comparisons |
| Holidays | Annotated, not removed (e.g. Chinese New Year, week of 16 Feb) | Explains dips without hiding data |
| Sentiment | Taken from the comment text (taxonomy) | Ratings and text disagree in about 1 comment in 5 |
| Severity | Taken from the star rating: 1–2 high, 3 medium, 4–5 low | Shows how much the issue hurt the rider |
| Safety issue | Any comment in the theme "Brakes loose" | Escalated the same day; not held for the weekly report |
