// Builds docs/ANL559_ECA_1a_explainer.docx and ai_use_log/ (docx + md) from one source.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType,
  ShadingType, AlignmentType, LevelFormat, ImageRun, BorderStyle, PageOrientation,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const FONT = "Calibri";
const runs = (text, size) => text.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(t =>
  t.startsWith("**") ? new TextRun({ text: t.slice(2, -2), bold: true, size }) : new TextRun({ text: t, size }));
const p = (t, o = {}) => new Paragraph({ spacing: { after: 120 }, ...o, children: runs(t) });
const h1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 280, after: 120 }, children: [new TextRun(t)] });
const h2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 220, after: 100 }, children: [new TextRun(t)] });
const h3 = t => new Paragraph({ spacing: { before: 140, after: 60 }, children: [new TextRun({ text: t, bold: true, color: "2E5597" })] });
const bullet = t => new Paragraph({ numbering: { reference: "b", level: 0 }, spacing: { after: 60 }, children: runs(t) });
const quote = t => new Paragraph({ spacing: { after: 140 }, indent: { left: 360 }, shading: { type: ShadingType.CLEAR, fill: "EEF4FB" },
  border: { left: { style: BorderStyle.SINGLE, size: 18, color: "2A78D6", space: 8 } }, children: runs(t) });
const code = t => t.split("\n").map(l => new Paragraph({ spacing: { after: 0 }, indent: { left: 360 },
  shading: { type: ShadingType.CLEAR, fill: "F3F3F1" }, children: [new TextRun({ text: l || " ", font: "Consolas", size: 17 })] }));
const img = (f, w, h) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 },
  children: [new ImageRun({ type: "png", data: fs.readFileSync(path.join(ROOT, "out", f)), transformation: { width: w, height: h } })] });

function table(widths, rows, size = 18) {
  const b = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
  return new Table({
    width: { size: widths.reduce((a, c) => a + c, 0), type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({ tableHeader: i === 0, cantSplit: false, children: r.map((c, j) => new TableCell({
      width: { size: widths[j], type: WidthType.DXA }, borders: { top: b, bottom: b, left: b, right: b },
      shading: i === 0 ? { type: ShadingType.CLEAR, fill: "DCE8F7" } : (r.length === 1 ? { type: ShadingType.CLEAR, fill: "F3F3F1" } : undefined),
      columnSpan: r.length === 1 ? widths.length : undefined,
      margins: { top: 50, bottom: 50, left: 80, right: 80 },
      children: String(c).split("\n").map(line => new Paragraph({ spacing: { after: 30 },
        children: i === 0 ? [new TextRun({ text: line, bold: true, size })] : runs(line, size) })),
    })) })),
  });
}
const styles = {
  default: { document: { run: { font: FONT, size: 21 } } },
  paragraphStyles: [
    { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 30, bold: true, color: "1F3864", font: FONT } },
    { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 24, bold: true, color: "2E5597", font: FONT } },
    { id: "Title", name: "Title", basedOn: "Normal", run: { size: 38, bold: true, font: FONT } },
  ],
};
const numbering = { config: [{ reference: "b", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
  style: { paragraph: { indent: { left: 400, hanging: 260 } } } }] }] };

// =====================================================================================
// EXPLAINER
// =====================================================================================
const E = [];
E.push(new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("Question 1a: your highlighted points, explained")] }));
E.push(p("For each part you highlighted: why it's done this way, what it looks like in the pipeline, and suggested wording you can adapt. All figures come from the re-run pipeline (workflow/weekly_report.py) on the full quarter, 1 Jan – 31 Mar 2026."));

