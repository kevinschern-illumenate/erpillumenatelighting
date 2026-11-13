# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Delivered lumens per foot on the fixture template (owner, 2026-11-13).

One row per fixture output level (lm/ft), one column per lens: White, Frosted, Clear, Black.
Rebuilt on every template save from the template's own data, like the old Export Spec Sheet
CSV (``api/spec_sheet_export.py``) without the CCT multiplier:

    delivered = tape spec Lumens per Foot x lens Transmission

for each of the template's allowed tape offerings and active Lens Appearance options (lens
Code WH, FR, CL or BK; an offering limited to one lens counts for that lens only). Each value
goes to the one fixture output level (lm/ft, never lm/sqft) nearest to it; when two land on the
same level the nearer one wins. Levels no lens reaches are left out; a lens that does not reach
a level leaves its cell empty.
"""

import math

import frappe

FIELD = "delivered_lumens"
DOCTYPES = ("ilL-Fixture-Template",)
LENS_COLUMNS = {"WH": "white", "FR": "frosted", "CL": "clear", "BK": "black"}
NOT_REACHED = "\u2014"


def per_foot(level):
	"""Pure: whether an output level is per foot (not an LED sheet's per square foot)."""
	name = str(level.get("output_level_name") or level.get("name") or "").lower().replace(" ", "")
	return "sqft" not in name and "/ft" in name


def table(lenses, tapes, levels):
	"""Pure: the rows.

	``lenses``: {lens column: (lens name, transmission fraction)}. ``tapes``: [(lumens per foot,
	lens name the offering is limited to or None)]. ``levels``: [{name, value}] per-foot
	fixture levels. Returns [{"output_level", <lens column>: "127" or a dash, ...}] by level
	value, with a column only for the template's lenses.
	"""
	levels = sorted((level for level in levels if level.get("value")), key=lambda level: level["value"])
	if not levels:
		return []
	cells = {}  # (level name, column) -> (distance, value)
	for column, (lens_name, transmission) in lenses.items():
		for lumens, only_lens in tapes:
			if not lumens or (only_lens and only_lens != lens_name):
				continue
			delivered = float(lumens) * transmission
			level = min(levels, key=lambda level: abs(level["value"] - delivered))
			distance = abs(level["value"] - delivered)
			key = (level["name"], column)
			if key not in cells or distance < cells[key][0]:
				cells[key] = (distance, round(delivered, 1))
	rows = []
	for level in levels:
		if not any((level["name"], column) in cells for column in lenses):
			continue
		# Owner, 2026-11-13: a lens the template has but that does not reach this output shows
		# a dash, never 0; a lens the template does not have stays empty (its column is hidden).
		row = {"output_level": level["name"]}
		for column in lenses:
			cell = cells.get((level["name"], column))
			# Whole numbers, rounded up (owner, 2026-11-13); rounded to one decimal first so float
			# noise (56.0000001) does not round up.
			row[column] = str(math.ceil(cell[1])) if cell else NOT_REACHED
		rows.append(row)
	return rows


def transmission_fraction(value):
	"""Pure: 0.56 or 56 -> 0.56; empty counts as 100%."""
	if not value:
		return 1.0
	value = float(value)
	return value / 100 if value > 1 else value


def rows_for(template):
	"""The template's delivered lumens rows, read from its options, tape offerings and levels."""
	lenses = {}
	for option in template.get("allowed_options") or []:
		if option.get("option_type") != "Lens Appearance" or not option.get("lens_appearance"):
			continue
		if option.get("is_active") == 0:
			continue
		lens = frappe.db.get_value(
			"ilL-Attribute-Lens Appearance", option.lens_appearance, ["code", "transmission"], as_dict=True
		)
		column = LENS_COLUMNS.get(str((lens or {}).get("code") or "").upper())
		if column and column not in lenses:
			lenses[column] = (option.lens_appearance, transmission_fraction((lens or {}).get("transmission")))
	from illumenate_lighting.illumenate_lighting.api.item_availability import allowed_tape_offering_rows

	tapes = []
	for row in allowed_tape_offering_rows(template):
		if not row.get("tape_offering"):
			continue
		tape_spec = frappe.db.get_value("ilL-Rel-Tape Offering", row.tape_offering, "tape_spec")
		lumens = frappe.db.get_value("ilL-Spec-LED Tape", tape_spec, "lumens_per_foot") if tape_spec else None
		tapes.append((lumens, row.get("lens_appearance") or None))
	levels = [
		level
		for level in frappe.get_all(
			"ilL-Attribute-Output Level",
			filters={"is_fixture_level": 1},
			fields=["name", "output_level_name", "value"],
		)
		if per_foot(level)
	]
	return table(lenses, tapes, levels)


def refresh(template):
	"""Rebuild the table. Called from template_listing.refresh_template."""
	meta = getattr(template, "meta", None)
	if template.doctype not in DOCTYPES or (meta is not None and not meta.has_field(FIELD)):
		return
	template.set(FIELD, rows_for(template))
