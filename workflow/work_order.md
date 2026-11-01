# Work order · CityCycle weekly operations report (v1.1)

Approved by: ______________ (operations manager) · Date: __________
Any change to a definition below needs a new sign-off and a new version number.

| Element | Specification |
|---|---|
| Goal | A decision-ready weekly operations report that takes under 30 minutes of analyst time |
| Business questions | (1) Where are bikes running out? (2) Which stations are busiest? (3) What are riders complaining about? |
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
| Opening stock needed | The 90th percentile, across days, of the largest number of bikes a station lost in a day before it got any back. Stocking to this level would have avoided an empty station on 9 days in 10 | No dock-level inventory data exists, so the need is estimated from trips |
| Sentiment | Taken from the comment text (taxonomy) | Ratings and text disagree in about 1 comment in 5 |
| Severity | Taken from the star rating: 1–2 high, 3 medium, 4–5 low | Shows how much the issue hurt the rider |
| Safety issue | Any comment in the theme "Brakes loose" | Escalated the same day; not held for the weekly report |