E.push(h1("1. Why numbers are computed in code, never by the language model"));
E.push(p("A language model writes by predicting the most likely next words. It does not calculate. Ask it to count 6,500 trip rows and it may sample them, approximate, or give a figure that looks right but isn't, and it gives the wrong answer just as confidently as the right one. Code is deterministic: the same data gives the same number every time, it can be tested, it can be re-run every Monday, and a reviewer can read how each number was made."));
E.push(p("So the work is split: **code does the arithmetic, and the model does the language**, which means classifying free text and writing the narrative. The model can still write the code (Claude wrote weekly_report.py). What matters is that the code, not the model, produces the number, and that you review the code once rather than every number every week."));
E.push(p("**A concrete example from testing.** A draft sentence said Changi Business Park started 540 trips. The real figure is 533. 540 is close, plausible and round, which is exactly the kind of error a reader won't notice and the kind a model is likely to produce. The number check (section 2) caught it."));
E.push(quote("**Suggested wording:** All figures are calculated by a Python script, not by the language model. A model predicts text rather than calculating, so it can state a plausible but wrong number with full confidence. The script gives the same answer every time it runs and can be checked line by line."));

E.push(h1("2. Why the report is written from facts.json, and why every figure must trace to it"));
E.push(p("**What facts.json is:** a small file the script writes at the end of each run. It holds every approved number for the week: control totals, busiest stations, the stations that drain in each peak, opening stock needed, and complaint counts. It is the single source of truth, and the hand‑off point between code and AI."));
E.push(table([2300, 6726], [
  ["Reason", "What it means for CityCycle"],
  ["Grounding", "The model only ever sees the approved numbers, never the 6,500 raw rows, so it has nothing to compute and nothing to invent from. The prompt also says: 'if a figure is not in facts.json, write not available'."],
  ["Traceability (lineage)", "Any number in the report can be followed back: report → facts.json → script → raw file. A manager, auditor or your successor can check where it came from."],
  ["Automatic checking", "Because every allowed number is in one file, a script (verify_report.py) can compare each number in the draft against it. Tested with a planted error: it passed 10 numbers and flagged 540 as UNTRACED, so the report stays DRAFT."],
  ["Privacy (PDPA)", "Only aggregate numbers go to the AI tool, never trip-level records. This is data minimisation, which you can reuse in 1d."],
  ["Consistency", "The same definitions produce the same facts every week, so week-on-week comparisons are fair."],
]));
E.push(p("**Be honest about the limit (good material for 1d):** the check proves that a number exists in facts.json. It doesn't prove the number is attached to the right station or used in the right sentence. That is why the analyst still reads the draft."));
E.push(quote("**Suggested wording:** The script writes every approved figure to a single file, facts.json. The language model drafts the report from this file only, and a second script checks that every number in the draft appears in it. This keeps the model from inventing figures, lets any number be traced back to the raw data, and means only aggregates, never trip records, are shared with the AI tool."));

E.push(h1("3. Should we use both the star rating and the sentiment? Yes, for different jobs"));
E.push(p("The text tells you **what** the rider means. The stars tell you **how strongly** they feel. Either one alone misleads in this dataset:"));
E.push(bullet("**Stars only:** 16 'hard to find a bike at peak hour' comments average 4.5 stars, and 27 'app GPS shows wrong station' average 4.2. A star-based rule (4–5 = positive) would count 43 complaints as praise and understate the availability problem."));
E.push(bullet("**Text only:** you lose the intensity. 'App keeps crashing when I unlock' averages 2.3 stars and 'tyre was flat' 2.8, so the crash hurts more."));
E.push(p("**Recommended rule** (now in the pipeline and in work_order.md): sentiment and theme come from the text, severity comes from the stars (1–2 high, 3 medium, 4–5 low). Where the two disagree (63 comments, 21%), the comment goes to needs_review.csv for a human. Chart 3 shows both: each bar is a complaint theme (from text), split into 1–2 star and 3–5 star comments."));
E.push(p("Note: in the GBA, sentiment came from stars. This data shows why the text should lead here, and saying so in 1a or 1b shows you checked rather than reused a rule."));
E.push(img("chart3_complaint_themes.png", 540, 338));
E.push(quote("**Suggested wording:** Sentiment and theme are read from the comment text; the star rating is kept as a measure of severity. The two disagree in 63 of 300 comments (for example, 'hard to find a bike at peak hour' averages 4.5 stars), so using stars alone would hide complaints. Comments where they disagree are routed to a human for review."));

