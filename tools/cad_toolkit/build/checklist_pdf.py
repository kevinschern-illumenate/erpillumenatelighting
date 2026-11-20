"""Render the dealer DXF drafting checklist (draw-to-quote plan 6.3) to PDF.

``python -m tools.cad_toolkit.build.checklist_pdf`` writes
``illumenate_lighting/public/cad_toolkit/ilLumenate-DXF-drafting-checklist.pdf`` from
``dxf_checklist.md`` (headings, numbered items). Needs reportlab (a test dependency).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).resolve().parent / "dxf_checklist.md"
TARGET = ROOT / "illumenate_lighting/public/cad_toolkit/ilLumenate-DXF-drafting-checklist.pdf"


def blocks(text):
	"""``[(kind, text)]``: title, heading or item (continuation lines join their item)."""
	result = []
	for raw in text.splitlines():
		line = raw.rstrip()
		if not line:
			continue
		if line.startswith("# "):
			result.append(("title", line[2:]))
		elif line.startswith("## "):
			result.append(("heading", line[3:]))
		elif line[:1].isdigit():
			result.append(("item", line))
		elif result:
			kind, previous = result[-1]
			result[-1] = (kind, f"{previous} {line.strip()}")
	return result


def render(target=TARGET):
	from reportlab.lib.pagesizes import letter
	from reportlab.lib.styles import ParagraphStyle
	from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

	styles = {
		"title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=8),
		"heading": ParagraphStyle(
			"heading", fontName="Helvetica-Bold", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4
		),
		"item": ParagraphStyle(
			"item",
			fontName="Helvetica",
			fontSize=10,
			leading=13.5,
			leftIndent=14,
			firstLineIndent=-14,
			spaceAfter=4,
		),
		"body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=6),
	}
	items = blocks(SOURCE.read_text(encoding="utf-8"))
	story = []
	for kind, text in items:
		safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
		story.append(Paragraph(safe, styles.get(kind, styles["body"])))
	story.append(Spacer(1, 12))
	story.append(Paragraph("ilLumenate Lighting - draw-to-quote", styles["body"]))
	target.parent.mkdir(parents=True, exist_ok=True)
	SimpleDocTemplate(
		str(target),
		pagesize=letter,
		title="ilLumenate DXF drafting checklist",
		author="ilLumenate Lighting",
		leftMargin=54,
		rightMargin=54,
		topMargin=54,
		bottomMargin=54,
		invariant=1,
	).build(story)
	return target


def main(argv=None):
	print(f"Wrote {render()}")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
