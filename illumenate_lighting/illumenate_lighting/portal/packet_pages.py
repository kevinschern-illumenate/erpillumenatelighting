"""The pages a spec submittal packet generates itself: shared brand styling, the logo and the contents page.

Every page here is customer-facing, so it names documents and pages only; why a document is
missing is recorded on the export job for staff, never printed.
"""

import base64
import html
import os
from functools import lru_cache

NAVY = "#1a365d"
INK = "#1f2933"
MUTED = "#6b7280"
RULE = "#d9dee5"
TINT = "#f5f7fa"

DOCUMENT_LABELS = {
	"filled_submittal": "Spec submittal",
	"approved_literature": "Product literature",
	"approved_item_literature": "Product literature",
	"uploaded_literature": "Spec sheet",
	"template_spec_sheet": "Spec sheet",
	"selected_line_document": "Attached document",
	"generated_sheet": "Spec sheet",
}

# wkhtmltopdf's WebKit predates flexbox gaps, so layouts here are tables.
BASE_CSS = f"""
body {{ font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: {INK}; margin: 0; font-size: 10pt; }}
.brand {{ width: 100%; border-collapse: collapse; border-bottom: 2px solid {NAVY}; margin-bottom: 18px; }}
.brand td {{ padding: 0 0 8px 0; vertical-align: bottom; border: 0; }}
.brand img {{ height: 22px; }}
.brand .wordmark {{ font-size: 15pt; font-weight: bold; color: {NAVY}; letter-spacing: 0.5px; }}
.brand .doc {{ text-align: right; font-size: 8pt; color: {MUTED}; text-transform: uppercase; letter-spacing: 1.5px; }}
h1 {{ font-size: 18pt; font-weight: 300; color: {NAVY}; margin: 0 0 4px 0; }}
.subtitle {{ font-size: 10pt; color: {MUTED}; margin: 0 0 18px 0; }}
table.list {{ width: 100%; border-collapse: collapse; }}
table.list th {{ text-align: left; font-size: 7.5pt; font-weight: bold; color: {MUTED}; text-transform: uppercase;
	letter-spacing: 1px; padding: 6px 8px; border-bottom: 1.5px solid {NAVY}; }}
table.list td {{ padding: 7px 8px; border-bottom: 1px solid {RULE}; font-size: 9pt; vertical-align: top; }}
table.list thead {{ display: table-header-group; }}
table.list tr {{ page-break-inside: avoid; }}
table.list .num {{ text-align: right; white-space: nowrap; }}
table.list .type {{ font-weight: bold; color: {NAVY}; white-space: nowrap; }}
table.list .part {{ word-break: break-all; }}
.footer {{ margin-top: 24px; padding-top: 8px; border-top: 1px solid {RULE}; font-size: 7.5pt; color: {MUTED}; }}
"""


@lru_cache(maxsize=1)
def logo_data_uri():
	"""The wordmark inlined, so rendering needs no request back to the site; None when the image is absent."""
	path = os.path.join(
		os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "public", "images", "nav-logo.png"
	)
	try:
		with open(path, "rb") as image:
			return "data:image/png;base64," + base64.b64encode(image.read()).decode()
	except OSError:
		return None


def brand_header(document_title):
	logo = logo_data_uri()
	mark = (
		f'<img src="{logo}" alt="ilLumenate Lighting">'
		if logo
		else '<span class="wordmark">ilLumenate Lighting</span>'
	)
	return (
		f'<table class="brand"><tr><td>{mark}</td>'
		f'<td class="doc">{html.escape(document_title)}</td></tr></table>'
	)


def contents_html(manifest, *, schedule_title=None, project_title=None):
	"""The packet's table of contents. A document that is not in the packet shows a dash, not a reason."""
	rows = []
	for entry in manifest:
		included = entry.get("status") == "included" and entry.get("page_start")
		page = str(entry["page_start"]) if included else "&mdash;"
		document = DOCUMENT_LABELS.get(entry.get("source_kind"), "") if included else ""
		rows.append(
			"<tr>"
			f'<td class="type">{html.escape(str(entry.get("designation") or ""))}</td>'
			f'<td class="part">{html.escape(str(entry.get("part_number") or ""))}</td>'
			f"<td>{html.escape(document)}</td>"
			f'<td class="num">{page}</td>'
			"</tr>"
		)
	subtitle = " &middot; ".join(
		html.escape(str(value)) for value in (project_title, schedule_title) if value
	)
	return (
		f"<html><head><meta charset='utf-8'><style>{BASE_CSS}</style></head><body>"
		+ brand_header("Submittal package")
		+ "<h1>Contents</h1>"
		+ (f'<p class="subtitle">{subtitle}</p>' if subtitle else "")
		+ '<table class="list"><thead><tr><th style="width:14%">Type</th><th>Part number</th>'
		+ '<th style="width:20%">Document</th><th class="num" style="width:10%">Page</th></tr></thead><tbody>'
		+ "".join(rows)
		+ "</tbody></table></body></html>"
	)