E.push(h1("4. Why the model reads the text and returns JSON"));
E.push(p("JSON is structured output: every comment comes back with the same fixed fields, so code can count, join and check it. A free-text answer ('most riders complain about the app') can't be counted or verified."));
E.push(...code('{"feedback_id": "F0044", "theme": "Docks full, can\'t return",\n "sentiment": "negative", "safety_flag": false}'));
E.push(p(" "));
E.push(bullet("**Countable:** the script tallies themes and joins them to the star rating for severity."));
E.push(bullet("**Checkable:** the code confirms every feedback_id comes back exactly once and every theme is on the approved list. If the model skips a comment or invents a new theme, the run stops."));
E.push(bullet("**Consistent:** a fixed taxonomy plus fixed fields means the same comment gets the same label every week."));
E.push(p("Efficiency point: the 300 comments contain only 18 distinct texts. So the model proposes the taxonomy once, you approve it, and it is frozen in code. The model is only needed again when a new kind of comment appears, which the data contract flags."));
E.push(quote("**Suggested wording:** The model returns its labels as JSON with fixed fields (ID, theme, sentiment, safety flag) rather than as prose, so the script can count them, check that every comment was labelled exactly once with an approved theme, and produce the same labels every week."));

E.push(h1("5. Two peaks: morning and evening"));
E.push(p("Yes. The pipeline now uses your two windows as approved definitions: **weekdays 07:00–09:00 and 17:30–19:30**. Member trips peak at 08:00 and 18:00 (Chart 2, with both windows shaded). The finding is stronger with both:"));
E.push(bullet("**Morning:** six stations lose bikes every weekday: Changi Business Park and Marina Bay 2.1 each, Tanjong Pagar 1.8, one-north and Clarke Quay 1.7, Raffles Place 1.6."));
E.push(bullet("**Evening:** every station stays between −0.6 and +0.4. The evening peak does **not** reverse the morning drain."));
E.push(bullet("**So the losses build up:** over the quarter Changi Business Park is down a net 211 bikes. The system doesn't rebalance itself, and someone has to restock."));
E.push(p("Update in your draft: step 2 says '7 to 10 am peak'; change it to the two windows."));
E.push(img("chart1_peak_imbalance.png", 560, 354));
E.push(img("chart2_hourly_demand.png", 520, 260));

E.push(h1("6. A chart of availability vs usage, to show the need to restock"));
E.push(p("There is no dock-level inventory data (no 'bikes on hand at 08:00' field), so availability is **estimated from the trips**. For each station and day, the script walks through departures (−1) and arrivals (+1) in time order and keeps a running total. Two numbers come out of each day:"));
E.push(bullet("**Largest loss:** the most bikes the station lost before getting any back. It must open with at least this many bikes, or someone finds it empty."));
E.push(bullet("**Largest gain:** the most bikes it gained. It must open with at least this many free docks, or someone can't return a bike."));
E.push(p("Using a 9-in-10-day level for both gives each station a **safe opening range** (minimum bikes to maximum bikes), and the target is the middle of it. Chart 4 shows the range inside each station's dock capacity, which is the 'availability vs usage' picture you wanted. Every station has a workable range. Raffles Place is the tightest, with only 7 to 12 bikes safe on 15 docks."));
E.push(img("chart4_restock_need.png", 540, 394));

