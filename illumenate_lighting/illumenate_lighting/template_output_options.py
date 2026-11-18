# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Output Options on the fixture template (owner, 2026-11-18).

For each fixture output level (lm/ft) and each lens the template has: the fixture wattage
(W/ft) and max run length of the tape that makes that output through that lens. The tape is
picked the same way as for Delivered Lumens (``template_delivered_lumens``): each allowed tape's
Lumens per Foot x the lens Transmission goes to the nearest per-foot fixture level, the nearer
tape winning a level. Its wattage is the tape spec's Watts per Foot (the highest, when several
tape specs have that lumen output) and its max run length the tape spec's Max Run Length (the
shortest).

Lenses with the same numbers at every level share a row group: a lens on its own is "White
Lens"; a group of several is "Other Lenses" (or their names, when there is more than one such
group). A lens that does not reach a level shows a dash. One row per lens group and level,
rebuilt on every save; the spec sheet lays it out with the levels as columns.
"""

import frappe

from illumenate_lighting.illumenate_lighting.template_delivered_lumens import (
	LENS_COLUMNS,
	NOT_REACHED,
	per_foot,
	transmission_fraction,
)

FIELD = "output_options"
DOCTYPE = "ilL-Fixture-Template"


def _watts(value):
	return f"{float(value):.1f}W" if value else NOT_REACHED


def _run(value):
	return f"{float(value):g}ft" if value else NOT_REACHED


def table(lenses, tapes, levels):
	"""Pure: the rows.

	``lenses``: [(lens name, transmission fraction)] in display order. ``tapes``: [(lumens per
	foot, lens name the offering is limited to or None, watts per foot, max run length ft)].
	``levels``: [{name, value}] per-foot fixture levels. Returns [{"lens_group",
	"output_level", "fixture_wattage", "max_run_length"}] by group, then level value; only
	levels some lens reaches.
	"""
	levels = sorted((level for level in levels if level.get("value")), key=lambda level: level["value"])
	if not levels or not lenses:
		return []
	cells = {}  # (lens name, level name) -> (distance, lumens)
	for lens_name, transmission in lenses:
		for lumens, only_lens, _watts_ft, _run_ft in tapes:
			if not lumens or (only_lens and only_lens != lens_name):
				continue
			delivered = float(lumens) * transmission
			level = min(levels, key=lambda level: abs(level["value"] - delivered))
			distance = abs(level["value"] - delivered)
			key = (lens_name, level["name"])
			if key not in cells or distance < cells[key][0]:
				cells[key] = (distance, float(lumens))
	reached = [level for level in levels if any((lens, level["name"]) in cells for lens, _t in lenses)]

	def numbers(lens_name, level):
		cell = cells.get((lens_name, level["name"]))
		if not cell:
			return (None, None)
		matching = [
			(w, r)
			for lumens, only_lens, w, r in tapes
			if lumens and float(lumens) == cell[1] and (not only_lens or only_lens == lens_name)
		]
		watts = max((w for w, _r in matching if w), default=None)
		run = min((r for _w, r in matching if r), default=None)
		return (watts, run)

	values = {lens: tuple(numbers(lens, level) for level in reached) for lens, _t in lenses}
	groups = []  # [(names, values)]
	for lens, _t in lenses:
		for names, group_values in groups:
			if group_values == values[lens]:
				names.append(lens)
				break
		else:
			groups.append(([lens], values[lens]))
	singles = [group for group in groups if len(group[0]) == 1]
	several = [group for group in groups if len(group[0]) > 1]

	def label(names):
		if len(names) == 1:
			return f"{names[0]} Lens"
		if len(several) == 1:
			return "Other Lenses"
		return " & ".join(names) + " Lenses"

	rows = []
	for names, group_values in singles + several:
		for level, (watts, run) in zip(reached, group_values, strict=True):
			rows.append(
				{
					"lens_group": label(names),
					"output_level": level["name"],
					"fixture_wattage": _watts(watts),
					"max_run_length": _run(run),
				}
			)
	return rows


def rows_for(template):
	"""The template's Output Options rows, read from its options, tape offerings and levels."""
	order = list(LENS_COLUMNS)
	found = {}
	for option in template.get("allowed_options") or []:
		if option.get("option_type") != "Lens Appearance" or not option.get("lens_appearance"):
			continue
		if option.get("is_active") == 0:
			continue
		lens = frappe.db.get_value(
			"ilL-Attribute-Lens Appearance", option.lens_appearance, ["code", "transmission"], as_dict=True
		)
		code = str((lens or {}).get("code") or "").upper()
		if code in LENS_COLUMNS and code not in found:
			found[code] = (option.lens_appearance, transmission_fraction((lens or {}).get("transmission")))
	lenses = [found[code] for code in order if code in found]
	from illumenate_lighting.illumenate_lighting.api.item_availability import allowed_tape_offering_rows

	tapes = []
	for row in allowed_tape_offering_rows(template):
		if not row.get("tape_offering"):
			continue
		tape_spec = frappe.db.get_value("ilL-Rel-Tape Offering", row.tape_offering, "tape_spec")
		spec = (
			frappe.db.get_value(
				"ilL-Spec-LED Tape",
				tape_spec,
				["lumens_per_foot", "watts_per_foot", "voltage_drop_max_run_length_ft"],
				as_dict=True,
			)
			if tape_spec
			else None
		) or {}
		tapes.append(
			(
				spec.get("lumens_per_foot"),
				row.get("lens_appearance") or None,
				spec.get("watts_per_foot"),
				spec.get("voltage_drop_max_run_length_ft"),
			)
		)
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
	if template.doctype != DOCTYPE or (meta is not None and not meta.has_field(FIELD)):
		return
	template.set(FIELD, rows_for(template))
