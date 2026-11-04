"""Step 7 RENDER: turn the checked weekly report (markdown) into a Word document with its charts embedded.

    python workflow/render_report.py out/week_2026-03-23/weekly_report_draft.md

Writes weekly_report.docx next to the draft. Run it only after verify_report.py passes; the rendering
changes no wording or numbers, it only lays the text out and places each chart where the draft names it.
"""
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

src = Path(sys.argv[1]).resolve()
lines = src.read_text(encoding="utf-8").splitlines()
doc = Document()
st = doc.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(10.5)
for sec in doc.sections:
    sec.left_margin = sec.right_margin = Inches(0.9); sec.top_margin = sec.bottom_margin = Inches(0.8)
fig = 0


def add_runs(par, text):
    for part in re.split(r"(\*\*[^*]+\*\*)", text):
        if part:
            run = par.add_run(part[2:-2] if part.startswith("**") else part)
            run.bold = part.startswith("**")


i = 0
while i < len(lines):
    line = lines[i].rstrip()
    if not line:
        i += 1; continue
    if line.startswith("# "):
        h = doc.add_heading(line[2:], level=1)
    elif line.startswith("## "):
        doc.add_heading(line[3:], level=2)
    elif line.startswith("!["):
        alt, img = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line).groups()
        fig += 1
        doc.add_picture(str(src.parent / img), width=Inches(6.2))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap = doc.add_paragraph(); r = cap.add_run(f"Chart {fig}. {alt}"); r.italic = True; r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0x52, 0x51, 0x4E)
    elif line.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].startswith("|"):
            if not re.match(r"^\|[-| ]+\|$", lines[i]):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
            i += 1
        t = doc.add_table(rows=len(rows), cols=len(rows[0])); t.style = "Light Grid Accent 1"
        for r_i, row in enumerate(rows):
            for c_i, cell in enumerate(row):
                add_runs(t.cell(r_i, c_i).paragraphs[0], cell)
        continue
    elif line.startswith("- "):
        add_runs(doc.add_paragraph(style="List Bullet"), line[2:])
    else:
        text = line[1:-1] if (line.startswith("*") and line.endswith("*") and not line.startswith("**")) else line
        add_runs(doc.add_paragraph(), text)
    i += 1

out = src.parent / "weekly_report.docx"
doc.save(out)
print(f"Wrote {out.relative_to(src.parents[2]) if len(src.parents) > 2 else out} with {fig} charts")