E.push(h1("7. Can we assume every station starts the day full?"));
E.push(p("It is good that you want to state an opening assumption, because the analysis needs one. But **opening full is the wrong assumption, and the data shows why.** If every dock is full, there is nowhere to return a bike. I tested three opening rules on March data that the targets had not seen (targets were set on January–February):"));
E.push(table([3200, 1800, 2000, 2026], [
  ["Opening rule (March, 620 station-days)", "Days a rider finds no bike", "Days a rider finds no free dock", "Verdict"],
  ["Every station full", "0", "433 (70%)", "Rejected: blocks returns"],
  ["Every station half full", "0 (but 4 days in Jan–Feb)", "0", "Works most days"],
  ["Station-specific target (middle of safe range)", "0", "0", "Recommended"],
]));
E.push(p("Two more facts support this. First, the fleet has 899 bike IDs but only 450 docks, so 'all docks full' is a choice about where the spare bikes sit, not a natural state. Second, if stations really opened full, 'docks were all full' would be the biggest complaint. It is only 12 of 300."));
E.push(p("**What to assume instead (now in work_order.md):** each day starts at the station's opening target, reset overnight by the rebalancing team. Each day is treated separately, and the overnight reset is an assumption to confirm with operations, because the data doesn't record truck moves. Testing on unseen March data follows the course habit: never judge a rule on the data used to build it."));
E.push(quote("**Suggested wording:** The data does not record rebalancing, so I assume each station is reset overnight to an opening target. Opening every station full was tested and rejected: on March data, arriving riders would have found no free dock on 433 of 620 station-days. Instead, each station opens in the middle of a safe range, with enough bikes for a 9-in-10 day's outflow and enough free docks for a 9-in-10 day's inflow. Targets set on January–February data gave no empty or full stations in March."));

E.push(h1("8. Should trends be part of the report? Yes, with care"));
E.push(p("A weekly report that only describes this week can't tell management whether things are getting better or worse, and three months of data is enough to show direction. What the data shows:"));
E.push(table([2600, 6426], [
  ["Trend", "Finding (per day, so month lengths don't distort it)"],
  ["Usage", "70.9 → 71.3 → 74.4 trips a day (Jan → Mar). Casual riders 27.7 → 30.4, members flat (43.1 → 44.0). Complete weeks range from 468 to 545 trips"],
  ["Stations", "Growing fastest: Woodlands +29%, Bishan and HarbourFront +23%. Falling: Paya Lebar −24%"],
  ["Morning drain", "Raffles Place lost 1.2 bikes per weekday morning in January and 2.0 in March; Changi Business Park 1.9 → 2.4"],
  ["Complaints", "Availability complaints 16 → 14 → 25 (a jump in March, as the morning drain grew). Billing complaints fell every month (16 → 10 → 8)"],
  ["Holiday", "Member trips dip in the Chinese New Year week (16 Feb: 276, against 311 the week before); annotate it, don't delete it"],
]));
E.push(img("chart5_weekly_trend.png", 520, 260));
E.push(img("chart6_complaint_trend.png", 540, 180));
E.push(p("**How to present trends responsibly:**"));
E.push(bullet("Compare complete weeks only; the first (1–4 Jan) and last (30–31 Mar) are partial."));
E.push(bullet("In the weekly report, compare this week with the **average of the previous four weeks**, not just last week. One week is noisy: weekly trips swing between 468 and 545 with no real change."));
E.push(bullet("Say what three months can't tell you. You can't separate a trend from seasonality (school holidays, Chinese New Year) without a year of data. 'Usage rose 5%' is a signal to watch, not proof of growth."));
E.push(p("The link worth making in 1b and 1c: the stations losing the most bikes in the morning are losing more each month, and availability complaints jumped at the same time. That is the case for acting on the opening targets now."));

E.push(h1("9. What the supervisor's loop is"));
E.push(p("The course's supervisor's loop is **H-SAAF, the Human-Supervised Agentic Analytics Framework**: nine steps in three phases, always in the same order. Each step exists to prevent a known failure. The AI can do the work inside the loop, but a human owns it. Here it is mapped to the CityCycle pipeline:"));
E.push(table([1500, 2100, 5426], [
  ["Phase", "Step", "In the CityCycle automation"],
  ["Set up", "1 Frame", "Name the decision: where to restock, what to fix. Success = report in under 30 minutes"],
  ["", "2 Decompose", "Split into small checkable tasks: validate → compute → classify → draft → check"],
  ["", "3 Contextualise", "Write down the definitions (peak windows, severity, safety) in work_order.md"],
  ["Run and check", "4 Delegate", "Give the AI a specification, not a wish: the work order, the taxonomy, 'only use facts.json'"],
  ["", "5 Execute", "The script runs on a copy of the data and writes logs; it never edits the raw files"],
  ["", "6 Verify (the heart)", "Data contract, control totals, verify_report.py, analyst review of needs_review.csv"],
  ["Land it", "7 Integrate", "Approved report and code saved as a dated commit in the Git repository"],
  ["", "8 Govern", "AI-use log, data-quality log and sign-off recorded. If it isn't written down, it didn't happen"],
  ["", "9 Communicate", "Report in management's terms, including what the automation can't tell them"],
]));
E.push(quote("**Suggested wording (replaces 'Following the supervisor's loop'):** The automation follows a human-supervised loop: a person frames the task and sets the definitions, the AI does the routine work, and a person verifies the result before it is recorded and released. Within that loop, four decisions stay with a human:"));

