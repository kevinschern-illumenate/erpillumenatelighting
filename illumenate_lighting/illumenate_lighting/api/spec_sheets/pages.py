# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Page layouts. Phase 0 covers the linear fixture catalog sheet, page 1.

A sheet model is a plain dict (see ``fixtures/st_helens_sf_sw/model.json``).
Layout functions place its content with the measured tokens; they never read
the database, so the same model always produces the same PDF.
"""

from illumenate_lighting.illumenate_lighting.api.spec_sheets import tokens
from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import Page, document


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


def page_chrome(page, model, page_number, page_count):
	header, brand, footer = model["header"], model["brand"], model.get("footer") or {}

	# The hero sits above the top spec line; the bottom line is the top one mirrored.
	top, bottom = tokens.SPEC_LINE_TOP, tokens.SPEC_LINE_BOTTOM
	page.image(brand["spec_line"], 0, top["y"], tokens.PAGE_WIDTH, top["height"])
	page.image(brand["spec_line"], 0, bottom["y"], tokens.PAGE_WIDTH, bottom["height"], flip_x=True)

	hero = tokens.HERO
	page.image(
		header["hero"], hero["x"], hero["y"], hero["size"], hero["size"], radius=hero["radius"], fit="cover"
	)
	logo = tokens.LOGO
	page.image(brand["logo"], logo["x"], logo["y"], logo["width"], logo["height"])

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
	_bulleted_line(page, brand["footer_lines"][0], first, x=tokens.MARGIN)
	_bulleted_line(page, brand["footer_lines"][1], second, x=tokens.MARGIN)
	page.text(tokens.CONTENT_RIGHT, first, f"{page_number}/{page_count}", "page_number", anchor="end")
	_bulleted_line(page, [brand["notice"], footer["date_code"]], second, right=tokens.CONTENT_RIGHT)


def icon_row(page, model):
	row = tokens.ICON_ROW
	x = row["x"]
	for icon in model.get("icons") or []:
		width, height = page.natural_size(icon)
		page.image(icon, x, row["y"], width, height)
		x += width + row["gap"]
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
	page.text(tokens.MARGIN, section_baseline, section["title"], "section")
	for item in section["drawings"]:
		if item.get("caption"):
			page.text(
				item.get("caption_x", item["x"]),
				section_baseline + tokens.DRAWINGS["caption_below_section"],
				item["caption"],
				"caption",
			)
		page.image(item["asset"], item["x"], section_baseline + item["dy"], item["width"], item["height"])


def linear_catalog_page_one(model, assets, page_count):
	page = Page(tokens.brand_colors(model.get("brand")), assets)
	page_chrome(page, model, 1, page_count)
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