# The ilLumenate print design (templates/print/ill_print.html, docs/PRINT_FORMATS.md), for the
# contents page that follows the Fixture Schedule print layout in a generated-sheet packet.
PRINT_NAVY = "#172e48"
PRINT_MUTED = "#5d6d7f"
PRINT_INK = "#231f20"
PRINT_HAIRLINE = "#d1d6db"
PRINT_GOLD = "#fdc757"
PRINT_CSS = f"""
body {{ font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: {PRINT_INK}; margin: 0; font-size: 8.5px; }}
.head {{ width: 100%; border-collapse: collapse; }}
.head td {{ vertical-align: top; padding: 0; border: 0; }}
.head img {{ height: 28px; }}
.head .wordmark {{ font-size: 15px; font-weight: bold; color: {PRINT_NAVY}; }}
.head .right {{ text-align: right; padding-top: 10px; }}
.title {{ font-weight: 700; font-size: 18px; letter-spacing: 2px; text-transform: uppercase; color: {PRINT_NAVY}; }}
.subtitle {{ font-size: 8.5px; color: {PRINT_MUTED}; margin-top: 4px; }}
.rule {{ border-top: 1px solid {PRINT_NAVY}; margin: 12px 0 16px 0; height: 0; }}
.rule span {{ display: block; width: 48px; border-top: 2px solid {PRINT_GOLD}; margin-top: -1.5px; }}
table.list {{ width: 100%; border-collapse: collapse; }}
table.list thead {{ display: table-header-group; }}
table.list th {{ text-align: left; font-size: 6.5px; font-weight: bold; color: {PRINT_MUTED}; text-transform: uppercase;
	letter-spacing: 1px; padding: 4px 6px; border-bottom: 1px solid {PRINT_NAVY}; background: none; }}
table.list td {{ padding: 6px; border-bottom: 1px solid {PRINT_HAIRLINE}; font-size: 8.5px; vertical-align: top; }}
table.list tr {{ page-break-inside: avoid; }}
table.list .num {{ text-align: right; white-space: nowrap; }}
table.list .type {{ font-weight: bold; color: {PRINT_NAVY}; white-space: nowrap; }}
table.list .part {{ font-size: 7.5px; word-break: break-all; }}
.closing {{ margin-top: 16px; padding-top: 6px; border-top: 1px solid {PRINT_HAIRLINE}; font-size: 7.5px; color: {PRINT_MUTED}; }}
"""


def print_contents_html(manifest, *, schedule_title=None, project_title=None):
	"""The contents page in the print design, listing each document after the schedule pages."""
	rows = []
	for entry in manifest:
		included = entry.get("status") == "included" and entry.get("page_start")
		page = str(entry["page_start"]) if included else "&mdash;"
		document = DOCUMENT_LABELS.get(entry.get("source_kind"), "") if included else ""
		rows.append(
			"<tr>"
			f'<td class="type">{html.escape(str(entry.get("designation") or ""))}</td>'
			f'<td class="part">{html.escape(str(entry.get("part_number") or ""))}</td>'
			f"<td>{html.escape(document)}</td>"
			f'<td class="num">{page}</td>'
			"</tr>"
		)
	subtitle = " &middot; ".join(
		html.escape(str(value)) for value in (project_title, schedule_title) if value
	)
	logo = logo_data_uri()
	mark = (
		f'<img src="{logo}" alt="ilLumenate Lighting">'
		if logo
		else '<span class="wordmark">ilLumenate Lighting</span>'
	)
	return (
		f"<html><head><meta charset='utf-8'><style>{PRINT_CSS}</style></head><body>"
		+ f'<table class="head"><tr><td style="width:55%">{mark}</td><td class="right">'
		+ '<div class="title">Submittal Contents</div>'
		+ (f'<div class="subtitle">{subtitle}</div>' if subtitle else "")
		+ '</td></tr></table><div class="rule"><span></span></div>'
		+ '<table class="list"><thead><tr><th style="width:14%">Type</th><th>Part number</th>'
		+ '<th style="width:20%">Document</th><th class="num" style="width:10%">Page</th></tr></thead><tbody>'
		+ "".join(rows)
		+ "</tbody></table>"
		+ '<div class="closing">Pages are numbered from the first page of the fixture schedule.</div>'
		+ "</body></html>"
	)