E.push(h1("10. Why 'a clean run is a question, not an answer'"));
E.push(p("A 'clean run' means the pipeline finished with no errors. That proves the code ran. It doesn't prove the numbers are right. Failures come in two kinds:"));
E.push(table([4500, 4500], [
  ["Loud failure", "Silent failure"],
  ["File not found, the script crashes", "The script finishes and reports a wrong number"],
  ["You notice immediately", "Management may notice weeks later, or never"],
  ["The system stops", "The wrong result flows into decisions"],
]));
E.push(p("CityCycle's data is a perfect example. Every basic check passes: no blanks, no duplicate IDs, every station valid, durations consistent. An AI tool would truthfully report 'no errors, no missing values'. Yet underneath:"));
E.push(bullet("14 trips put the same bike on two journeys at once"));
E.push(bullet("14 of 20 station regions don't match where the station is (Raffles Place listed as 'North-East')"));
E.push(bullet("63 star ratings contradict their comment, and 26 pieces of praise are filed under 'Availability'"));
E.push(p("An AI agent is built to finish the task and say 'done', so a clean run is where the human's checking **starts**: are the row counts right, do the totals reconcile, does the result make operational sense? For example, the CBD stations emptying in the morning, which is the opposite of the usual commuter flow."));
E.push(quote("**Suggested wording:** A run that finishes without errors is treated as the start of checking, not the end. The CityCycle data passes every basic check, yet contains overlapping bike trips, mislabelled regions and ratings that contradict the comments, problems that only a deliberate check finds."));

E.push(h1("11. Small fixes in your draft"));
E.push(table([4000, 5026], [
  ["In your draft", "Change to"],
  ["Gen-AI (Claude) written, hum reviewed", "Claude-written, human-reviewed"],
  ["the AI does the routine work, bet a person owns", "but a person owns"],
  ["20 about loose breaks", "loose brakes"],
  ["hourly demand by ride type", "by rider type"],
  ["weekday 7 to 10 am peak", "weekday 07:00–09:00 and 17:30–19:30 peaks"],
  ["Step 3 output: feedback_themes.csv", "feedback_classified.csv and needs_review.csv"],
  ["At least four charts (while ECA asks for 2, I would like....)", "At least four charts: one per business question, plus the demand pattern that explains them"],
  ["Output: Two page report, data quality log, AI-use log entry", "add: needs-review list"],
  ["References: ChatGPT declaration", "Replace or add Claude: Anthropic. (2026). Claude (Opus 5.5) [Large language model]. https://claude.ai"],
]));

