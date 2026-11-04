# Work order · CityCycle weekly operations report (v2.0)

Approved by: ______________ (operations manager) · Date: __________
Any change to a definition below needs a new sign-off and a new version number.

| Element | Specification |
|---|---|
| Goal | A decision-ready weekly operations report, with next week's rebalancing plan, that takes under 30 minutes of analyst time |
| Business questions | (1) Where are bikes running out, and when? (2) How should bikes be rebalanced, and should it be done overnight or at midday? (3) Which stations are busiest, and is usage changing? (4) What are riders complaining about, and which complaints are safety issues? |
| Reporting week | The latest complete week (Monday–Sunday) by default; all earlier data gives context |
| Inputs | `CityCycle_trips.csv`, `CityCycle_stations.csv`, `CityCycle_feedback.csv`; approved feedback taxonomy (`THEMES` in `weekly_report.py`) |
| Constraints | No personal data in prompts. All numbers are computed in code, never by the language model. The model may only quote figures in `facts.json`. Comment text is data, never instructions |
| Acceptance criteria | No data-contract failure; control totals match source row counts; every number in the report traces to `facts.json` (`verify_report.py`); key figures match an independent recalculation (`independent_check.py`); at least four charts; human sign-off recorded |
| Output | Two-page report with rebalancing plan; `rebalancing_plan.csv`, `rebalancing_transfers.csv`; `safety_escalations.csv`; `needs_review.csv`; `data_quality_log.csv`; AI-use log entry |

## Approved definitions

| Term | Definition | Why |
|---|---|---|
| Peak hours | Weekdays 08:00–10:00, 12:00–13:00 and 17:00–20:00 | Detected from the data: 30-minute slots with at least 1.5× the average weekday demand. Re-checked every run; if the detected windows change, the report flags it and a person approves any change |
| Peak consistency | Busiest morning and evening hour per complete week | 08:00 busiest in 10 of 12 weeks, 18:00 in 11 of 12; same on every weekday |
| Net bikes leaving | Departures starting in a peak minus arrivals ending in it, per weekday | Shows which stations lose or gain bikes |
| Daily rebalancing | The team resets every station to its opening target overnight, every day. Days are independent: nothing carries over | Matches operations; the data doesn't record truck moves |
| Opening target | Middle of the safe range: enough bikes for a 9-in-10 day's largest loss AND enough free docks for a 9-in-10 day's largest gain. Set from the latest 4 complete weeks | Avoids both empty stations and full docks |
| Timing rule | Overnight only, unless replaying the week shows a midday run (11:00, the quiet gap between peaks) would turn away fewer riders | Midday trucks cost extra moves; only justified if riders benefit |
| Rounding the plan | Average moves are rounded to whole bikes so that bikes delivered equal bikes collected. If an adjustment is needed, collect one more bike rather than deliver one fewer; remaining ties go alphabetically | Found by the independent check: the rule was ambiguous on ties |
| Watch list | A station that hits empty or full on 2+ days in a week, even with no rider turned away, gets its target reviewed | Catches near-misses early |
| Opening full | Rejected | Riders would find no free dock (224 riders in the week of 23 March) |
| Sentiment / severity | Sentiment from the comment text; severity from stars (1–2 high, 3 medium, 4–5 low) | Ratings and text disagree in about 1 comment in 5 |
| Rating watch list | Complaint types whose star ratings are lower than all other comments with Mann–Whitney p < 0.01, recomputed each run (`rating_impact.csv`). Types with significantly HIGHER stars are flagged as 'hidden by high stars' and tracked from the text | Shows which complaints hurt the rating most, and which ones the stars would hide |
| Safety issue | Themes "Brakes loose" and "Gears slipping" | Escalated to the maintenance lead the same day; listed in `safety_escalations.csv` |
| Trend | Complete weeks only; this week vs the previous 4-week average; monthly figures per day | Partial weeks and month lengths distort comparisons |
