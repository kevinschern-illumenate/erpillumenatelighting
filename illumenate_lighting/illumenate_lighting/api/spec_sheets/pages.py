# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Page layouts. Phase 0 covers the linear fixture catalog sheet, page 1.

A sheet model is a plain dict (see ``fixtures/st_helens_sf_sw/model.json``).
Layout functions place its content with the measured tokens; they never read
the database, so the same model always produces the same PDF.
"""

from datetime import date

from illumenate_lighting.illumenate_lighting.api.spec_sheets import tokens
from illumenate_lighting.illumenate_lighting.api.spec_sheets.brands import load_brand, logo_for
from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import DirectoryAssets, Page, document


def _bulleted_line(page, segments, baseline, x=None, right=None):
	"""Lay out ``segments`` separated by bullet dots, left-aligned at ``x`` or right-aligned at ``right``."""
	footer = tokens.FOOTER
	bullet = 2 * footer["bullet_radius"]
	widths = [page.width(segment, "footer_text") for segment in segments]
	total = sum(widths) + (len(segments) - 1) * (bullet + footer["bullet_gap_after"])
	cursor = x if x is not None else right - total
	for index, (segment, width) in enumerate(zip(segments, widths, strict=True)):
		page.text(cursor, baseline, segment, "footer_text")
		cursor += width
		if index < len(segments) - 1:
			page.circle(
				cursor + footer["bullet_radius"],
				baseline - footer["bullet_rise"],
				footer["bullet_radius"],
				"bullet",
			)
			cursor += bullet + footer["bullet_gap_after"]


def page_chrome(page, model, brand, page_number, page_count):
	header, footer = model["header"], model.get("footer") or {}

	# The hero sits above the top spec line; the bottom line is the top one mirrored.
	stops = tokens.spec_line_stops(model["spec_line"])
	top, bottom = tokens.SPEC_LINE_TOP, tokens.SPEC_LINE_BOTTOM
	page.gradient_rect(0, top["y"], tokens.PAGE_WIDTH, top["height"], stops)
	page.gradient_rect(0, bottom["y"], tokens.PAGE_WIDTH, bottom["height"], stops, reverse=True)

	hero = tokens.HERO
	page.image(
		header["hero"], hero["x"], hero["y"], hero["size"], hero["size"], radius=hero["radius"], fit="cover"
	)
	logo, logo_file = tokens.LOGO, logo_for(brand, model["spec_line"])["file"]
	width, height = page.natural_size(logo_file, brand=True)
	page.image(logo_file, logo["x"], logo["y"], width * logo["scale"], height * logo["scale"], brand=True)

	title = tokens.TITLE
	for index, line in enumerate(header["title_lines"]):
		page.text(title["x"], title["first_baseline"] + index * title["leading"], line, "title")
	page.text(title["x"], title["sublabel_baseline"], header["sublabel"].upper(), "sublabel")

	settings = tokens.FOOTER
	for key, label, label_x, rule_x0, rule_x1 in settings["fields"]:
		page.text(label_x, settings["label_baseline"], label, "footer_label")
		page.line(rule_x0, settings["rule_y"], rule_x1, settings["rule_y"], "text", settings["rule_width"])
		if footer.get(key):
			raise NotImplementedError("Filled footer fields arrive with submittals (Phase 3)")

	first, second = settings["first_line_baseline"], settings["second_line_baseline"]
	year = str(footer.get("copyright_year") or date.today().year)
	lines = [[segment.replace("{year}", year) for segment in line] for line in brand["footer_lines"]]
	_bulleted_line(page, lines[0], first, x=tokens.MARGIN)
	_bulleted_line(page, lines[1], second, x=tokens.MARGIN)
	page.text(tokens.CONTENT_RIGHT, first, f"{page_number}/{page_count}", "page_number", anchor="end")
	_bulleted_line(page, [brand["notice"], footer["date_code"]], second, right=tokens.CONTENT_RIGHT)


def icon_row(page, model):
	row = tokens.ICON_ROW
	for index, icon in enumerate(model.get("icons") or []):
		page.image(icon, row["x"] + index * row["pitch"], row["y"], row["size"], row["size"])
	statement = model.get("listing_statement")
	if statement:
		settings = tokens.LISTING_STATEMENT
		after = f" {statement['after']}"
		icon_right = tokens.CONTENT_RIGHT - page.width(after, "statement")
		icon_left = icon_right - settings["icon_size"]
		page.text(tokens.CONTENT_RIGHT, settings["baseline"], after, "statement", anchor="end")
		page.image(
			statement["icon"], icon_left, settings["icon_top"], settings["icon_size"], settings["icon_size"]
		)
		page.text(icon_left, settings["baseline"], f"{statement['before']} ", "statement", anchor="end")


def spec_table(page, section_baseline, table):
	"""Draw the SPECIFICATIONS table; returns the baseline of the last row."""
	settings = tokens.SPEC_TABLE
	page.text(tokens.MARGIN, section_baseline, table.get("title", "SPECIFICATIONS"), "section")
	rows = table["rows"]
	baseline = section_baseline + settings["section_to_first_row"]
	x0, x1 = settings["value_x0"], settings["value_x1"]
	for index, row in enumerate(rows):
		values = row["values"]
		column = (x1 - x0) / len(values)
		if row.get("band") == "cct":
			page.gradient_rect(
				x0,
				baseline - settings["band_top_above_baseline"],
				x1 - x0,
				settings["band_height"],
				tokens.CCT_GRADIENT,
			)
		page.text(settings["label_x"], baseline, row["label"], "spec_label")
		for position, value in enumerate(values):
			page.text(
				x0 + column * (position + 0.5),
				baseline + settings["value_baseline_shift"],
				value,
				"spec_value",
				anchor="middle",
			)
		if index < len(rows) - 1:
			rule_y = baseline + settings["rule_below_baseline"]
			page.line(tokens.MARGIN, rule_y, tokens.CONTENT_RIGHT, rule_y, "rule", settings["rule_width"])
			baseline += settings["row_pitch"]
	return baseline


def drawings(page, section_baseline, section):
	"""Place drawings at their artboard size, left to right, with optional captions."""
	settings = tokens.DRAWINGS
	page.text(tokens.MARGIN, section_baseline, section["title"], "section")
	x = tokens.MARGIN
	for item in section["drawings"]:
		width, height = page.natural_size(item["asset"])
		top = section_baseline + settings["top_below_section"]
		if item.get("caption"):
			page.text(x, section_baseline + settings["caption_below_section"], item["caption"], "caption")
			top += settings["caption_offset"]
		page.image(item["asset"], x, top, width, height)
		x += width + settings["gap"]


def resolve_brand(model):
	overrides = model.get("brand") or {}
	return load_brand(overrides.get("brand_code") or "illumenate", overrides)


def placeholders(model):
	"""Placeholder artwork this sheet would use; a revision cannot be approved while any remain."""
	brand = resolve_brand(model)
	found = (
		[f"logo {model['spec_line']}: {note}"]
		if (note := logo_for(brand, model["spec_line"]).get("placeholder"))
		else []
	)
	return found + [f"{ref}: {note}" for ref, note in (model.get("placeholders") or {}).items()]


def linear_catalog_page_one(model, assets, page_count):
	brand = resolve_brand(model)
	page = Page(tokens.brand_colors(brand), assets, DirectoryAssets(brand["root"]))
	page_chrome(page, model, brand, 1, page_count)
	icon_row(page, model)
	last_row = spec_table(page, model["spec_table"]["section_baseline"], model["spec_table"])
	drawings(page, last_row + tokens.SPEC_TABLE["after_table_to_section"], model["dimensions"])
	return page


def build_html(model, assets):
	"""Phase 0: the linear catalog sheet's first page as a self-contained HTML document."""
	if model.get("family") != "Linear Fixture":
		raise ValueError("Phase 0 renders linear fixture catalog sheets only")
	page_count = model.get("footer", {}).get("page_count") or 1
	pages = [linear_catalog_page_one(model, assets, page_count)]
	return document(pages, " ".join(model["header"]["title_lines"]))