// =====================================================================================
// AI-USE LOG
// =====================================================================================
const LOG_INTRO = "Recommended structure, based on the GBA log, with five additions that the ECA's Section G and good record keeping need: the date; the tool and mode; a pointer to the full output (the ECA asks for 'the full output provided by the tool'); where the output is used in the report; and the Git commit that holds it.";
const LOG_COLS = ["#", "Date", "Stage", "What I asked (prompt)", "What the AI produced", "What I checked", "My decision", "Evidence / where used"];
const LOG = [
  ["Phase 1 · EXPLORE: understand the data before automating anything. Tool: Claude (Opus 5.5), chat with file upload."],
  ["1", "____", "BUILD\nProfile", "This is the data set I have: CityCycle_trips.csv, CityCycle_stations.csv, CityCycle_feedback.csv and the combined CityCycle_data.xlsx. Before doing anything else, profile it: rows, columns, data types, missing values, duplicate IDs, whether every station in the trips exists in the station list, whether duration matches end minus start, and whether the Excel workbook matches the CSVs. Do not fix anything yet. Show me what you find, with counts.",
    "Profile: trips 6,500 × 9, stations 20 × 3, feedback 300 × 6; no blanks, no duplicate IDs, all stations valid, durations consistent; workbook identical to the CSVs. Control totals: 112,366 ride-minutes, 19,104.91 km.",
    "Row counts with =COUNTA() in Excel; sum of duration_min with =SUM(); spot-checked 5 durations by hand.",
    "Accepted. A clean profile is not proof, so row 2 tests further.",
    "out/data_quality_log.csv; report 1b data-quality section"],
  ["2", "____", "BREAK\nSilent failures", "The basic checks pass. Look for problems a basic check would miss: the same bike on overlapping trips, round trips, whether distance is consistent for the same pair of stations, whether each station's region matches where the station really is, whether star ratings agree with the comment text, and whether the feedback category matches the comment.",
    "14 overlapping bike trips (e.g. BK802 twice at 18:27 on 3 Feb); 340 round trips; distance varies about 1.4 km for the same station pair; 14 of 20 regions don't match location; 63 rating–text conflicts; 26 praise comments filed under 'Availability'.",
    "Filtered BK802 on 3 Feb in Excel; looked up Raffles Place region; pivot of comment × average rating.",
    "Accepted. Region field not used for analysis; distance not used; both flagged.",
    "Data-quality table (1b); risks (1d)"],
  ["Phase 2 · DESIGN: specify the automation before building it."],
  ["3", "____", "BUILD\nWork order", "I would like to automate the process of generating CityCycle's weekly operations report, which answers: where are bikes running out, which stations are busiest, and what are riders complaining about? Write a work order for the automation with the goal, inputs, constraints, acceptance criteria and output. Constraints: no personal data in prompts, all numbers computed in code, and the AI may only quote numbers that the code produced.",
    "Work-order table (goal, inputs, constraints, acceptance criteria, output).",
    "Checked each element against the three business questions; set the 30-minute goal from my own estimate of the manual process.",
    "Modified: raised charts from 2 to 4; added the two peak windows and the needs-review list.",
    "workflow/work_order.md; 1a work-order table"],
  ["4", "____", "BUILD\nPipeline design", "This is what I need the automated pipeline to do each week: (1) validate the data and stop if a hard check fails; (2) compute station flows in the morning and evening peaks, the busiest stations and hourly demand; (3) classify each feedback comment into a theme and sentiment and flag safety issues; (4) write all numbers into one facts file; (5) draft the report only from that file; (6) check every number in the draft against it. Lay out the steps, the tool at each step and the output.",
    "Five-step pipeline: Validate, Compute, Classify, Draft, Check, with outputs.",
    "Walked one week through the steps on paper; confirmed each step has a checkable output.",
    "Accepted with edits to the wording of the steps.",
    "1a pipeline table"],
  ["5", "____", "BUILD\nTaxonomy", "Here are the distinct comment texts in the feedback file. Propose a theme and a sentiment (positive or negative) for each, based on what the text says, not the star rating. Return JSON with fields comment_text, theme, sentiment, safety_flag.",
    "18 comment texts mapped to 12 complaint themes and 4 praise themes; safety flag on 'brakes felt loose'.",
    "Read all 18 mappings myself; confirmed every comment in the file maps to one theme.",
    "Accepted as taxonomy v1 (or note any theme you renamed).",
    "THEMES in workflow/weekly_report.py; 1b feedback section"],
  ["6", "____", "BREAK\nRating vs text", "Should sentiment come from the star rating, the comment text, or both? Show me where they disagree.",
    "Text for sentiment, stars for severity; 63 comments disagree, e.g. 'hard to find a bike at peak hour' averages 4.5 stars.",
    "Pivot of comment text × average rating in Excel.",
    "Accepted. Disagreements go to needs_review.csv.",
    "work_order.md definitions; Chart 3"],
  ["Phase 3 · BUILD: turn the design into a re-runnable workflow. Tool: Claude as a coding agent."],
  ["7", "____", "BUILD\nScript", "Turn the pipeline into a Python script I can re-run every week with a --week-start option. Morning peak is 07:00–09:00 and evening peak 17:30–19:30 on weekdays. Save a data-quality log, station flows, classified feedback, a facts.json file and four charts.",
    "weekly_report.py; outputs in out/: data_quality_log.csv, station_peak_flows.csv, opening_plan.csv, feedback_classified.csv, needs_review.csv, facts.json, four charts.",
    "Ran it myself; compared total trips (6,500), top start station (Changi Business Park 533) and negative comments (218) with Excel pivots.",
    "Accepted.",
    "workflow/weekly_report.py; commit ____"],
  ["8", "____", "BREAK\nTwo peaks", "Is there an evening peak as well as a morning one, and does the evening peak put the bikes back?",
    "Morning: six stations lose 1.6–2.1 bikes per weekday. Evening: all stations between −0.6 and +0.4, so losses build up (Changi Business Park −211 over the quarter).",
    "Pivot: Marina Bay weekday departures and arrivals 07:00–09:00, divided by 64 weekdays.",
    "Accepted. Changed the peak definition from 07:00–10:00 to two windows.",
    "Chart 1; 1b findings"],
  ["9", "____", "BUILD\nRestock chart", "Can we show availability against usage to make the need to restock clearer? There is no dock-level data, so explain how you estimate it.",
    "Method: running loss and gain per station per day, 90th percentile; a safe opening range per station (enough bikes AND free docks). Chart 4: Raffles Place safe range 7–12 bikes on 15 docks.",
    "Hand-traced one day for Raffles Place in Excel (sorted departures and arrivals, running total).",
    "Accepted, with the assumption stated: no rebalancing moves recorded.",
    "Chart 4; out/opening_plan.csv"],
  ["10", "____", "BREAK\nOpening full?", "Can we assume that at the start of each day the bikes are redeployed and every station is at full capacity? Test it against the data, and compare it with other opening rules on data the rule wasn't built from.",
    "Opening full rejected: on unseen March data, riders would find no free dock on 433 of 620 station-days. Half full: 0 problems in March but 4 empty-station days in Jan–Feb. Station targets set on Jan–Feb: 0 problems in March. Fleet 899 bikes vs 450 docks.",
    "Counted bike IDs and summed capacity in Excel; checked that only 12 of 300 comments say 'docks full'.",
    "Modified my assumption: overnight reset to a station-specific target, not to full.",
    "work_order.md (opening assumption); 1b; 1d assumptions"],
  ["11", "____", "BUILD\nTrends", "We have three months of data. Add usage and complaint trends to the report: complete weeks only, this week vs the previous four-week average, monthly figures per day, and mark public holidays.",
    "Trips per day 70.9 → 71.3 → 74.4; casual 27.7 → 30.4; Woodlands +29%, Paya Lebar −24%; Raffles Place morning drain 1.2 → 2.0; availability complaints 16 → 14 → 25; billing 16 → 10 → 8. Charts 5 and 6.",
    "Monthly pivot of trips divided by days in the month; Chinese New Year week (16 Feb) checked against the calendar.",
    "Accepted. Noted that three months can't separate trend from seasonality.",
    "Charts 5–6; out/trend_*.csv; 1b, 1c"],
  ["Phase 4 · DEFEND: prove the automation can be trusted before relying on it."],
  ["12", "____", "DEFEND\nNumber check", "Write a check that confirms every number in the drafted report appears in facts.json, then test it with a draft that contains one wrong number.",
    "verify_report.py. Test: 10 of 11 numbers traced; '540 trips at Changi Business Park' flagged UNTRACED (true value 533); exit code 1.",
    "Re-ran the test myself and saw the failure.",
    "Accepted. Limitation noted: it confirms a number exists, not that it's attached to the right station.",
    "workflow/verify_report.py; 1a step 5; 1d"],
  ["13", "____", "DEFEND\nWorked example", "(to do in 1b) Run the pipeline for the week of 23–29 March 2026 from start to finish and draft the report from facts.json.", "", "", "", "1b worked example"],
  ["14", "____", "BUILD\nDraft report", "(to do in 1b) Using ONLY the figures in facts.json, write the weekly operations report in this template …", "", "", "", "1b output"],
];
const LOG_TIPS = [
  "**Prompts must be the ones you actually ran.** These are written to match what you want the log to show. Run them yourself, in a fresh Claude chat with only the CityCycle data attached, then paste the real response into 'What the AI produced' and save the full output as a file in ai_use_log/outputs/. Then the log is true, and it holds up in a viva.",
  "Fill 'What I checked' with the checks you really did, including the result (e.g. '=COUNTA(A:A)-1 = 6,500 ✓').",
  "Use Accept / Modify / Reject plus one line of 'why'. Some Modify and Reject rows are healthy: they show judgement.",
  "Number rows so the report can cite them, as the GBA did ('see AI-use log, row 9').",
  "After each working session, commit to Git with a message like 'log rows 7–9: script + two peaks', and paste the commit ID into the Evidence column.",
];

