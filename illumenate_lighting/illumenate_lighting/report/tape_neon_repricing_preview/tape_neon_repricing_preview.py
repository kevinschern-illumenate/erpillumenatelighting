# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Old versus new tape/neon unit prices under sum-then-round (hardening plan 6.3, D3).

Read-only. Both columns are priced from the line's pinned build against today's
price list, so the difference is only the rounding change. Issued Quotations,
Sales Orders and pricing snapshots keep their own stored rates and never change.
Open schedules pick up the new price when they are next opened or recalculated.
"""

import frappe
from frappe import _

OPEN_STATUSES = ("DRAFT", "READY", "QUOTED")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Schedule"), "fieldname": "schedule", "fieldtype": "Link", "options": "ilL-Project-Fixture-Schedule", "width": 170},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
		{"label": _("Line"), "fieldname": "line", "fieldtype": "Int", "width": 60},
		{"label": _("Build"), "fieldname": "configured_tape_neon", "fieldtype": "Link", "options": "ilL-Configured-Tape-Neon", "width": 170},
		{"label": _("Part Number"), "fieldname": "part_number", "fieldtype": "Data", "width": 200},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 60},
		{"label": _("Old Unit MSRP"), "fieldname": "old_unit", "fieldtype": "Currency", "width": 120},
		{"label": _("New Unit MSRP"), "fieldname": "new_unit", "fieldtype": "Currency", "width": 120},
		{"label": _("Line Difference"), "fieldname": "line_difference", "fieldtype": "Currency", "width": 120},
		{"label": _("Note"), "fieldname": "note", "fieldtype": "Data", "width": 260},
	]


def get_data(filters):
	from illumenate_lighting.illumenate_lighting.api.tape_neon_build import current_estimate

	statuses = [filters.status] if filters.get("status") in OPEN_STATUSES else list(OPEN_STATUSES)
	schedules = {
		row.name: row
		for row in frappe.get_all(
			"ilL-Project-Fixture-Schedule", filters={"status": ["in", statuses]}, fields=["name", "status"]
		)
	}
	if not schedules:
		return []
	lines = frappe.get_all(
		"ilL-Child-Fixture-Schedule-Line",
		filters={
			"parenttype": "ilL-Project-Fixture-Schedule",
			"parent": ["in", list(schedules)],
			"configured_tape_neon": ["is", "set"],
		},
		fields=["parent", "idx", "configured_tape_neon", "qty"],
		order_by="parent asc, idx asc",
	)
	prices = {}
	rows = []
	for line in lines:
		name = line.configured_tape_neon
		if name not in prices:
			prices[name] = _price(name, current_estimate)
		old, new, part_number, note = prices[name]
		if filters.get("only_changed", 1) and not note and old == new:
			continue
		qty = float(line.qty or 0)
		rows.append(
			{
				"schedule": line.parent,
				"status": schedules[line.parent].status,
				"line": line.idx,
				"configured_tape_neon": name,
				"part_number": part_number,
				"qty": qty,
				"old_unit": old,
				"new_unit": new,
				"line_difference": None if note else round((new - old) * qty, 2),
				"note": note,
			}
		)
	return rows


def _price(name, current_estimate):
	doc = frappe.get_doc("ilL-Configured-Tape-Neon", name)
	try:
		return (
			current_estimate(doc, legacy_rounding=True),
			current_estimate(doc),
			doc.get("part_number"),
			"",
		)
	except Exception as exc:
		# Unverifiable or unpriced builds are listed so sales can reconfigure them.
		return None, None, doc.get("part_number"), str(exc)[:240]