const L = [];
L.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Appendix: AI-use log (Question 1)")] }));
L.push(p(LOG_INTRO));
L.push(p("**Tool declaration:** Anthropic. (2026). Claude (Opus 5.5) [Large language model]. https://claude.ai. Claude was used in chat to profile the data and propose the feedback taxonomy, and as a coding agent to build and test the weekly report pipeline. Rows are labelled BUILD (make something), BREAK (try to find what is wrong with it) or DEFEND (prove it can be trusted)."));
L.push(table([400, 700, 900, 3700, 3000, 2300, 1700, 1700], [LOG_COLS, ...LOG], 15));
L.push(h2("How to keep this log well"));
LOG_TIPS.forEach(t => L.push(bullet(t)));

const port = { properties: { page: { margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 } } } };
const land = { properties: { page: { size: { orientation: PageOrientation.LANDSCAPE }, margin: { top: 720, bottom: 720, left: 720, right: 720 } } } };

const explainer = new Document({ styles, numbering, sections: [{ ...port, children: E }, { ...land, children: L }] });
const logDoc = new Document({ styles, numbering, sections: [{ ...land, children: L.map(x => x) }] });

// markdown copy of the log, for the repository
const md = ["# AI-use log · ANL559 ECA Question 1", "", LOG_INTRO, "",
  "Tool: Anthropic. (2026). Claude (Opus 5.5) [Large language model]. https://claude.ai", "",
  "| " + LOG_COLS.join(" | ") + " |", "|" + LOG_COLS.map(() => "---").join("|") + "|",
  ...LOG.map(r => r.length === 1 ? `| **${r[0]}** |${" |".repeat(LOG_COLS.length - 1)}` : "| " + r.map(c => String(c).replace(/\n/g, " ").replace(/\|/g, "/")).join(" | ") + " |"),
  "", "## How to keep this log well", "", ...LOG_TIPS.map(t => "- " + t), ""].join("\n");

(async () => {
  fs.writeFileSync(path.join(ROOT, "docs", "ANL559_ECA_1a_explainer.docx"), await Packer.toBuffer(explainer));
  // separate Document instance needed for the log (docx elements can't be shared across docs safely)
  const L2 = [];
  L2.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Appendix: AI-use log (Question 1)")] }));
  L2.push(p(LOG_INTRO));
  L2.push(p("**Tool declaration:** Anthropic. (2026). Claude (Opus 5.5) [Large language model]. https://claude.ai. Rows are labelled BUILD, BREAK or DEFEND."));
  L2.push(table([400, 700, 900, 3700, 3000, 2300, 1700, 1700], [LOG_COLS, ...LOG], 15));
  L2.push(h2("How to keep this log well"));
  LOG_TIPS.forEach(t => L2.push(bullet(t)));
  fs.writeFileSync(path.join(ROOT, "ai_use_log", "ANL559_ECA_AI_use_log.docx"),
    await Packer.toBuffer(new Document({ styles, numbering, sections: [{ ...land, children: L2 }] })));
  fs.writeFileSync(path.join(ROOT, "ai_use_log", "ai_use_log.md"), md);
  console.log("built");
})();
